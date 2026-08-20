import { useEffect, useState } from "react";
import { useI18n } from "../lib/i18n";
import { useAppState } from "../lib/appState";
import { Sidebar, AppTopBar } from "../components/Nav";
import { PersonaSelector } from "../components/PersonaSelector";
import { PERSONAS } from "../lib/personas";
import { EmptyState } from "../components/EmptyState";
import {
  analyzeProcesses,
  decideEinvoiceOutreach,
  decideRecommendation,
  fetchEinvoiceOutreachDrafts,
  fetchOutreachActions,
  fetchRecommendations,
  transitionOutreachAction,
  type EinvoiceOutreachDraft,
  type OutreachAction,
  type ProcessRecommendation,
} from "../api/client";

type CardType = "invoice" | "sop" | "action" | "recommendation" | "outreach";

const TYPE_ICON: Record<CardType, React.ReactNode> = {
  invoice: <path d="M6 2h9l3 3v17H6z M9 8h6M9 12h6M9 16h4" />,
  sop: <path d="M4 4h13a3 3 0 0 1 3 3v7a3 3 0 0 1-3 3H9l-5 3v-3a3 3 0 0 1-3-3V7a3 3 0 0 1 3-3z" />,
  action: <path d="M13 2 3 14h7l-1 8 10-12h-7z" />,
  recommendation: <path d="M9 18h6M10 22h4M12 2a6 6 0 0 0-3.6 10.8c.5.4.6 1 .6 1.6V16h6v-1.6c0-.6.1-1.2.6-1.6A6 6 0 0 0 12 2z" />,
  outreach: <path d="M22 2 11 13M22 2l-7 20-4-9-9-4 20-7z" />,
};

const TYPE_LABEL: Record<CardType, string> = {
  invoice: "Invoice approval",
  sop: "SOP",
  action: "Agent action",
  recommendation: "AI recommendation",
  outreach: "Outreach message",
};

const TYPE_SUMMARY_LABEL: Record<CardType, [string, string]> = {
  invoice: ["invoice", "invoices"],
  sop: ["SOP", "SOPs"],
  action: ["agent action", "agent actions"],
  recommendation: ["AI recommendation", "AI recommendations"],
  outreach: ["outreach message", "outreach messages"],
};

function needsAttention(text: string): boolean {
  return /overdue|past due|urgent/i.test(text);
}

function TypeBadge({ type }: { type: CardType }) {
  return (
    <div className={"fb-rec-type-badge is-type-" + type}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{TYPE_ICON[type]}</svg>
      {TYPE_LABEL[type]}
    </div>
  );
}

function ConfirmApproveButton({ label, disabled, disabledReason, onConfirm }: { label: string; disabled?: boolean; disabledReason?: string; onConfirm: () => void }) {
  const [confirming, setConfirming] = useState(false);
  if (confirming) {
    return (
      <>
        <button className="fb-btn fb-btn-solid" type="button" onClick={() => { onConfirm(); setConfirming(false); }}>Yes, {label.toLowerCase()}</button>
        <button className="fb-btn fb-btn-outline" type="button" onClick={() => setConfirming(false)}>Cancel</button>
      </>
    );
  }
  return (
    <>
      <button className="fb-btn fb-btn-solid" type="button" disabled={disabled} onClick={() => setConfirming(true)}>{label}</button>
      {disabled && disabledReason && (
        <span className="fb-disabled-hint">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="4" y="10" width="16" height="10" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></svg>
          {disabledReason}
        </span>
      )}
    </>
  );
}

export default function Approvals() {
  const { t } = useI18n();
  const {
    einvoices, approveEinvoiceById, rejectEinvoiceById,
    sops, approveSop, rejectSop,
    pendingActions, approveAction, rejectAction,
    askRole,
    focusedRecommendationId,
  } = useAppState();
  const capabilities = PERSONAS[askRole].capabilities;
  const [recommendations, setRecommendations] = useState<ProcessRecommendation[]>([]);
  const [loadingAnalysis, setLoadingAnalysis] = useState(false);
  const [recommendationError, setRecommendationError] = useState("");
  const [outreachDrafts, setOutreachDrafts] = useState<EinvoiceOutreachDraft[]>([]);
  const [customerOutreach, setCustomerOutreach] = useState<OutreachAction[]>([]);
  const [outreachError, setOutreachError] = useState("");
  const [activeFilter, setActiveFilter] = useState<CardType | null>(null);

  const refreshRecommendations = async () => {
    const rows = await fetchRecommendations();
    setRecommendations(rows);
  };

  useEffect(() => {
    let active = true;
    const initialLoad = async () => {
      try {
        if (!capabilities.viewRecommendations) {
          if (active) setRecommendations([]);
          return;
        }
        const rows = await fetchRecommendations();
        if (active) setRecommendations(rows);
      } catch {
        if (active) setRecommendations([]);
      }
    };
    void initialLoad();
    return () => { active = false; };
  }, [askRole, capabilities.viewRecommendations]);

  useEffect(() => {
    let active = true;
    const initialLoad = async () => {
      try {
        if (!capabilities.manageEinvoiceReadiness) {
          if (active) setOutreachDrafts([]);
          return;
        }
        const rows = await fetchEinvoiceOutreachDrafts();
        if (active) setOutreachDrafts(rows);
      } catch {
        if (active) setOutreachDrafts([]);
      }
    };
    void initialLoad();
    return () => { active = false; };
  }, [askRole, capabilities.manageEinvoiceReadiness]);

  useEffect(() => {
    let active = true;
    if (askRole !== "finance_ops" && askRole !== "owner_director" && askRole !== "compliance") {
      return () => { active = false; };
    }
    void fetchOutreachActions().then((rows) => {
      if (active) setCustomerOutreach(rows.filter((row) => row.status === "pending_approval"));
    }).catch(() => { if (active) setCustomerOutreach([]); });
    return () => { active = false; };
  }, [askRole]);

  useEffect(() => {
    if (focusedRecommendationId == null) return;
    const target = document.getElementById(`recommendation-${focusedRecommendationId}`);
    if (!target) return;
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    target.focus({ preventScroll: true });
  }, [focusedRecommendationId, recommendations]);

  const analyze = async () => {
    setLoadingAnalysis(true);
    setRecommendationError("");
    try {
      await analyzeProcesses();
      await refreshRecommendations();
    } catch (error) {
      setRecommendationError(error instanceof Error ? error.message : "Process analysis failed.");
    } finally {
      setLoadingAnalysis(false);
    }
  };

  const decide = async (
    id: number,
    decision: "approve" | "reject" | "mark-implemented",
  ) => {
    setRecommendationError("");
    try {
      const updated = await decideRecommendation(id, decision);
      setRecommendations((rows) => rows.map((row) => row.id === id ? updated : row));
    } catch (error) {
      setRecommendationError(error instanceof Error ? error.message : "Decision failed.");
    }
  };

  const decideOutreach = async (id: number, decision: "approve" | "reject") => {
    setOutreachError("");
    try {
      await decideEinvoiceOutreach(id, decision);
      setOutreachDrafts((rows) => rows.filter((row) => row.id !== id));
    } catch (error) {
      setOutreachError(error instanceof Error ? error.message : "Decision failed.");
    }
  };

  const decideCustomerOutreach = async (id: string, decision: "approve" | "reject") => {
    setOutreachError("");
    try {
      await transitionOutreachAction(id, decision);
      setCustomerOutreach((rows) => rows.filter((row) => row.id !== id));
    } catch (error) {
      setOutreachError(error instanceof Error ? error.message : "Outreach decision failed.");
    }
  };

  const pendingInvoices = Object.values(einvoices).filter((inv) => inv.status === "pending");
  const draftSops = sops.filter((s) => s.status === "draft");
  const activeActions = pendingActions.filter((a) => a.active);
  const visibleCustomerOutreach = askRole === "finance_ops" || askRole === "owner_director" || askRole === "compliance"
    ? customerOutreach
    : [];

  const openRecommendations = recommendations.filter((item) => (
    item.status === "proposed" || item.status === "approved"
  ));
  const isEmpty = pendingInvoices.length === 0
    && draftSops.length === 0
    && activeActions.length === 0
    && openRecommendations.length === 0
    && outreachDrafts.length === 0
    && visibleCustomerOutreach.length === 0;

  // Workflows groups by what happens next: some cards are an internal
  // decision (approve/reject a document or recommendation), others end in
  // an external message. Splitting them keeps "am I sending something to a
  // customer" visually distinct from "am I approving something internal."
  const showRec = (activeFilter === null || activeFilter === "recommendation") && openRecommendations.length > 0;
  const showInv = (activeFilter === null || activeFilter === "invoice") && pendingInvoices.length > 0;
  const showSop = (activeFilter === null || activeFilter === "sop") && draftSops.length > 0;
  const showAction = (activeFilter === null || activeFilter === "action") && activeActions.length > 0;
  const showOutreach = (activeFilter === null || activeFilter === "outreach") && outreachDrafts.length > 0;
  const showDecisionSection = showRec || showInv || showSop;
  const showSendSection = showAction || showOutreach;

  const summary: { type: CardType; tone: string; count: number }[] = [
    { type: "invoice" as const, tone: "is-blue", count: pendingInvoices.length },
    { type: "sop" as const, tone: "is-purple", count: draftSops.length },
    { type: "action" as const, tone: "is-orange", count: activeActions.length },
    { type: "recommendation" as const, tone: "is-green", count: openRecommendations.length },
    { type: "outreach" as const, tone: "is-teal", count: outreachDrafts.length + visibleCustomerOutreach.length },
  ].filter((item) => item.count > 0);

  return (
    <div className="fb-root fb-shell">
      <Sidebar current="approvals" />
      <AppTopBar current="approvals" />

      <header className="fb-app-header">
        <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap" }}>
          <div>
            <h1>{t("approvals.title")}</h1>
            <p>{t("approvals.desc")}</p>
          </div>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: ".5rem" }}>
            <button
              className="fb-btn fb-btn-outline"
              type="button"
              onClick={analyze}
              disabled={loadingAnalysis || !capabilities.analyzeProcesses}
            >
              {loadingAnalysis ? "Analyzing protected records…" : "Analyze recurring problems"}
            </button>
            {!capabilities.analyzeProcesses && (
              <span className="fb-disabled-hint" style={{ alignSelf: "flex-end" }}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="4" y="10" width="16" height="10" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></svg>
                Owner / director role required
              </span>
            )}
          </div>
        </div>
      </header>

      {summary.length > 0 && (
        <div className={"fb-approvals-summary" + (activeFilter ? " has-filter" : "")}>
          {summary.map((item) => (
            <button
              className={"fb-count-chip " + item.tone + (activeFilter === item.type ? " is-active" : "")}
              type="button"
              key={item.type}
              aria-pressed={activeFilter === item.type}
              onClick={() => setActiveFilter((f) => (f === item.type ? null : item.type))}
            >
              {item.count} {item.count === 1 ? TYPE_SUMMARY_LABEL[item.type][0] : TYPE_SUMMARY_LABEL[item.type][1]}
            </button>
          ))}
          {activeFilter && (
            <button className="fb-link-toggle" type="button" onClick={() => setActiveFilter(null)}>
              Showing {TYPE_SUMMARY_LABEL[activeFilter][1]} only — clear filter
            </button>
          )}
        </div>
      )}

      <div className="fb-page-body">
        <PersonaSelector compact />
        {!capabilities.viewRecommendations && (
          <div className="fb-callout">This persona cannot view process recommendations.</div>
        )}
        {recommendationError && <div className="fb-callout" role="alert">{recommendationError}</div>}
        {outreachError && <div className="fb-callout" role="alert">{outreachError}</div>}
        <div className="fb-card-list">
          {isEmpty && (
            <EmptyState
              icon={<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5" /></svg>}
              title="You're fully caught up"
              description="Nothing waiting on your review right now."
            />
          )}

          {showDecisionSection && <div className="fb-eyebrow" style={{ margin: "0 0 .6rem" }}>Needs your decision</div>}

          {showRec && openRecommendations.map((item) => (
            <article
              id={`recommendation-${item.id}`}
              className={`fb-rec-card is-type-recommendation${focusedRecommendationId === item.id ? " is-focused" : ""}`}
              key={`process-${item.id}`}
              tabIndex={-1}
            >
              <TypeBadge type="recommendation" />
              <div className="fb-eyebrow" style={{ marginBottom: ".4rem" }}>
                {item.origin_type === "query_brief" ? "Customer intelligence" : item.origin_type === "verification_gap" ? "Verification action" : "Process optimization"}
                {" · "}{item.priority} priority · {Math.round(item.confidence * 100)}% confidence
              </div>
              <h3>{item.title}</h3>
              <p>{item.problem_statement}</p>
              <div className="fb-rec-evidence">
                <strong>Recommended change:</strong> {item.recommendation}
                <br /><strong>Success metric:</strong> {item.success_metric}
                <br /><strong>Owner:</strong> {item.suggested_owner}
                <br /><strong>Evidence:</strong> {item.record_count} protected records across {item.source_systems.join(", ")}
                {item.origin_query_hash && <><br /><strong>Origin reference:</strong> {item.origin_query_hash}</>}
              </div>
              <details style={{ marginTop: ".8rem" }}>
                <summary className="fb-link">Inspect protected evidence</summary>
                <div style={{ display: "grid", gap: ".5rem", marginTop: ".6rem" }}>
                  {item.evidence.map((evidence) => (
                    <div className="fb-rec-evidence" key={`${item.id}-${evidence.citation_id}`}>
                      <strong>{evidence.citation_id}</strong> · {evidence.source_system} · {evidence.record_type ?? "record"}
                      <div style={{ marginTop: ".3rem" }}>{evidence.evidence_excerpt}</div>
                    </div>
                  ))}
                </div>
              </details>
              <div style={{ display: "flex", gap: ".6rem", flexWrap: "wrap", alignItems: "center", marginTop: ".8rem" }}>
                {item.status === "proposed" ? (
                  <>
                    <button className="fb-btn fb-btn-solid" type="button" disabled={!capabilities.decideRecommendations} onClick={() => decide(item.id, "approve")}>Approve recommendation</button>
                    <button className="fb-btn fb-btn-outline" type="button" disabled={!capabilities.decideRecommendations} onClick={() => decide(item.id, "reject")}>Reject</button>
                    {!capabilities.decideRecommendations && (
                      <span className="fb-disabled-hint">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="4" y="10" width="16" height="10" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></svg>
                        Owner / director role required
                      </span>
                    )}
                  </>
                ) : (
                  <button className="fb-btn fb-btn-solid" type="button" disabled={!capabilities.decideRecommendations} title="Owner / director persona required" onClick={() => decide(item.id, "mark-implemented")}>Mark implemented</button>
                )}
              </div>
            </article>
          ))}

          {showInv && pendingInvoices.map((inv) => (
            <div className="fb-rec-card is-type-invoice" key={inv.id}>
              <TypeBadge type="invoice" />
              {needsAttention(inv.description) && (
                <span className="fb-status-pill is-review" style={{ marginBottom: ".5rem" }}>
                  <span className="fb-status-dot"></span>Needs attention
                </span>
              )}
              <div className="fb-eyebrow" style={{ marginBottom: ".2rem" }}>{inv.date}</div>
              <h3>{inv.supplier} — {inv.amount}</h3>
              <div className="fb-rec-evidence">{inv.description}</div>
              <div style={{ display: "flex", gap: ".6rem", flexWrap: "wrap", alignItems: "center", marginTop: ".8rem" }}>
                <ConfirmApproveButton label="Approve & submit" onConfirm={() => approveEinvoiceById(inv.id)} />
                <button className="fb-btn fb-btn-outline" type="button" onClick={() => rejectEinvoiceById(inv.id)}>Send back</button>
              </div>
            </div>
          ))}

          {showSop && draftSops.map((sop) => (
            <div className="fb-rec-card is-type-sop" key={sop.id}>
              <TypeBadge type="sop" />
              <h3>{sop.title}</h3>
              <div className="fb-rec-evidence">Owner: {sop.owner} · v{sop.version}</div>
              <div style={{ display: "flex", gap: ".6rem", flexWrap: "wrap", marginTop: ".8rem" }}>
                <button className="fb-btn fb-btn-solid" type="button" onClick={() => approveSop(sop.id)}>Approve SOP</button>
                <button className="fb-btn fb-btn-outline" type="button" onClick={() => rejectSop(sop.id)}>Discard draft</button>
              </div>
            </div>
          ))}

          {showSendSection && <div className="fb-eyebrow" style={{ margin: showDecisionSection ? "1.6rem 0 .6rem" : "0 0 .6rem" }}>Ready to send</div>}

          {showAction && activeActions.map((act) => (
            <div className="fb-rec-card is-type-action" key={act.id}>
              <TypeBadge type="action" />
              {needsAttention(act.detail) && (
                <span className="fb-status-pill is-review" style={{ marginBottom: ".5rem" }}>
                  <span className="fb-status-dot"></span>Needs attention
                </span>
              )}
              <div className="fb-eyebrow" style={{ marginBottom: ".4rem" }}>{act.kind} · {act.agent}</div>
              <h3>{act.title}</h3>
              <div className="fb-rec-evidence">{act.detail}</div>
              <div style={{ display: "flex", gap: ".6rem", flexWrap: "wrap", alignItems: "center", marginTop: ".8rem" }}>
                <ConfirmApproveButton label={act.approveLabel} onConfirm={() => approveAction(act.id)} />
                <button className="fb-btn fb-btn-outline" type="button" onClick={() => rejectAction(act.id)}>Discard</button>
              </div>
              {/send/i.test(act.approveLabel) && (
                <div className="fb-fine" style={{ marginTop: ".6rem" }}>
                  Approving marks this ready — actual delivery needs an email or Telegram send provider connected, which isn't set up yet.
                </div>
              )}
            </div>
          ))}

          {showOutreach && outreachDrafts.map((draft) => (
            <div className="fb-rec-card is-type-outreach" key={`outreach-${draft.id}`}>
              <TypeBadge type="outreach" />
              {needsAttention(draft.draft_text) && (
                <span className="fb-status-pill is-review" style={{ marginBottom: ".5rem" }}>
                  <span className="fb-status-dot"></span>Needs attention
                </span>
              )}
              <div className="fb-eyebrow" style={{ marginBottom: ".4rem" }}>e-Invoice Readiness · via {draft.channel}</div>
              <div className="fb-rec-evidence">{draft.draft_text}</div>
              <div style={{ display: "flex", gap: ".6rem", flexWrap: "wrap", alignItems: "center", marginTop: ".8rem" }}>
                <ConfirmApproveButton label="Approve & send" onConfirm={() => decideOutreach(draft.id, "approve")} />
                <button className="fb-btn fb-btn-outline" type="button" onClick={() => decideOutreach(draft.id, "reject")}>Discard</button>
              </div>
              <div className="fb-fine" style={{ marginTop: ".6rem" }}>
                Approving marks this ready — actual delivery needs an email or Telegram send provider connected, which isn't set up yet.
              </div>
            </div>
          ))}
          {(activeFilter === null || activeFilter === "outreach") && visibleCustomerOutreach.map((action) => (
            <div className="fb-rec-card is-type-outreach" key={`customer-outreach-${action.id}`}>
              <TypeBadge type="outreach" />
              <div className="fb-eyebrow" style={{ marginBottom: ".4rem" }}>Customer intelligence · protected email · waiting for approval</div>
              <h3>{action.protected_subject}</h3>
              <div className="fb-rec-evidence">{action.protected_body}</div>
              <div className="fb-fine" style={{ marginTop: ".5rem" }}>Customer #{action.customer_id} · {action.attempt_count} delivery attempt(s)</div>
              <div style={{ display: "flex", gap: ".6rem", flexWrap: "wrap", alignItems: "center", marginTop: ".8rem" }}>
                <ConfirmApproveButton
                  label="Approve & queue"
                  disabled={askRole !== "owner_director"}
                  disabledReason="Owner / director role required"
                  onConfirm={() => void decideCustomerOutreach(action.id, "approve")}
                />
                <button className="fb-btn fb-btn-outline" type="button" disabled={askRole !== "owner_director"} onClick={() => void decideCustomerOutreach(action.id, "reject")}>Reject</button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
