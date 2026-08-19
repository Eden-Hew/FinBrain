import { useAppState, submitterName } from "../lib/appState";
import { Sidebar, AppTopBar } from "../components/Nav";
import { FB_EINVOICE_STATUS_LABEL } from "../data/sampleData";

export default function EinvoiceDetail() {
  const { einvoices, currentEinvoiceId, approveEinvoiceById, show } = useAppState();
  const inv = currentEinvoiceId ? einvoices[currentEinvoiceId] : null;

  if (!inv) return null;

  const showApproveBtn = inv.status !== "submitted" && inv.status !== "validated";
  const showUinPanel = inv.status === "submitted" || inv.status === "validated";

  return (
    <div className="fb-root fb-shell">
      <Sidebar backTo={() => show("einvoice")} backLabel="e-Invoicing" />
      <AppTopBar current="einvoice-detail" />

      <div className="fb-detail-header">
        <div className="fb-detail-header-top">
          <div>
            <div className="fb-eyebrow" style={{ marginBottom: ".5rem" }}>{FB_EINVOICE_STATUS_LABEL[inv.status]}</div>
            <h1>{inv.supplier} · {inv.amount}</h1>
            <p>{inv.description}</p>
          </div>
          {showApproveBtn && (
            <button
              className="fb-btn fb-btn-solid"
              type="button"
              disabled={inv.status === "review"}
              onClick={() => approveEinvoiceById(inv.id)}
            >
              Approve &amp; Submit to MyInvois
            </button>
          )}
        </div>
        {inv.status === "review" && (
          <div className="fb-callout" style={{ marginTop: "1rem" }}>
            <strong>This needs {submitterName(inv.submitter)}'s attention, not just approval:</strong> the flagged field above has to be corrected and resubmitted before this can move forward — approving is blocked until then.
          </div>
        )}
      </div>

      <div className="fb-detail-body">
        <div className="fb-detail-col">
          <h2>Extracted fields</h2>
          <p className="fb-sans" style={{ fontSize: ".68rem", color: "var(--ink-soft)", margin: "-.5rem 0 .8rem" }}>Showing 8 of the 55 mandatory MyInvois UBL fields.</p>
          <div className="fb-settings-list">
            {inv.fields.map((row) => <div className="fb-settings-row" key={row[0]}><span>{row[0]}</span><span>{row[1]}</span></div>)}
          </div>
        </div>
        <div className="fb-detail-col">
          <h2>PDPA &amp; compliance</h2>
          <div className="fb-log-list">
            {inv.compliance.map((row, i) => <div className="fb-log-row" key={i}><div className="fb-log-row-time">{row[0]}</div><div className="fb-log-row-text">{row[1]}</div></div>)}
          </div>
        </div>
      </div>

      {showUinPanel && (
        <div className="fb-uin-panel" style={{ maxWidth: "920px", margin: "1.4rem auto 0" }}>
          <div className="fb-qr-mock" aria-hidden="true"></div>
          <div>
            <div className="fb-eyebrow" style={{ marginBottom: ".3rem" }}>Submitted to MyInvois (sandbox)</div>
            <div className="fb-uin-code">UIN {inv.uin}</div>
            <div className="fb-sans" style={{ fontSize: ".68rem", color: "var(--ink-soft)", marginTop: ".3rem" }}>Validated by LHDN · QR code shown is a mock, not scannable.</div>
          </div>
        </div>
      )}
    </div>
  );
}
