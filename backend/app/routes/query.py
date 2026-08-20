import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.config import get_settings
from app.db import get_db
from app.models import (
    Customer,
    CustomerEndpoint,
    CustomerRecordLink,
    ProtectedTokenRegistry,
    VaultKeyVersion,
    utcnow,
)
from app.schemas import CitedAnswer, ExposureReceipt, QueryCitation, QueryRequest, QueryResponse
from app.security.detect import contains_known_pii, detect_spans
from app.security.detokenize import TOKEN_PATTERN, detokenize_response_with_trace, hash_query
from app.security.query_entities import resolve_registered_entity_spans
from app.security.tokenize import persist_vault_entries, tokenize_record
from app.services.conversation_planning import plan_conversation
from app.services.conversations import (
    get_or_create_conversation,
    is_ordinal_reference_question,
    is_person_reference_question,
    is_referential_question,
    persist_turn,
    prior_citation_hits,
    protected_history,
    protected_planning_history,
    turn_citation_hits,
)
from app.services.embeddings import embed_query_cached
from app.services.intelligence import (
    authorize_brief_with_trace,
    citation_freshness,
    generate_protected_brief,
    validate_protected_brief,
)
from app.services.query_filters import list_eligible_hits
from app.services.query_planning import QueryIntent, QueryPlan, plan_query, source_inventory
from app.services.reasoning import (
    answer_all_query_with_citations,
    is_contact_enumeration,
    is_customer_profile_lookup,
    structured_contact_lookup,
    structured_customer_profile_lookup,
    structured_record_listing,
    unknown_tokens,
)
from app.services.retrieval import RetrievalHit, retrieve_hybrid_hits

router = APIRouter(tags=["query"])
logger = logging.getLogger(__name__)

# Open-ended SEMANTIC questions get similarity-ranked evidence rather than every
# eligible row; ANALYZE_ALL keeps the unbounded listing since its whole meaning is
# "every/all/entire" and truncating to top-k would silently drop requested data.
SEMANTIC_TOP_K = 10


@router.post("/query", response_model=QueryResponse)
def query(
    payload: QueryRequest,
    principal: CurrentUser,
    db: Session = Depends(get_db),
) -> QueryResponse:
    inventory = source_inventory(db, str(principal.tenant_id))
    plan = plan_query(
        payload.question,
        [source for source, _count in inventory],
        tenant_id=str(principal.tenant_id),
    )
    deterministic_intent = plan.intent
    try:
        conversation = get_or_create_conversation(
            db, payload.conversation_id, str(principal.tenant_id), str(principal.user_id)
        )
    except ValueError as error:
        code = str(error)
        raise HTTPException(
            status_code=410 if code == "conversation_expired" else 404,
            detail=code,
        ) from error
    if (payload.customer_id is not None or payload.clear_customer_context) and not (
        get_settings().customer_intelligence_enabled
    ):
        raise HTTPException(status_code=503, detail="customer_intelligence_disabled")
    if payload.clear_customer_context:
        conversation.context_customer_id = None
        conversation.context_updated_at = utcnow()
        db.commit()
    elif payload.customer_id is not None:
        customer = db.get(Customer, payload.customer_id)
        if customer is None or customer.tenant_id != str(principal.tenant_id):
            raise HTTPException(status_code=404, detail="customer_not_found")
        conversation.context_customer_id = customer.id
        conversation.context_updated_at = utcnow()
        db.commit()
    if conversation.context_customer_id is not None:
        customer_content_ids = list(
            db.scalars(
                select(CustomerRecordLink.tokenized_content_id).where(
                    CustomerRecordLink.tenant_id == str(principal.tenant_id),
                    CustomerRecordLink.customer_id == conversation.context_customer_id,
                    CustomerRecordLink.match_status == "verified",
                )
            ).all()
        )
        plan = QueryPlan(plan.intent, plan.filters.with_content_ids(customer_content_ids or [-1]))
    history = protected_history(db, conversation.id, str(principal.tenant_id))
    query_id = f"query-{uuid.uuid4()}"
    detected_spans = detect_spans(payload.question)
    query_spans = resolve_registered_entity_spans(
        db,
        payload.question,
        str(principal.tenant_id),
        detected_spans,
    )
    sanitized_question, query_entries = tokenize_record(
        payload.question, query_spans, query_id, str(principal.tenant_id), db=db
    )
    if contains_known_pii(sanitized_question):
        raise HTTPException(
            status_code=422, detail="The question contains unsupported sensitive data"
        )
    persist_vault_entries(db, query_entries)
    db.commit()

    reference_requested = bool(payload.conversation_id) and is_referential_question(
        payload.question
    )
    explicit_entity = any(
        span.label.casefold() in {"person", "company name"} for span in query_spans
    )
    ordinal_reference = bool(payload.conversation_id) and is_ordinal_reference_question(
        payload.question
    )
    planning_history = (
        protected_planning_history(db, conversation.id, str(principal.tenant_id))
        if payload.conversation_id
        and not explicit_entity
        and not ordinal_reference
        else []
    )
    conversational_plan = (
        plan_conversation(
            history=planning_history,
            protected_question=sanitized_question,
            current_intent=plan.intent,
            available_sources=[source for source, _count in inventory],
        )
        if planning_history
        else None
    )
    if ordinal_reference:
        # Ordinals already select exact prior evidence. They are direct inspections,
        # even when the user misspells "describe" and the lexical planner says semantic.
        plan = QueryPlan(QueryIntent.LOOKUP, plan.filters)
    elif conversational_plan is not None:
        # The model may upgrade an ambiguous semantic phrase into a direct lookup,
        # but it must not turn an explicit reply/contact lookup into an analytical card.
        resolved_intent = (
            QueryIntent.LOOKUP
            if QueryIntent.LOOKUP in {plan.intent, conversational_plan.query_intent}
            else QueryIntent.SEMANTIC
        )
        plan = QueryPlan(resolved_intent, plan.filters)

    if conversational_plan is not None and conversational_plan.referenced_turn is not None:
        reference_requested = True
        prior_hits = turn_citation_hits(
            db,
            conversation.id,
            conversational_plan.referenced_turn,
            str(principal.tenant_id),
        )
    else:
        prior_hits = (
            prior_citation_hits(
                db,
                conversation.id,
                payload.question,
                str(principal.tenant_id),
            )
            if reference_requested
            else None
        )
    if prior_hits is not None:
        prior_ids = [hit.content_id for hit in prior_hits]
        prior_hits = (
            list_eligible_hits(db, plan.filters.with_content_ids(prior_ids)) if prior_ids else []
        )
    referential = reference_requested and bool(prior_hits)
    ambiguous_person_reference = bool(
        conversation.context_customer_id is None
        and (
            (conversational_plan is not None and conversational_plan.needs_clarification)
            or (
                referential
                and is_person_reference_question(payload.question)
                and len(prior_hits or []) != 1
            )
        )
    )
    # Referential scope is resolved deterministically to current hits above.
    # Do not expose historical SOURCE-n labels to the model after those hits
    # have been remapped to the current turn's SOURCE-n namespace.
    customer_scope_instruction = (
        "The backend has restricted this request to the explicitly selected customer. "
        "Treat references such as this customer, they, their issue, and their contact as "
        "referring to that selected customer. Use only the supplied protected evidence.\n\n"
        if conversation.context_customer_id is not None
        else ""
    )
    reasoning_question = customer_scope_instruction + (
        (
            "FinBrain's deterministic conversation resolver has already selected the "
            "protected evidence supplied with this request as the user's intended referent. "
            "Answer about that selected evidence directly; do not say the referent or its "
            "ordinal is missing merely because the earlier list is not repeated. Use only the "
            "current SOURCE-n citation identifiers.\n\n"
            f"User follow-up: {sanitized_question}"
        )
        if referential
        else f"{history}\n\nCurrent protected question: {sanitized_question}"
        if history and not explicit_entity
        else sanitized_question
    )

    scoped_profile_hits: list[RetrievalHit] = []
    scoped_profile_answer: CitedAnswer | None = None
    if (
        conversation.context_customer_id is not None
        and is_customer_profile_lookup(payload.question)
    ):
        scoped_profile_hits = list_eligible_hits(db, plan.filters)
        scoped_customer = db.get(Customer, conversation.context_customer_id)
        verified_endpoint = db.scalar(
            select(CustomerEndpoint)
            .where(
                CustomerEndpoint.tenant_id == str(principal.tenant_id),
                CustomerEndpoint.customer_id == conversation.context_customer_id,
                CustomerEndpoint.channel == "email",
                CustomerEndpoint.verification_status == "verified",
            )
            .order_by(CustomerEndpoint.verified_at.desc(), CustomerEndpoint.id.desc())
        )
        endpoint_registry = (
            db.get(ProtectedTokenRegistry, verified_endpoint.endpoint_token)
            if verified_endpoint is not None
            else None
        )
        scoped_profile_answer = structured_customer_profile_lookup(
            payload.question,
            scoped_profile_hits,
            name_token=scoped_customer.primary_name_token if scoped_customer else None,
            email_token=verified_endpoint.endpoint_token if verified_endpoint else None,
            email_mask=endpoint_registry.masked_value if endpoint_registry else None,
            reveal_email=principal.role.value == "owner_director",
        )

    hits: list[RetrievalHit]
    conversation_context_hits: list[RetrievalHit] | None = None
    if ambiguous_person_reference:
        hits = []
        cited_answer = CitedAnswer(
            answer="I’m not sure which person you mean. Please provide their name.",
            citations=[],
            insufficient_evidence=True,
        )
        reasoning_mode = "conversation-clarification"
    elif scoped_profile_answer is not None:
        hits = scoped_profile_hits
        cited_answer = scoped_profile_answer
        reasoning_mode = "structured-customer-profile"
    elif plan.intent is QueryIntent.LIST_SOURCES:
        hits = []
        cited_answer = CitedAnswer(
            answer=(
                "Available ready source systems:\n\n"
                + "\n".join(f"- {source}: {count} record(s)" for source, count in inventory)
            ),
            citations=[],
            insufficient_evidence=not inventory,
        )
        reasoning_mode = "structured-filter"
    elif plan.intent is QueryIntent.COUNT_SOURCES:
        hits = []
        cited_answer = CitedAnswer(
            answer=f"There are {len(inventory)} ready source system(s).",
            citations=[],
            insufficient_evidence=not inventory,
        )
        reasoning_mode = "structured-filter"
    elif plan.intent is QueryIntent.COUNT_RECORDS:
        if referential:
            hits = prior_hits or []
            conversation_context_hits = hits
        else:
            hits = []
            conversation_context_hits = list_eligible_hits(db, plan.filters)
        total = len(conversation_context_hits)
        scope = ", ".join(plan.source_systems) if plan.source_systems else "all source systems"
        cited_answer = CitedAnswer(
            answer=f"{scope}: {total} ready record(s).",
            citations=(
                [f"SOURCE-{index}" for index in range(1, len(hits) + 1)] if referential else []
            ),
            insufficient_evidence=total == 0,
        )
        reasoning_mode = "structured-filter"
    elif plan.intent is QueryIntent.LIST_RECORDS:
        hits = prior_hits or [] if referential else list_eligible_hits(db, plan.filters, limit=50)
        cited_answer = structured_record_listing(hits)
        reasoning_mode = "structured-filter"
    elif plan.intent in {QueryIntent.SEMANTIC, QueryIntent.LOOKUP}:
        if referential:
            hits = prior_hits or []
        elif plan.intent is QueryIntent.LOOKUP and is_contact_enumeration(payload.question):
            hits = list_eligible_hits(db, plan.filters)
        else:
            query_embedding, _embedding_mode = embed_query_cached(sanitized_question)
            hits = retrieve_hybrid_hits(
                db,
                sanitized_question,
                query_embedding,
                k=SEMANTIC_TOP_K,
                filters=plan.filters,
            )
        if plan.intent is QueryIntent.LOOKUP:
            contact_answer = structured_contact_lookup(payload.question, hits)
            if contact_answer is not None:
                cited_answer = contact_answer
                reasoning_mode = "structured-lookup"
            else:
                cited_answer, reasoning_mode = answer_all_query_with_citations(
                    reasoning_question,
                    hits,
                    response_style=(
                        "compact"
                        if ordinal_reference or deterministic_intent is QueryIntent.LOOKUP
                        else conversational_plan.response_style
                        if conversational_plan is not None
                        else "compact"
                    ),
                )
        else:
            cited_answer, reasoning_mode = answer_all_query_with_citations(reasoning_question, hits)
    else:  # QueryIntent.ANALYZE_ALL: unbounded on purpose, see SEMANTIC_TOP_K note above.
        hits = prior_hits or [] if referential else list_eligible_hits(db, plan.filters)
        cited_answer, reasoning_mode = answer_all_query_with_citations(reasoning_question, hits)
    raw_answer = cited_answer.answer
    known_tokens = set(db.scalars(select(ProtectedTokenRegistry.token)).all())
    invented = unknown_tokens(raw_answer, known_tokens)
    if invented:
        raise HTTPException(status_code=502, detail="The model returned an unknown protected token")
    cited_pairs = [
        (index, hit)
        for index, hit in enumerate(hits, 1)
        if f"SOURCE-{index}" in cited_answer.citations
    ]
    cited_hits = [hit for _index, hit in cited_pairs]
    protected_brief = (
        generate_protected_brief(
            question=sanitized_question,
            protected_answer=raw_answer,
            hits=hits,
            cited_ids=set(cited_answer.citations),
            insufficient_evidence=cited_answer.insufficient_evidence,
            reasoning_mode=reasoning_mode,
        )
        if plan.intent in {QueryIntent.SEMANTIC, QueryIntent.ANALYZE_ALL}
        and reasoning_mode
        not in {"conversation-clarification", "no-evidence", "structured-customer-profile"}
        else None
    )
    if protected_brief is not None:
        try:
            validate_protected_brief(
                protected_brief,
                allowed_citations=set(cited_answer.citations),
                protected_context=(
                    "\n".join(hit.retrieval_text for hit in hits) + f"\n{reasoning_question}"
                ),
            )
        except ValueError as error:
            # A secondary presentation artifact must not turn an already
            # validated cited answer into an HTTP 500.
            logger.warning(
                "intelligence_brief_validation_failed error_type=%s",
                type(error).__name__,
            )
            protected_brief = None
    turn = persist_turn(
        db,
        conversation,
        user_role=principal.role.value,
        protected_question=sanitized_question,
        protected_answer=raw_answer,
        protected_brief=(protected_brief.model_dump(mode="json") if protected_brief else None),
        query_intent=plan.intent.value,
        source_systems=list(plan.source_systems),
        reasoning_mode=reasoning_mode,
        insufficient_evidence=cited_answer.insufficient_evidence,
        cited_hits=(
            conversation_context_hits if conversation_context_hits is not None else cited_hits
        ),
        citation_ordinals=(
            None
            if conversation_context_hits is not None
            else [index for index, _hit in cited_pairs]
        ),
    )
    query_hash_value = hash_query(sanitized_question)
    answer_trace = detokenize_response_with_trace(
        db,
        raw_answer,
        principal.role.value,
        query_hash_value,
        actor_ref=principal.actor_ref,
        turn_ref=str(turn.id),
    )
    authorized_brief, brief_trace = authorize_brief_with_trace(
        db,
        protected_brief,
        role=principal.role.value,
        query_hash=query_hash_value,
        actor_ref=principal.actor_ref,
        turn_ref=str(turn.id),
    )
    settings = get_settings()
    reasoning_model = (
        settings.morpheus_model
        if reasoning_mode == "morpheus"
        else settings.gemini_reasoning_model
        if reasoning_mode == "gemini"
        else None
    )
    if reasoning_model is None and conversational_plan is not None:
        reasoning_model = settings.morpheus_model
    return QueryResponse(
        answer=answer_trace.text,
        model_answer=raw_answer,
        model_question=sanitized_question,
        query_intent=plan.intent.value,
        sources_used=len(hits),
        mode=reasoning_mode,
        insufficient_evidence=cited_answer.insufficient_evidence,
        citations=[
            QueryCitation(
                citation_id=f"SOURCE-{index}",
                source_record_id=hit.source_record_id,
                source_system=hit.source_system,
                record_type=hit.record_type,
                occurred_at=hit.occurred_at,
                protected_excerpt=hit.retrieval_text[:1_000],
                similarity=hit.similarity,
                freshness=citation_freshness(hit)[0],
                age_days=citation_freshness(hit)[1],
                relation=("stale" if citation_freshness(hit)[0] == "stale" else "supporting"),
            )
            for index, hit in enumerate(hits, 1)
            if f"SOURCE-{index}" in cited_answer.citations
        ],
        conversation_id=conversation.id,
        turn_id=turn.id,
        intelligence_brief=authorized_brief,
        protected_intelligence_brief=protected_brief,
        exposure_receipt=ExposureReceipt(
            request_id=query_id,
            query_hash=query_hash_value,
            reasoning_mode=reasoning_mode,
            reasoning_model=reasoning_model,
            external_ai_used=(
                conversational_plan is not None or reasoning_mode in {"morpheus", "gemini"}
            ),
            privacy_preflight_passed=True,
            recognized_sensitive_fields=len(query_entries),
            protected_question_tokens=len(set(TOKEN_PATTERN.findall(sanitized_question))),
            protected_context_tokens=len(
                {
                    *(
                        token
                        for hit in hits
                        for token in TOKEN_PATTERN.findall(hit.retrieval_text)
                    ),
                    *(
                        token
                        for turn in planning_history
                        for field in ("user", "assistant")
                        for token in TOKEN_PATTERN.findall(str(turn[field]))
                    ),
                }
            ),
            restored_tokens=(
                brief_trace.restored_tokens if brief_trace else answer_trace.restored_tokens
            ),
            withheld_tokens=(
                brief_trace.withheld_tokens if brief_trace else answer_trace.withheld_tokens
            ),
            active_role=principal.role,
            sources_supplied=len(hits),
            disclosure_session_ref=(
                brief_trace.disclosure_session_ref
                if brief_trace
                else answer_trace.disclosure_session_ref
            ),
            single_use_grants=(
                brief_trace.single_use_grants if brief_trace else answer_trace.single_use_grants
            ),
            vault_key_version=(
                db.scalar(
                    select(VaultKeyVersion.version)
                    .where(VaultKeyVersion.status == "active")
                    .limit(1)
                )
                or 1
            ),
        ),
        context_customer_id=conversation.context_customer_id,
    )
