# FinBrain Five-Feature Implementation Plan

## 1. Objective

Implement five connected features that turn FinBrain's existing protected query system into a
clear industrial customer-intelligence workflow:

1. Customer Intelligence Brief
2. Clickable Evidence Drawer
3. AI Exposure Receipt
4. Role Comparison View
5. Recommendation-to-Approval Workflow

The finished demonstration must tell one continuous story:

```text
Scattered protected records
  -> evidence-backed customer brief
  -> inspectable sources
  -> proof of what external AI received
  -> permission-policy comparison
  -> controlled recommendation
  -> human decision
  -> verifiable audit event
```

This plan targets a reliable hackathon proof of concept deliverable in six working days. It does
not attempt to deliver production authentication, arbitrary customer-health modeling, or external
email execution.

## 2. Current Baseline

The current repository already provides most of the difficult platform boundaries:

- Canonical protected ingestion across email, Telegram, file upload, structured CSV, manual data,
  and demonstration sources.
- Query-side sensitive-data detection and tokenization.
- Protected Morpheus/Gemini reasoning with validated `SOURCE-n` citations.
- SQL-first counts, listings, and deterministic business filters.
- Protected six-turn conversation context and citation-aware follow-ups.
- Role-gated detokenization with disclosure auditing.
- Four aligned demonstration personas.
- Persistent evidence-backed process recommendations.
- Recommendation approval, rejection, and implementation transitions.
- Separate disclosure and workflow audit chains.
- React screens for chat, approvals, ingestion, finance, and audit.
- Ninety passing backend tests and a successful frontend production build.

The implementation should extend these capabilities rather than create parallel sample-only
systems.

## 3. Product and Security Principles

The following rules apply across all five features:

1. Raw input, detokenized answers, and authorized evidence excerpts must not be persisted in
   conversation tables.
2. External AI providers receive only protected questions and protected source content.
3. Structured model output must be validated for citations, protected tokens, and recognizable
   residual PII before detokenization.
4. Every role-specific disclosure is decided by the backend and written to the disclosure audit
   chain.
5. Frontend persona controls are a demonstration interface, not an authorization boundary.
6. Role comparison must not expose a privileged answer to an ordinary role. It is a
   compliance-only policy-simulation operation.
7. Recommendations must retain the exact protected evidence used to create them.
8. Human approval remains mandatory before any recommendation is treated as implemented.
9. The UI must clearly distinguish live backend output from scripted fallback data.
10. Unsupported or insufficient evidence must be shown explicitly rather than filled with an AI
    guess.

## 4. Target Demonstration Scenario

Use one stable cross-source scenario. The current approval-delay dataset may be used instead of
introducing a new Acme Retail dataset if schedule risk is high.

Primary question:

> Why are customer payment approvals being delayed, and what should we do next?

Expected journey:

1. FinBrain produces a structured brief covering repeated delays, missing owners, affected source
   systems, and a recommended process change.
2. The user opens citations from email, Telegram, spreadsheet, CRM, and meeting records.
3. The user opens the AI Exposure Receipt and sees the protected question and answer.
4. A compliance reviewer compares General Employee and Finance Operator disclosure policies.
5. A Finance Operator sends the recommendation for approval.
6. A Business Owner approves it.
7. A Compliance Reviewer verifies the resulting workflow and disclosure audit events.

## 5. Shared Architecture

### 5.1 Query response extension

Extend the existing `QueryResponse` rather than replacing it. Existing plain chat responses must
continue to work.

Proposed additions:

```python
class IntelligenceStatus(StrEnum):
    HEALTHY = "healthy"
    NEEDS_ATTENTION = "needs_attention"
    AT_RISK = "at_risk"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class IntelligenceClaim(BaseModel):
    id: str
    statement: str
    citation_ids: list[str]
    relation: str  # supporting, contradicting, stale, missing


class IntelligenceTimelineEvent(BaseModel):
    occurred_at: datetime | None
    label: str
    detail: str
    citation_ids: list[str]


class IntelligenceAction(BaseModel):
    title: str
    rationale: str
    suggested_owner: str
    priority: str
    citation_ids: list[str]


class CustomerIntelligenceBrief(BaseModel):
    subject_label: str
    status: IntelligenceStatus
    executive_summary: str
    claims: list[IntelligenceClaim]
    timeline: list[IntelligenceTimelineEvent]
    open_commitments: list[IntelligenceClaim]
    risks: list[IntelligenceClaim]
    missing_information: list[IntelligenceClaim]
    recommended_action: IntelligenceAction | None


class ExposureReceipt(BaseModel):
    request_id: str
    query_hash: str
    reasoning_mode: str
    reasoning_model: str | None
    external_ai_used: bool
    privacy_preflight_passed: bool
    recognized_sensitive_fields: int
    protected_question_tokens: int
    protected_context_tokens: int
    restored_tokens: int
    withheld_tokens: int
    active_role: UserRole
    sources_supplied: int
```

Add optional fields to `QueryResponse`:

```python
protected_intelligence_brief: CustomerIntelligenceBrief | None
intelligence_brief: CustomerIntelligenceBrief | None
exposure_receipt: ExposureReceipt
```

The protected brief is safe to persist or pass to external services. The authorized brief is
returned to the user but must never be stored in the conversation database.

### 5.2 Detokenization trace

The current detokenization service returns only text. Introduce a trace-returning internal API:

```python
class DetokenizationTrace(BaseModel):
    text: str
    restored_tokens: int
    withheld_tokens: int
    decisions: list[DisclosureDecision]
```

Keep the existing text-returning function as a compatibility wrapper. Query, comparison, and
evidence endpoints should use the traced version.

The trace must never include decrypted values in logs or persisted event payloads.

### 5.3 Frontend information architecture

Rename the primary workspace label from **AI Agents** to **Customer Intelligence**. Keep the route
and screen identifier unchanged during the hackathon to avoid unnecessary navigation refactoring.

The main result composition should be:

```text
Question and context

Customer Intelligence Brief
  - status and summary
  - claims and timeline
  - risks and missing information
  - recommended action

Trust controls
  - Evidence
  - AI Exposure Receipt
  - Compare policies (compliance only)

Action
  - Send recommendation for approval
```

Plain chat bubbles remain for greetings, short exact counts, errors, and unsupported questions.

## 6. Feature 1: Customer Intelligence Brief

### 6.1 User outcome

A user should understand the situation, evidence quality, and proposed next action within ten
seconds without reading a long chat response.

### 6.2 Backend implementation

Create:

```text
backend/app/services/intelligence.py
backend/tests/test_intelligence.py
```

Extend:

```text
backend/app/schemas.py
backend/app/routes/query.py
backend/app/services/reasoning.py
backend/tests/test_cited_retrieval.py
backend/tests/test_query_planning.py
```

Implementation flow:

1. Run the existing query planner and protected evidence selection.
2. Detect whether the request is eligible for an intelligence brief. Initial eligible intents:
   - cross-source summary;
   - customer/account risk;
   - recurring approval delay;
   - unresolved action or commitment;
   - process-recommendation question.
3. Build the existing cited protected context.
4. Ask the reasoning provider for a protected `CustomerIntelligenceBrief` JSON response.
5. Validate the response:
   - all citation IDs exist in the current evidence set;
   - each factual claim has a citation or uses relation `missing`;
   - no unknown protected token is present;
   - no recognizable PII remains;
   - status is an allowed enum;
   - maximum five claims, five timeline events, three risks, and three missing-information items;
   - recommended-action citations are a subset of the allowed citations.
6. Serialize the protected brief and perform one traced role-gated detokenization pass.
7. Parse the authorized JSON back into the same schema.
8. Return both protected and authorized brief objects.

Do not calculate a mysterious numeric risk score. Derive the categorical status from visible
signals:

- `at_risk`: a high-priority unresolved issue, repeated escalation, overdue obligation, or missing
  owner with supporting evidence;
- `needs_attention`: an action-required record without a high-priority or repeated signal;
- `healthy`: explicit recent positive evidence and no unresolved action;
- `insufficient_evidence`: the evidence set cannot support a status.

For offline mode, add a deterministic builder based on `structured_summary`, safe metadata, and
the current citations. It should produce a usable brief for the judging dataset without fabricating
customer facts.

### 6.3 Frontend implementation

Create:

```text
frontend/src/components/intelligence/CustomerIntelligenceBrief.tsx
frontend/src/components/intelligence/IntelligenceStatus.tsx
frontend/src/components/intelligence/ClaimList.tsx
frontend/src/components/intelligence/CustomerTimeline.tsx
frontend/src/components/intelligence/MissingInformation.tsx
frontend/src/components/intelligence/RecommendedAction.tsx
```

Extend:

```text
frontend/src/api/client.ts
frontend/src/screens/Agents.tsx
frontend/src/styles.css
frontend/src/lib/i18n.tsx
```

Interaction requirements:

- Render the brief as the primary response artifact, not inside a narrow speech bubble.
- The status label must always include text; do not rely on color alone.
- Each claim citation opens Feature 2's evidence drawer.
- Recommended action remains visibly connected to its supporting claims.
- Missing information uses neutral warning treatment and a **Create verification action** affordance.
- Exact-count and simple listing questions may continue using the compact chat result.

### 6.4 States

- Loading: show the brief skeleton and `Building protected brief...`.
- Success: show the full brief.
- Insufficient evidence: explain what source or fact is missing.
- Partial evidence: show available claims and a visible limitation notice.
- Backend unavailable: show `Sample response — backend unavailable`; never silently substitute.
- Provider fallback: label `Offline protected analysis` without presenting it as live Morpheus.
- Long content: clamp lists to the documented limits and place overflow behind **Show all**.

### 6.5 Tests

Backend:

- Valid brief accepts only current citations.
- Unknown citation is rejected.
- Unknown protected token is rejected.
- Residual PII is rejected.
- Unsupported status is rejected.
- Every factual claim requires evidence.
- Deterministic offline brief contains no fabricated values.
- Authorized brief is not written to conversation storage.

Frontend:

- Brief renders all defined sections.
- Missing sections do not leave empty containers.
- Citation selection opens the correct evidence item.
- Insufficient-evidence and backend-fallback states are distinguishable.

### 6.6 Definition of done

The flagship judging question returns a brief with status, summary, at least three cited claims, a
timeline or open commitment, a missing-information item, and one recommended action.

## 7. Feature 2: Clickable Evidence Drawer

### 7.1 User outcome

The user can verify a claim without leaving the intelligence brief and can see whether the source
is current, conflicting, protected, or unavailable.

### 7.2 Backend implementation

Extend `QueryCitation` with safe server-derived metadata:

```python
freshness: str  # current, aging, stale, undated
age_days: int | None
relation: str  # supporting, contradicting, stale, missing
```

Do not return a role-authorized citation excerpt for every result automatically. That would create
unnecessary disclosures. Add a lazy endpoint:

```text
GET /query-turns/{turn_id}/citations/{citation_id}?role={role}
```

Response:

```python
class CitationDetailResponse(BaseModel):
    citation: QueryCitation
    protected_excerpt: str
    authorized_excerpt: str
    restored_tokens: int
    withheld_tokens: int
    access_explanation: str
    query_hash: str
```

Endpoint rules:

1. Load the citation through `conversation_turn_citations`; do not accept arbitrary record IDs.
2. Re-evaluate the supplied role.
3. Detokenize only the selected excerpt.
4. Audit all allow and deny decisions.
5. Return a human-readable access explanation based on the decision trace.
6. Return 404 for a citation not attached to the turn.
7. Return 410 for expired or deleted conversations.

Freshness rules for the prototype:

- `current`: 0–30 days old;
- `aging`: 31–90 days old;
- `stale`: more than 90 days old;
- `undated`: no reliable occurrence date.

These thresholds must be constants and clearly described as product defaults, not regulatory
rules.

### 7.3 Frontend implementation

Create:

```text
frontend/src/components/intelligence/EvidenceDrawer.tsx
frontend/src/components/intelligence/EvidenceList.tsx
frontend/src/components/intelligence/EvidenceBadge.tsx
frontend/src/components/intelligence/SourceIdentity.tsx
```

Behavior:

- Citation markers are real buttons with accessible names such as `Open evidence SOURCE-2`.
- Opening the drawer fetches the authorized excerpt lazily.
- The drawer shows source, record type, date, freshness, relationship, protected excerpt, and
  authorized excerpt.
- The protected excerpt is the default visual focus; authorized details appear under a labeled
  `Your permitted view` section.
- Selecting another citation updates the drawer without closing it.
- Escape and the close button dismiss the drawer and restore focus to the triggering citation.
- On narrow screens, the drawer becomes a full-width bottom sheet.

### 7.4 States

- Loading excerpt.
- Authorized excerpt available.
- Some values withheld.
- Entire citation unavailable to the current role.
- Undated or stale evidence.
- Citation no longer available because conversation expired.
- Backend error with protected metadata still visible.

### 7.5 Tests

- A turn cannot access another turn's citation.
- Citation detail rechecks role permissions.
- Opening evidence creates the expected disclosure audit entries.
- Protected and authorized excerpts never cross their UI labels.
- Drawer focus behavior and keyboard dismissal work.
- Stale and undated states render with text, not color only.

### 7.6 Definition of done

Every major claim in the flagship brief opens the correct cited source, with a protected excerpt,
an authorized view, freshness, and an access explanation.

## 8. Feature 3: AI Exposure Receipt

### 8.1 User outcome

The user can verify which recognized sensitive values were protected, which model path ran, and
what was restored or withheld for the selected role.

### 8.2 Backend implementation

Generate the receipt inside `/query` using facts already produced during processing:

- `request_id`: existing opaque query UUID;
- `query_hash`: existing HMAC query reference;
- `reasoning_mode`: current mode;
- `reasoning_model`: configured model for Morpheus or Gemini;
- `external_ai_used`: false for structured filters and offline mode;
- `privacy_preflight_passed`: true only after the protected question and context pass residual-PII
  validation;
- `recognized_sensitive_fields`: number of detected query spans;
- `protected_question_tokens`: distinct protected tokens in the model question;
- `protected_context_tokens`: distinct protected tokens supplied in current evidence;
- `restored_tokens` and `withheld_tokens`: traced detokenization totals;
- `active_role`: request role;
- `sources_supplied`: number of evidence records supplied to reasoning.

Use the label **Recognized sensitive values sent in raw form: 0**, not **Raw PII sent: 0**. The
former accurately reflects the detector boundary without claiming that detection is infallible.

For structured-filter answers, the receipt must explicitly state:

```text
External reasoning model used: No
Execution path: Deterministic protected SQL filter
```

Do not store the raw question in the receipt or audit event. The frontend already holds the user's
question in local component state for the current session.

### 8.3 Frontend implementation

Create:

```text
frontend/src/components/intelligence/ExposureReceipt.tsx
frontend/src/components/intelligence/ExposureMetric.tsx
frontend/src/components/intelligence/ProtectedComparison.tsx
```

Replace the current **Show model view** button with **AI Exposure Receipt**.

Receipt sections:

1. **Protection summary** — counts, provider, role, sources, audit reference.
2. **User question** — original question held locally and never restored from storage.
3. **Model question** — `model_question` from the backend.
4. **Protected model response** — `model_answer` or protected brief.
5. **Authorized result** — the final role-specific answer or brief.

The receipt should open as a modal or wide drawer and must not mix protected and authorized text in
the same unlabeled block.

### 8.4 States

- External model used.
- Deterministic SQL path.
- Offline protected analysis.
- No sensitive fields detected.
- Detected and protected fields.
- All fields withheld.
- Receipt unavailable for a scripted sample response.

### 8.5 Tests

- Counts match the tokenization and detokenization traces.
- Receipt contains no decrypted values outside the authorized answer.
- Structured filters report no external reasoning call.
- Model/provider labels match the executed mode.
- Scripted fallback cannot display a fabricated receipt.
- Keyboard and screen-reader labels distinguish user, model, and authorized views.

### 8.6 Definition of done

The judging flow can show the original question, protected model question, protected response,
authorized response, role, provider, protected-token counts, and audit reference in one receipt.

## 9. Feature 4: Role Comparison View

### 9.1 User outcome

A compliance reviewer can simulate how one protected answer is disclosed under different policies
without rerunning reasoning or exposing privileged output to an ordinary user.

### 9.2 Security decision

Do not implement this as three client-side `/query` calls. That would:

- pay for or invoke reasoning multiple times;
- risk different source sets and nondeterministic answers;
- append misleading turns to conversation history;
- allow an ordinary persona to request a more privileged answer.

Add a compliance-restricted endpoint:

```text
POST /query-turns/{turn_id}/compare-roles
```

Request:

```json
{
  "requesting_role": "compliance",
  "comparison_roles": ["general_employee", "finance_ops", "owner_director"]
}
```

Response:

```python
class RoleComparisonResult(BaseModel):
    role: UserRole
    answer: str
    restored_tokens: int
    withheld_tokens: int
    policy_explanations: list[str]


class RoleComparisonResponse(BaseModel):
    turn_id: int
    query_hash: str
    protected_answer: str
    results: list[RoleComparisonResult]
```

Endpoint rules:

1. Only the Compliance role may call it in the current role model.
2. Load the already stored protected answer for the turn.
3. Do not call Morpheus, Gemini, embeddings, or retrieval.
4. Detokenize the same protected answer once per requested role.
5. Write distinct disclosure audit decisions with one comparison-run reference.
6. Do not modify conversation turns.
7. Return at most three allowlisted comparison roles.

The prototype must display that authentication is not implemented. Production deployment would
replace the request-supplied role with a verified session claim.

### 9.3 Frontend implementation

Create:

```text
frontend/src/components/intelligence/RoleComparison.tsx
frontend/src/components/intelligence/RoleComparisonColumn.tsx
frontend/src/components/intelligence/DisclosureSummary.tsx
```

Behavior:

- Show **Compare policies** only for the Compliance Reviewer persona.
- Keep the active user answer unchanged.
- Present comparison columns using role names and text explanations.
- Highlight exact, banded, and withheld information without relying only on color.
- Explain that the comparison reuses one protected result and does not rerun AI.
- On mobile, use an accessible role selector instead of three compressed columns.

### 9.4 States

- Compliance access available.
- Non-compliance role: control hidden and direct API call returns 403.
- No protected turn available.
- Conversation expired.
- No disclosure difference between roles.
- Partial versus full disclosure.

### 9.5 Tests

- Non-compliance requests return 403.
- The comparison endpoint does not call the reasoning service.
- Each role receives the expected amount-band behavior.
- Each disclosure creates an audit decision.
- Conversation state is unchanged.
- The frontend does not render privileged comparison content for another persona.

### 9.6 Definition of done

A Compliance Reviewer can compare one existing answer across General Employee, Finance Operator,
and Business Owner policies and then locate the resulting disclosure decisions in Audit.

## 10. Feature 5: Recommendation-to-Approval Workflow

### 10.1 User outcome

A cited intelligence recommendation can become a controlled approval item without losing its
question, evidence, ownership, or audit lineage.

### 10.2 Backend implementation

The existing recommendation engine already supports recurring-process analysis and decisions.
Add a query-originated creation path rather than a second recommendation model.

New endpoint:

```text
POST /query-turns/{turn_id}/recommendations
```

Request:

```python
class QueryRecommendationRequest(BaseModel):
    role: UserRole
    action_id: str
    suggested_owner: str | None = None
```

Rules:

1. Finance Operator and Business Owner may create a proposal.
2. Only Business Owner may approve, reject, or mark implemented.
3. Load the protected brief/action from the turn response or reproduce it from stored protected
   answer data. Never submit the authorized UI text as the source of truth.
4. Validate that every action citation belongs to the selected turn.
5. Create `RecommendationEvidence` links to the cited `TokenizedContent` rows.
6. Set recommendation status to `proposed`.
7. Write `recommendation_created_from_query` to the workflow audit chain.
8. Return the existing `RecommendationResponse` contract.

To preserve lineage, extend `process_recommendations` through a forward-only migration:

```text
origin_type           text not null default 'process_analysis'
origin_turn_id        bigint null references conversation_turns(id) on delete set null
origin_query_hash     text null
```

Allowed `origin_type` values:

```text
process_analysis
query_brief
verification_gap
```

Do not store the raw question. `origin_query_hash` is the existing HMAC reference.

### 10.3 Frontend implementation

Extend:

```text
frontend/src/components/intelligence/RecommendedAction.tsx
frontend/src/screens/Approvals.tsx
frontend/src/api/client.ts
frontend/src/lib/appState.tsx
```

Behavior:

- Show **Send for approval** when the active persona may create a proposal.
- Confirmation includes action, rationale, owner, priority, and evidence count.
- After creation, show a success state with **Open approval**.
- Navigate to Approvals and focus or highlight the created recommendation.
- The approval card shows origin, evidence, success metric, owner, and status.
- Decision comments remain optional and pass through the existing protected-comment handling.
- Approval and rejection must update the current card without a page refresh.

### 10.4 Audit accuracy requirement

The current Audit UI displays `actor_ref` or `query_hash` under a column labeled **Hash**. These are
references, not the chain-entry hashes.

Extend both audit response contracts to include:

```text
previous_hash
entry_hash
```

Update the Audit table to show `entry_hash`, and show `query_hash` or `actor_ref` under a separate
**Reference** column. This is required before claiming that the UI demonstrates a hash chain.

### 10.5 States

- User cannot create recommendation.
- Proposal being created.
- Proposal created.
- Duplicate proposal already exists.
- Proposed, approved, rejected, and implemented.
- Evidence record unavailable.
- Invalid status transition.
- Backend unavailable.

### 10.6 Tests

- Recommendation uses only citations belonging to the query turn.
- Finance may create but not decide.
- Owner may create and decide.
- General Employee and Compliance cannot create query proposals.
- Duplicate creation is idempotent.
- Protected evidence and query hash remain linked.
- Approval writes a valid workflow event.
- Audit responses expose real chain-entry hashes.
- Frontend navigates to and highlights the new approval.

### 10.7 Definition of done

A Finance Operator can send the flagship brief's action for approval, a Business Owner can approve
it, and a Compliance Reviewer can verify its real workflow-chain entry.

## 11. API Summary

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/query` | Return optional intelligence brief and exposure receipt |
| `GET` | `/query-turns/{turn_id}/citations/{citation_id}` | Lazily authorize and inspect evidence |
| `POST` | `/query-turns/{turn_id}/compare-roles` | Compliance-only policy comparison |
| `POST` | `/query-turns/{turn_id}/recommendations` | Create an approval proposal from a cited action |
| `GET` | `/audit-log` | Include disclosure chain hashes |
| `GET` | `/workflow-audit` | Include workflow chain hashes |

Do not add endpoints that return raw email, raw uploaded documents, unrestricted vault values, or
detokenized conversation history.

## 12. Database and Migration Plan

Create one forward-only migration:

```text
supabase/migrations/202608150001_query_recommendation_lineage.sql
```

Changes:

- Add `origin_type` to `process_recommendations`.
- Add nullable `origin_turn_id` foreign key.
- Add nullable `origin_query_hash`.
- Add an index on `(origin_type, origin_turn_id)`.
- Add nullable JSON/JSONB `protected_brief` to `conversation_turns`.
- Preserve forced RLS and revoked Data API access.

No new table is required for exposure receipts. They should be generated from current request
facts and existing audit records. No new table is required for role comparison; it is an audited
view over one stored protected turn.

Store the validated protected structured brief in `conversation_turns.protected_brief`. The
evidence drawer, policy comparison, and query-originated recommendation endpoints need a stable
protected artifact after the initial request finishes. Existing turns may leave the field null.
Never store the authorized brief.

## 13. Frontend Component Map

```text
Agents.tsx
  |
  +-- CustomerIntelligenceBrief
  |     +-- IntelligenceStatus
  |     +-- ClaimList
  |     +-- CustomerTimeline
  |     +-- MissingInformation
  |     +-- RecommendedAction
  |
  +-- EvidenceDrawer
  |     +-- EvidenceList
  |     +-- EvidenceBadge
  |     +-- SourceIdentity
  |
  +-- ExposureReceipt
  |     +-- ExposureMetric
  |     +-- ProtectedComparison
  |
  +-- RoleComparison
        +-- RoleComparisonColumn
        +-- DisclosureSummary

Approvals.tsx
  +-- existing ProcessRecommendation cards
  +-- query-origin badge and lineage

Audit.tsx
  +-- real previous/entry hash presentation
```

Keep components data-driven. Do not add new large blocks directly inside `Agents.tsx`, which is
already responsible for conversation and upload state.

## 14. Six-Day Delivery Plan

### Day 1: Contracts and structured brief backend

Backend:

- Add brief and receipt schemas.
- Add traced detokenization compatibility API.
- Implement protected brief generation and validation.
- Implement deterministic offline brief for the judging scenario.
- Extend `/query` response.
- Add backend tests.

Frontend:

- Add TypeScript contracts.
- Prepare the new component directory and response routing.

Exit gate:

- One API request returns a valid protected and authorized brief with citations.
- Existing query and conversation tests still pass.

### Day 2: Brief UI and Evidence Drawer

Backend:

- Add citation-detail endpoint and freshness calculation.
- Add permission and audit tests.

Frontend:

- Build the intelligence brief composition.
- Build citation buttons and responsive evidence drawer.
- Add loading, insufficient, stale, withheld, and error states.
- Replace silent fallback with an explicit sample label.

Exit gate:

- Every flagship claim opens the correct evidence.
- Keyboard focus returns correctly when the drawer closes.

### Day 3: AI Exposure Receipt

Backend:

- Populate request, token, provider, source, and disclosure counts.
- Verify structured-filter and offline paths.

Frontend:

- Build receipt metrics and protected/authorized comparison.
- Replace the current model-view toggle.
- Add precise copy for recognized sensitive-value guarantees.

Exit gate:

- The receipt truthfully describes live, structured-filter, and offline execution paths.

### Day 4: Role Comparison

Backend:

- Add compliance-only comparison endpoint.
- Reuse the stored protected answer without model calls.
- Add per-role trace and audit tests.

Frontend:

- Build desktop comparison columns and mobile role switching.
- Add compliance gating and demo-authentication disclaimer.

Exit gate:

- One protected answer produces visibly different audited views without changing conversation
  state.

### Day 5: Recommendation Integration and Audit Accuracy

Backend:

- Apply lineage migration.
- Add query-originated recommendation endpoint.
- Add idempotency and permission tests.
- Return actual audit chain hashes.

Frontend:

- Connect **Send for approval** to the endpoint.
- Navigate to and highlight the created approval.
- Correct Audit columns and hash presentation.

Exit gate:

- A brief becomes a proposal, is approved, and appears with a verifiable workflow-chain hash.

### Day 6: Integration, accessibility, and rehearsal

- Run the complete backend suite and Ruff.
- Run frontend lint and production build.
- Test desktop and mobile layouts.
- Test keyboard navigation, focus management, and reduced motion.
- Reset and seed the demonstration database.
- Rehearse the exact judging flow at least twice.
- Verify offline/scripted fallback labels.
- Record a backup demonstration.
- Freeze features by the middle of the day; use the remaining time only for blocking defects.

Exit gate:

- The complete journey runs from a clean start without manual database edits or developer tools.

## 15. Parallel Team Ownership

If three teammates are available:

### Backend and privacy owner

- Structured brief generation and validation
- Detokenization trace
- Exposure receipt data
- Evidence-detail and role-comparison endpoints
- Recommendation lineage and audit hashes

### Frontend and interaction owner

- Intelligence brief
- Evidence drawer
- Exposure receipt
- Comparison layout
- Approval navigation and responsive states

### Data, QA, and demo owner

- Stable cross-source scenario
- Expected evidence and role outcomes
- Automated route and regression tests
- Accessibility checks
- Demo reset, rehearsal, and backup recording

Changes to API contracts should be agreed and committed at the start of each day so backend and
frontend work can proceed against stable fixtures.

## 16. Verification Matrix

| Area | Required verification |
| --- | --- |
| Brief grounding | Every factual claim has current allowed citations |
| Brief privacy | No unknown tokens or recognizable residual PII |
| Authorized brief | Never persisted in conversation storage |
| Evidence | Turn-scoped lookup and lazy role authorization |
| Exposure receipt | Counts and provider path match actual execution |
| Comparison | Compliance-only and no reasoning-provider call |
| Recommendation | Evidence belongs to the originating turn |
| Approval | Backend role checks and valid status transitions |
| Audit | Real chain-entry hashes returned and displayed |
| Fallback | Scripted output visibly labeled |
| Accessibility | Keyboard, focus, labels, non-color status cues |
| Responsive UI | Desktop brief/drawer and mobile bottom-sheet behavior |
| Regression | Existing ingestion, conversation, query, and recommendation tests pass |

## 17. Scope Cuts if Schedule Slips

Cut in this order:

1. Limit Intelligence Brief generation to cross-source analysis intents and the judging scenario.
2. Use fixed freshness thresholds without tenant configuration.
3. Compare only General Employee and Finance Operator instead of three roles.
4. Defer editing recommendation fields; keep create, approve, reject, and implement.
5. Do not persist the protected brief for page reload; keep it in the active response.
6. Use a modal for Evidence and Exposure instead of separate desktop drawer variants.

Do not cut:

- Backend citation validation.
- Protected-versus-authorized separation.
- Backend role checks.
- Explicit scripted-fallback labeling.
- Recommendation evidence lineage.
- Real audit chain hashes.
- End-to-end rehearsal.

## 18. Explicit Non-Goals

- Production authentication or Supabase Auth.
- Multi-tenant isolation.
- Sending or drafting Gmail messages.
- Arbitrary AI-generated SQL.
- A trained customer-health prediction model.
- Causal claims about recommendation outcomes.
- General contradiction detection across every document type.
- Configurable enterprise policy authoring.
- Persisting raw questions or detokenized answers.

## 19. Overall Definition of Done

The five-feature package is complete when all of the following are true:

1. The flagship question produces a structured, evidence-backed intelligence brief.
2. Every important claim opens the correct protected source and role-authorized excerpt.
3. The AI Exposure Receipt accurately shows the protected model boundary and disclosure trace.
4. A Compliance Reviewer can compare policies using one protected answer and no new AI call.
5. A cited recommended action can be sent into the existing approval workflow.
6. A Business Owner can approve or reject the proposal.
7. A Compliance Reviewer can see real disclosure and workflow chain-entry hashes.
8. Scripted fallback output is never presented as a live backend result.
9. The backend test suite, Ruff, frontend lint, and frontend build pass.
10. The complete demonstration works twice from a clean seeded state within the allotted judging
    time.

At that point, FinBrain will present as a governed customer-intelligence and process-optimization
platform rather than a chat wrapper: it unifies evidence, proves the privacy boundary, simulates
permissions safely, and converts intelligence into an accountable human decision.
