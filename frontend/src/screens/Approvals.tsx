import { useEffect, useState } from "react";
import { useI18n } from "../lib/i18n";
import { useAppState } from "../lib/appState";
import { AppNav } from "../components/Nav";
import { PersonaSelector } from "../components/PersonaSelector";
import { PERSONAS } from "../lib/personas";
import {
  analyzeProcesses,
  decideRecommendation,
  fetchRecommendations,
  type ProcessRecommendation,
} from "../api/client";

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

  const refreshRecommendations = async () => {
    const rows = await fetchRecommendations(askRole);
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
        const rows = await fetchRecommendations(askRole);
        if (active) setRecommendations(rows);
      } catch {
        if (active) setRecommendations([]);
      }
    };
    void initialLoad();
    return () => { active = false; };
  }, [askRole, capabilities.viewRecommendations]);

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
      await analyzeProcesses(askRole);
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
      const updated = await decideRecommendation(id, decision, askRole);
      setRecommendations((rows) => rows.map((row) => row.id === id ? updated : row));
    } catch (error) {
      setRecommendationError(error instanceof Error ? error.message : "Decision failed.");
    }
  };

  const pendingInvoices = Object.values(einvoices).filter((inv) => inv.status === "pending");
  const draftSops = sops.filter((s) => s.status === "draft");
  const activeActions = pendingActions.filter((a) => a.active);

  const openRecommendations = recommendations.filter((item) => (
    item.status === "proposed" || item.status === "approved"
  ));
  const isEmpty = pendingInvoices.length === 0
    && draftSops.length === 0
    && activeActions.length === 0
    && openRecommendations.length === 0;

  return (
    <div className="fb-root">
      <AppNav current="approvals" />

      <header className="fb-app-header">
        <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap" }}>
          <div>
            <h1>{t("approvals.title")}</h1>
            <p>{t("approvals.desc")}</p>
          </div>
          <button
            className="fb-btn fb-btn-solid"
            type="button"
            onClick={analyze}
            disabled={loadingAnalysis || !capabilities.analyzeProcesses}
            title={capabilities.analyzeProcesses ? "" : "Owner / director persona required"}
          >
            {loadingAnalysis ? "Analyzing protected records…" : "Analyze recurring problems"}
          </button>
        </div>
      </header>

      <div className="fb-page-body">
        <PersonaSelector />
        {!capabilities.viewRecommendations && (
          <div className="fb-callout">This persona cannot view process recommendations.</div>
        )}
        {recommendationError && <div className="fb-callout" role="alert">{recommendationError}</div>}
        <div className="fb-card-list">
          {isEmpty && <p className="fb-sans" style={{ color: "var(--ink-soft)", fontSize: ".8rem" }}>Nothing waiting on you right now — you're fully caught up.</p>}

          {openRecommendations.map((item) => (
            <article
              id={`recommendation-${item.id}`}
              className={`fb-rec-card${focusedRecommendationId === item.id ? " is-focused" : ""}`}
              key={`process-${item.id}`}
              tabIndex={-1}
            >
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
              <div style={{ display: "flex", gap: ".6rem", flexWrap: "wrap", marginTop: ".8rem" }}>
                {item.status === "proposed" ? (
                  <>
                    <button className="fb-btn fb-btn-solid" type="button" disabled={!capabilities.decideRecommendations} title="Owner / director persona required" onClick={() => decide(item.id, "approve")}>Approve recommendation</button>
                    <button className="fb-btn fb-btn-outline" type="button" disabled={!capabilities.decideRecommendations} title="Owner / director persona required" onClick={() => decide(item.id, "reject")}>Reject</button>
                  </>
                ) : (
                  <button className="fb-btn fb-btn-solid" type="button" disabled={!capabilities.decideRecommendations} title="Owner / director persona required" onClick={() => decide(item.id, "mark-implemented")}>Mark implemented</button>
                )}
              </div>
            </article>
          ))}

          {pendingInvoices.map((inv) => (
            <div className="fb-rec-card is-financial" key={inv.id}>
              <div className="fb-eyebrow" style={{ marginBottom: ".4rem" }}>Invoice · Invoicing Agent</div>
              <h3>{inv.supplier} — {inv.amount}</h3>
              <div className="fb-rec-evidence">{inv.description}</div>
              <div style={{ display: "flex", gap: ".6rem", flexWrap: "wrap", marginTop: ".8rem" }}>
                <button className="fb-btn fb-btn-solid" type="button" onClick={() => approveEinvoiceById(inv.id)}>Approve &amp; submit</button>
                <button className="fb-btn fb-btn-outline" type="button" onClick={() => rejectEinvoiceById(inv.id)}>Send back</button>
              </div>
            </div>
          ))}

          {draftSops.map((sop) => (
            <div className="fb-rec-card" key={sop.id}>
              <div className="fb-eyebrow" style={{ marginBottom: ".4rem" }}>SOP · drafted from a recommendation</div>
              <h3>{sop.title}</h3>
              <div className="fb-rec-evidence">Owner: {sop.owner} · v{sop.version}</div>
              <div style={{ display: "flex", gap: ".6rem", flexWrap: "wrap", marginTop: ".8rem" }}>
                <button className="fb-btn fb-btn-solid" type="button" onClick={() => approveSop(sop.id)}>Approve SOP</button>
                <button className="fb-btn fb-btn-outline" type="button" onClick={() => rejectSop(sop.id)}>Discard draft</button>
              </div>
            </div>
          ))}

          {activeActions.map((act) => (
            <div className="fb-rec-card is-financial" key={act.id}>
              <div className="fb-eyebrow" style={{ marginBottom: ".4rem" }}>{act.kind} · {act.agent}</div>
              <h3>{act.title}</h3>
              <div className="fb-rec-evidence">{act.detail}</div>
              <div style={{ display: "flex", gap: ".6rem", flexWrap: "wrap", marginTop: ".8rem" }}>
                <button className="fb-btn fb-btn-solid" type="button" onClick={() => approveAction(act.id)}>{act.approveLabel}</button>
                <button className="fb-btn fb-btn-outline" type="button" onClick={() => rejectAction(act.id)}>Discard</button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
