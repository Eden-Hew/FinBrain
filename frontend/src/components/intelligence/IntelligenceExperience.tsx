import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  compareTurnRoles,
  createRecommendationFromTurn,
  fetchCitationDetail,
  type CitationDetail,
  type CustomerIntelligenceBrief,
  type ExposureReceipt,
  type QueryCitation,
  type Role,
  type RoleComparisonResponse,
} from "../../api/client";
import { PERSONAS } from "../../lib/personas";

interface Props {
  brief: CustomerIntelligenceBrief;
  citations: QueryCitation[];
  exposure: ExposureReceipt | null;
  turnId: number;
  rawQuestion: string;
  modelQuestion: string;
  protectedAnswer: string;
  authorizedAnswer: string;
  role: Role;
  onOpenApprovals: (recommendationId: number) => void;
}

interface PendingRecommendation {
  actionId: string;
  title: string;
  rationale: string;
  owner: string;
  priority: "low" | "medium" | "high";
  evidenceCount: number;
}

function CitationButtons({
  ids,
  onSelect,
}: {
  ids: string[];
  onSelect: (id: string) => void;
}) {
  if (!ids.length) return null;
  return (
    <span className="fb-intel-citations" aria-label="Supporting evidence">
      {ids.map((id) => (
        <button
          className="fb-intel-citation"
          data-citation-id={id}
          type="button"
          key={id}
          onClick={() => onSelect(id)}
          aria-label={`Open evidence ${id}`}
        >
          {id.replace("SOURCE-", "[")}]
        </button>
      ))}
    </span>
  );
}

function Overlay({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);
  return (
    <div className="fb-intel-overlay-backdrop" role="presentation" onMouseDown={onClose}>
      <aside
        className="fb-intel-overlay"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="fb-intel-overlay-head">
          <h2>{title}</h2>
          <button ref={closeRef} className="fb-btn fb-btn-outline" type="button" onClick={onClose}>
            Close
          </button>
        </div>
        {children}
      </aside>
    </div>
  );
}

function ExposureContent({
  exposure,
  rawQuestion,
  modelQuestion,
  protectedAnswer,
  authorizedAnswer,
}: {
  exposure: ExposureReceipt;
  rawQuestion: string;
  modelQuestion: string;
  protectedAnswer: string;
  authorizedAnswer: string;
}) {
  const executionPath = exposure.reasoning_mode === "structured-filter"
    ? "Deterministic protected SQL filter"
    : exposure.reasoning_mode === "offline-demo"
      ? "Offline protected analysis"
      : `${exposure.reasoning_mode} · ${exposure.reasoning_model ?? "configured model"}`;
  return (
    <div className="fb-intel-exposure">
      <div className="fb-intel-metrics">
        <div><strong>{exposure.recognized_sensitive_fields}</strong><span>recognized fields protected in the question</span></div>
        <div><strong>{exposure.protected_context_tokens}</strong><span>protected context tokens supplied</span></div>
        <div><strong>{exposure.restored_tokens}</strong><span>values restored for this role</span></div>
        <div><strong>{exposure.withheld_tokens}</strong><span>values withheld for this role</span></div>
      </div>
      <dl className="fb-intel-receipt-list">
        <div><dt>External reasoning model used</dt><dd>{exposure.external_ai_used ? "Yes" : "No"}</dd></div>
        <div><dt>Execution path</dt><dd>{executionPath}</dd></div>
        <div><dt>Recognized sensitive values sent in raw form</dt><dd>0</dd></div>
        <div><dt>Active policy</dt><dd>{PERSONAS[exposure.active_role].label}</dd></div>
        <div><dt>Sources supplied</dt><dd>{exposure.sources_supplied}</dd></div>
        <div><dt>Audit reference</dt><dd>{exposure.query_hash}</dd></div>
      </dl>
      <div className="fb-intel-text-compare">
        <section><h3>User question</h3><pre>{rawQuestion}</pre></section>
        <section><h3>Protected model question</h3><pre>{modelQuestion}</pre></section>
        <section><h3>Protected model response</h3><pre>{protectedAnswer}</pre></section>
        <section><h3>Authorized response</h3><pre>{authorizedAnswer}</pre></section>
      </div>
    </div>
  );
}

export function StandaloneExposureReceipt({
  exposure,
  rawQuestion,
  modelQuestion,
  protectedAnswer,
  authorizedAnswer,
}: {
  exposure: ExposureReceipt;
  rawQuestion: string;
  modelQuestion: string;
  protectedAnswer: string;
  authorizedAnswer: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className="fb-btn fb-btn-outline" type="button" onClick={() => setOpen(true)}>AI Exposure Receipt</button>
      {open && (
        <Overlay title="AI Exposure Receipt" onClose={() => setOpen(false)}>
          <ExposureContent exposure={exposure} rawQuestion={rawQuestion} modelQuestion={modelQuestion} protectedAnswer={protectedAnswer} authorizedAnswer={authorizedAnswer} />
        </Overlay>
      )}
    </>
  );
}

export function IntelligenceExperience({
  brief,
  citations,
  exposure,
  turnId,
  rawQuestion,
  modelQuestion,
  protectedAnswer,
  authorizedAnswer,
  role,
  onOpenApprovals,
}: Props) {
  const [selectedCitation, setSelectedCitation] = useState<string | null>(null);
  const [citationDetail, setCitationDetail] = useState<CitationDetail | null>(null);
  const [citationError, setCitationError] = useState("");
  const [citationLoading, setCitationLoading] = useState(false);
  const [showExposure, setShowExposure] = useState(false);
  const [showComparison, setShowComparison] = useState(false);
  const [comparison, setComparison] = useState<RoleComparisonResponse | null>(null);
  const [comparisonError, setComparisonError] = useState("");
  const [comparisonLoading, setComparisonLoading] = useState(false);
  const [selectedComparisonRole, setSelectedComparisonRole] = useState<Role>("general_employee");
  const [recommendationState, setRecommendationState] = useState<
    "idle" | "creating" | "created" | "failed"
  >("idle");
  const [recommendationError, setRecommendationError] = useState("");
  const [pendingRecommendation, setPendingRecommendation] = useState<PendingRecommendation | null>(null);
  const [createdRecommendationId, setCreatedRecommendationId] = useState<number | null>(null);

  const openCitation = async (citationId: string) => {
    setSelectedCitation(citationId);
    setCitationDetail(null);
    setCitationError("");
    setCitationLoading(true);
    try {
      setCitationDetail(await fetchCitationDetail(turnId, citationId));
    } catch (error) {
      setCitationError(error instanceof Error ? error.message : "Evidence is unavailable.");
    } finally {
      setCitationLoading(false);
    }
  };

  const closeCitation = () => {
    const citationId = selectedCitation;
    setSelectedCitation(null);
    requestAnimationFrame(() => {
      if (citationId) {
        document.querySelector<HTMLButtonElement>(`[data-citation-id="${citationId}"]`)?.focus();
      }
    });
  };

  const runComparison = async () => {
    setShowComparison(true);
    setComparison(null);
    setComparisonError("");
    setComparisonLoading(true);
    try {
      setComparison(await compareTurnRoles(
        turnId,
        ["general_employee", "finance_ops", "owner_director"],
      ));
    } catch (error) {
      setComparisonError(error instanceof Error ? error.message : "Policy comparison failed.");
    } finally {
      setComparisonLoading(false);
    }
  };

  const createRecommendation = async () => {
    if (!pendingRecommendation) return;
    setRecommendationState("creating");
    setRecommendationError("");
    try {
      const created = await createRecommendationFromTurn(
        turnId,
        pendingRecommendation.actionId,
        pendingRecommendation.owner,
      );
      setCreatedRecommendationId(created.id);
      setRecommendationState("created");
      setPendingRecommendation(null);
    } catch (error) {
      setRecommendationError(error instanceof Error ? error.message : "Recommendation creation failed.");
      setRecommendationState("failed");
    }
  };

  const statusLabel = {
    healthy: "Healthy",
    needs_attention: "Needs attention",
    at_risk: "At risk",
    insufficient_evidence: "Insufficient evidence",
  }[brief.status];
  const mayCreateRecommendation = role === "finance_ops" || role === "owner_director";

  const requestRecommendation = (item: PendingRecommendation) => {
    setRecommendationError("");
    setPendingRecommendation(item);
  };

  return (
    <article className="fb-intel-brief">
      {exposure?.reasoning_mode === "offline-demo" && (
        <div className="fb-intel-mode-note" role="status">Offline protected analysis</div>
      )}
      <header className="fb-intel-brief-head">
        <div>
          <h2>{brief.subject_label}</h2>
          <p>{brief.executive_summary}</p>
        </div>
        <span className={`fb-intel-status is-${brief.status}`}>{statusLabel}</span>
      </header>

      {!!brief.claims.length && (
        <section className="fb-intel-section">
          <h3>What the evidence says</h3>
          <div className="fb-intel-claim-list">
            {brief.claims.map((claim) => (
              <div className="fb-intel-claim" key={claim.id}>
                <span className={`fb-intel-relation is-${claim.relation}`}>{claim.relation}</span>
                <p>{claim.statement}</p>
                <CitationButtons ids={claim.citation_ids} onSelect={openCitation} />
              </div>
            ))}
          </div>
        </section>
      )}

      {!!brief.timeline.length && (
        <section className="fb-intel-section">
          <h3>Recent sequence</h3>
          <ol className="fb-intel-timeline">
            {brief.timeline.map((event, index) => (
              <li key={`${event.label}-${index}`}>
                <time>{event.occurred_at ? new Date(event.occurred_at).toLocaleDateString() : "Undated"}</time>
                <strong>{event.label}</strong>
                <p>{event.detail}</p>
                <CitationButtons ids={event.citation_ids} onSelect={openCitation} />
              </li>
            ))}
          </ol>
        </section>
      )}

      {!!brief.missing_information.length && (
        <section className="fb-intel-section fb-intel-missing">
          <h3>Information that still needs verification</h3>
          {brief.missing_information.map((claim) => (
            <div className="fb-intel-missing-row" key={`missing-${claim.id}`}>
              <p>{claim.statement} <CitationButtons ids={claim.citation_ids} onSelect={openCitation} /></p>
              {mayCreateRecommendation && (
                <button
                  className="fb-btn fb-btn-outline"
                  type="button"
                  onClick={() => requestRecommendation({
                    actionId: `verification-gap:${claim.id}`,
                    title: "Create verification action",
                    rationale: claim.statement,
                    owner: "Finance Operations",
                    priority: "medium",
                    evidenceCount: claim.citation_ids.length,
                  })}
                >
                  Create verification action
                </button>
              )}
            </div>
          ))}
        </section>
      )}

      {brief.recommended_action && (
        <section className="fb-intel-action">
          <div>
            <h3>{brief.recommended_action.title}</h3>
            <p>{brief.recommended_action.rationale}</p>
            <span>Suggested owner: {brief.recommended_action.suggested_owner}</span>
          </div>
          <div className="fb-intel-action-controls">
            {mayCreateRecommendation && recommendationState !== "created" && (
              <button
                className="fb-btn fb-btn-solid"
                type="button"
                disabled={recommendationState === "creating"}
                onClick={() => requestRecommendation({
                  actionId: brief.recommended_action?.id ?? "recommended-action",
                  title: brief.recommended_action?.title ?? "Recommended action",
                  rationale: brief.recommended_action?.rationale ?? "",
                  owner: brief.recommended_action?.suggested_owner ?? "Finance Operations",
                  priority: brief.recommended_action?.priority ?? "medium",
                  evidenceCount: brief.recommended_action?.citation_ids.length ?? 0,
                })}
              >
                {recommendationState === "creating" ? "Creating proposal…" : "Send for approval"}
              </button>
            )}
            {recommendationState === "created" && (
              <button className="fb-btn fb-btn-solid" type="button" onClick={() => createdRecommendationId && onOpenApprovals(createdRecommendationId)}>
                Open approval
              </button>
            )}
            {recommendationError && <span className="fb-intel-error">{recommendationError}</span>}
          </div>
        </section>
      )}

      <footer className="fb-intel-trustbar">
        <button type="button" onClick={() => setShowExposure(true)}>AI Exposure Receipt</button>
        <button type="button" onClick={() => openCitation(citations[0]?.citation_id)} disabled={!citations.length}>
          Inspect {citations.length} cited source{citations.length === 1 ? "" : "s"}
        </button>
        {role === "compliance" && (
          <button type="button" onClick={runComparison}>Compare policies</button>
        )}
      </footer>

      {selectedCitation && (
        <Overlay title={`Evidence ${selectedCitation}`} onClose={closeCitation}>
          <div className="fb-intel-evidence-picker" aria-label="Cited evidence">
            {citations.map((citation) => (
              <button
                className={citation.citation_id === selectedCitation ? "is-current" : ""}
                type="button"
                key={citation.citation_id}
                onClick={() => openCitation(citation.citation_id)}
              >
                {citation.citation_id} · {citation.source_system}
              </button>
            ))}
          </div>
          {citationLoading && <p className="fb-intel-muted">Authorizing protected evidence…</p>}
          {citationError && <p className="fb-intel-error">{citationError}</p>}
          {citationDetail && (
            <div className="fb-intel-evidence-detail">
              <div className="fb-intel-meta-row">
                <span>{citationDetail.citation.source_system}</span>
                <span>{citationDetail.citation.record_type ?? "record"}</span>
                <span>{citationDetail.citation.freshness}</span>
                <span>{citationDetail.citation.age_days == null ? "Date unavailable" : `${citationDetail.citation.age_days} days old`}</span>
              </div>
              <h3>Protected source</h3>
              <pre>{citationDetail.citation.protected_excerpt}</pre>
              <h3>Your permitted view</h3>
              <p>{citationDetail.authorized_excerpt}</p>
              <div className="fb-intel-policy-note">
                {citationDetail.access_explanation} Restored: {citationDetail.restored_tokens}. Withheld: {citationDetail.withheld_tokens}.
              </div>
            </div>
          )}
        </Overlay>
      )}

      {showExposure && (
        <Overlay title="AI Exposure Receipt" onClose={() => setShowExposure(false)}>
          {exposure ? (
            <ExposureContent exposure={exposure} rawQuestion={rawQuestion} modelQuestion={modelQuestion} protectedAnswer={protectedAnswer} authorizedAnswer={authorizedAnswer} />
          ) : (
            <p className="fb-intel-muted">A verified exposure receipt is unavailable for this response.</p>
          )}
        </Overlay>
      )}

      {showComparison && (
        <Overlay title="Role Policy Comparison" onClose={() => setShowComparison(false)}>
          <p className="fb-intel-muted">One protected answer, disclosed through three policies. No additional AI call is made.</p>
          {comparisonLoading && <p>Applying role policies…</p>}
          {comparisonError && <p className="fb-intel-error">{comparisonError}</p>}
          {comparison && (
            <>
              <label className="fb-intel-role-select">
                Policy view
                <select value={selectedComparisonRole} onChange={(event) => setSelectedComparisonRole(event.target.value as Role)}>
                  {comparison.results.map((result) => <option key={result.role} value={result.role}>{PERSONAS[result.role].label}</option>)}
                </select>
              </label>
              <div className="fb-intel-role-grid" data-selected-role={selectedComparisonRole}>
              {comparison.results.map((result) => (
                <section key={result.role} data-role={result.role}>
                  <h3>{PERSONAS[result.role].label}</h3>
                  <p>{result.answer}</p>
                  <div className="fb-intel-policy-note">Restored {result.restored_tokens} · Withheld {result.withheld_tokens}</div>
                  {result.policy_explanations.map((explanation) => <small key={explanation}>{explanation}</small>)}
                </section>
              ))}
              </div>
            </>
          )}
        </Overlay>
      )}

      {pendingRecommendation && (
        <Overlay title="Send recommendation for approval?" onClose={() => recommendationState !== "creating" && setPendingRecommendation(null)}>
          <div className="fb-intel-confirmation">
            <h3>{pendingRecommendation.title}</h3>
            <p>{pendingRecommendation.rationale}</p>
            <dl className="fb-intel-receipt-list">
              <div><dt>Suggested owner</dt><dd>{pendingRecommendation.owner}</dd></div>
              <div><dt>Priority</dt><dd>{pendingRecommendation.priority}</dd></div>
              <div><dt>Protected evidence</dt><dd>{pendingRecommendation.evidenceCount} cited source{pendingRecommendation.evidenceCount === 1 ? "" : "s"}</dd></div>
            </dl>
            {recommendationError && <p className="fb-intel-error">{recommendationError}</p>}
            <div className="fb-intel-confirm-actions">
              <button className="fb-btn fb-btn-solid" type="button" disabled={recommendationState === "creating"} onClick={createRecommendation}>
                {recommendationState === "creating" ? "Creating proposal…" : "Confirm and send"}
              </button>
              <button className="fb-btn fb-btn-outline" type="button" disabled={recommendationState === "creating"} onClick={() => setPendingRecommendation(null)}>Cancel</button>
            </div>
          </div>
        </Overlay>
      )}
    </article>
  );
}
