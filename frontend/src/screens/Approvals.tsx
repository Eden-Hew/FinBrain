import { useI18n } from "../lib/i18n";
import { useAppState } from "../lib/appState";
import { AppNav } from "../components/Nav";

export default function Approvals() {
  const { t } = useI18n();
  const {
    einvoices, approveEinvoiceById, rejectEinvoiceById,
    sops, approveSop, rejectSop,
    pendingActions, approveAction, rejectAction,
  } = useAppState();

  const pendingInvoices = Object.values(einvoices).filter((inv) => inv.status === "pending");
  const draftSops = sops.filter((s) => s.status === "draft");
  const activeActions = pendingActions.filter((a) => a.active);

  const isEmpty = pendingInvoices.length === 0 && draftSops.length === 0 && activeActions.length === 0;

  return (
    <div className="fb-root">
      <AppNav current="approvals" />

      <header className="fb-app-header">
        <h1>{t("approvals.title")}</h1>
        <p>{t("approvals.desc")}</p>
      </header>

      <div className="fb-page-body">
        <div className="fb-card-list">
          {isEmpty && <p className="fb-sans" style={{ color: "var(--ink-soft)", fontSize: ".8rem" }}>Nothing waiting on you right now — you're fully caught up.</p>}

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
