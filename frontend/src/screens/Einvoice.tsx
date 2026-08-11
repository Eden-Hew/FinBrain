import { useI18n } from "../lib/i18n";
import { useAppState, submitterName } from "../lib/appState";
import { AppNav } from "../components/Nav";
import { FB_EINVOICE_ORDER, FB_EINVOICE_STATUS_LABEL, FB_ROLE_IDENTITY } from "../data/sampleData";

export default function Einvoice() {
  const { t } = useI18n();
  const { einvoices, einvoiceFilterMine, setEinvoiceFilterMine, askRole, showEinvoiceDetail } = useAppState();
  const myEmail = FB_ROLE_IDENTITY[askRole].email;

  const order = FB_EINVOICE_ORDER.filter((id) => !einvoiceFilterMine || einvoices[id].submitter === myEmail);

  const needsAttention = order
    .map((id) => einvoices[id])
    .filter((inv) => inv.submitter === myEmail && (inv.status === "pending" || inv.status === "review"));

  return (
    <div className="fb-root">
      <AppNav current="einvoice" />

      <header className="fb-app-header">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "1rem", flexWrap: "wrap" }}>
          <div>
            <h1>{t("einvoice.title")}</h1>
            <p>{t("einvoice.desc")}</p>
          </div>
          <div className="fb-role-switch" role="tablist" style={{ margin: 0 }}>
            <button className={"fb-role-btn" + (!einvoiceFilterMine ? " is-current" : "")} type="button" onClick={() => setEinvoiceFilterMine(false)}>{t("einvoice.filterAll")}</button>
            <button className={"fb-role-btn" + (einvoiceFilterMine ? " is-current" : "")} type="button" onClick={() => setEinvoiceFilterMine(true)}>{t("einvoice.filterMine")}</button>
          </div>
        </div>
      </header>

      <div className="fb-callout" style={{ marginTop: 0 }}>
        <strong>PDPA compliance:</strong> personal identifiers (IC numbers, phone numbers) captured on a receipt are masked immediately after OCR — before any extracted field is stored or sent to an AI model. Only the fields MyInvois requires are retained, and the source photo is purged automatically after 30 days.
      </div>

      {needsAttention.length > 0 && myEmail && (
        <div className="fb-callout">
          <strong>{needsAttention.length} of your submissions need attention:</strong>{" "}
          {needsAttention
            .map((inv) => inv.supplier + (inv.status === "review" ? " — missing a field, please resubmit with the correction" : " — awaiting Finance Director approval"))
            .join("; ")}.
        </div>
      )}

      <div className="fb-table-wrap">
        <table className="fb-table">
          <thead>
            <tr><th>Date</th><th>Supplier</th><th style={{ textAlign: "right" }}>Amount</th><th>Status</th><th>Submitted by</th><th>UIN</th></tr>
          </thead>
          <tbody>
            {order.length === 0 ? (
              <tr><td colSpan={6} style={{ color: "var(--ink-soft)" }}>No submissions from you yet — receipts you send via Telegram, email, or upload will show up here.</td></tr>
            ) : (
              order.map((id) => {
                const inv = einvoices[id];
                const pillClass = inv.status === "review" ? "is-review" : inv.status === "pending" ? "" : "is-active";
                return (
                  <tr key={id} tabIndex={0} role="button" onClick={() => showEinvoiceDetail(id)} onKeyDown={(e) => { if (e.key === "Enter") showEinvoiceDetail(id); }}>
                    <td>{inv.date}</td>
                    <td>{inv.supplier}</td>
                    <td className="fb-num">{inv.amount}</td>
                    <td><span className={"fb-status-pill " + pillClass}><span className="fb-status-dot"></span>{FB_EINVOICE_STATUS_LABEL[inv.status]}</span></td>
                    <td>{inv.submitter === myEmail ? "You" : submitterName(inv.submitter)}</td>
                    <td>{inv.uin || "—"}</td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
