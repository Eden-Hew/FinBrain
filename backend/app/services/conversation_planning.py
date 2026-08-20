import json
import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import get_settings
from app.security.detect import contains_known_pii
from app.services.morpheus import morpheus_chat
from app.services.query_planning import QueryIntent

logger = logging.getLogger(__name__)

PLANNER_SYSTEM_INSTRUCTION = (
    "You are FinBrain's protected conversation planner. You never answer the user. "
    "Interpret the latest protected question using only the bounded protected conversation. "
    "Tokens such as PERSON_xxxxxxxxxx are opaque identifiers and must remain unchanged. "
    "Choose referenced_turn only when the latest question clearly refers to evidence cited by "
    "that earlier turn. Prefer the most recent matching turn, but follow topic changes and named "
    "references. A reply-writing request normally refers to the immediately preceding discussed "
    "customer or issue. Set needs_clarification=true if a singular reference could identify more "
    "than one cited subject. Never infer permissions, reveal hidden values, or create source "
    "filters. Output one JSON object only, with exactly these fields: intent ('semantic' or "
    "'lookup'), referenced_turn (integer or null), response_style ('compact' or 'analysis'), "
    "needs_clarification (boolean)."
)


class ConversationalPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Literal["semantic", "lookup"]
    referenced_turn: int | None = Field(default=None, ge=1)
    response_style: Literal["compact", "analysis"]
    needs_clarification: bool

    @property
    def query_intent(self) -> QueryIntent:
        return QueryIntent(self.intent)


def _json_object(text: str) -> dict[str, object]:
    start = text.find("{")
    if start < 0:
        raise ValueError("conversation_planner_missing_json")
    value, _end = json.JSONDecoder().raw_decode(text[start:])
    if not isinstance(value, dict):
        raise ValueError("conversation_planner_invalid_json")
    return value


def plan_conversation(
    *,
    history: list[dict[str, object]],
    protected_question: str,
    current_intent: QueryIntent,
    available_sources: list[str],
) -> ConversationalPlan | None:
    """Interpret an ambiguous follow-up, returning None for a safe deterministic fallback."""
    settings = get_settings()
    if (
        not settings.conversation_planner_enabled
        or not settings.morpheus_api_key
        or not history
        or current_intent not in {QueryIntent.SEMANTIC, QueryIntent.LOOKUP}
    ):
        return None

    payload = {
        "protected_conversation": history,
        "latest_protected_question": protected_question,
        "deterministic_intent": current_intent.value,
        "available_source_systems": available_sources,
    }
    serialized_payload = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
    if contains_known_pii(serialized_payload):
        logger.warning("conversation_planner_preflight_failed")
        return None
    try:
        response = morpheus_chat(
            [
                {"role": "system", "content": PLANNER_SYSTEM_INSTRUCTION},
                {
                    "role": "user",
                    "content": serialized_payload,
                },
            ],
            temperature=0.0,
            timeout_seconds=settings.conversation_planner_timeout_seconds,
        )
        plan = ConversationalPlan.model_validate(_json_object(response))
        available_turns = {int(turn["turn"]) for turn in history}
        if plan.referenced_turn is not None and plan.referenced_turn not in available_turns:
            raise ValueError("conversation_planner_unknown_turn")
        return plan
    except Exception as error:
        # Provider text may echo protected content, so logs intentionally expose only classes.
        logger.warning(
            "conversation_planner_failed error_type=%s validation=%s",
            type(error).__name__,
            isinstance(error, (ValidationError, ValueError)),
        )
        return None
