import { useMemo, useState } from "react";
import { useI18n } from "../lib/i18n";
import { useAppState, submitterName } from "../lib/appState";
import { Sidebar, AppTopBar } from "../components/Nav";
import { FB_EINVOICE_ORDER, FB_EINVOICE_STATUS_LABEL, FB_ROLE_IDENTITY, type EinvoiceStatus } from "../data/sampleData";

const STATUS_LEGEND: { status: EinvoiceStatus; note: string }[] = [
  { status: "review", note: "A required field couldn't be read — needs a human fix before it can move forward." },
  { status: "pending", note: "OCR looks good; waiting on a Finance Director to approve submission." },
  { status: "submitted", note: "Signed and sent to the MyInvois sandbox — waiting on LHDN validation." },
  { status: "validated", note: "LHDN returned a UIN and QR code. Nothing further to do." },
];

function parseAmount(amount: string): number {
  const n = Number(amount.replace(/[^0-9.]/g, ""));
  return Number.isFinite(n) ? n : 0;
}

function formatRm(total: number): string {
  return "RM " + total.toLocaleString("en-MY", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function Einvoice() {
  const { t } = useI18n();
  const { einvoices, einvoiceFilterMine, setEinvoiceFilterMine, askRole, showEinvoiceDetail } = useAppState();
  const myEmail = FB_ROLE_IDENTITY[askRole].email;
  const [search, setSearch] = useState("");
  const [legendOpen, setLegendOpen] = useState(false);
  const [pdpaOpen, setPdpaOpen] = useState(false);

  const scoped = FB_EINVOICE_ORDER.filter((id) => !einvoiceFilterMine || einvoices[id].submitter === myEmail);
  const order = scoped.filter((id) => einvoices[id].supplier.toLowerCase().includes(search.trim().toLowerCase()));

  const needsAttention = scoped
    .map((id) => einvoices[id])
    .filter((inv) => inv.submitter === myEmail && (inv.status === "pending" || inv.status === "review"));

  const stats = useMemo(() => {
    const rows = scoped.map((id) => einvoices[id]);
    return {
      review: rows.filter((r) => r.status === "review").length,
      pending: rows.filter((r) => r.status === "pending").length,
      processed: rows.filter((r) => r.status === "submitted" || r.status === "validated").length,
      total: formatRm(rows.reduce((sum, r) => sum + parseAmount(r.amount), 0)),
    };
  }, [scoped, einvoices]);

  return (
    <div className="fb-root fb-shell">
      <Sidebar current="einvoice" />
      <AppTopBar current="einvoice" />

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

      <div className="fb-kpi-row" style={{ paddingBottom: "1.4rem" }}>
        <div className="fb-kpi-tile">
          <div className="fb-kpi-label">Needs review</div>
          <div className="fb-kpi-value" style={{ color: stats.review > 0 ? "var(--chart-attn)" : undefined }}>{stats.review}</div>
        </div>
        <div className="fb-kpi-tile">
          <div className="fb-kpi-label">Pending approval</div>
          <div className="fb-kpi-value">{stats.pending}</div>
        </div>
        <div className="fb-kpi-tile">
          <div className="fb-kpi-label">Submitted / validated</div>
          <div className="fb-kpi-value" style={{ color: "var(--chart-good)" }}>{stats.processed}</div>
        </div>
        <div className="fb-kpi-tile">
          <div className="fb-kpi-label">Total in view</div>
          <div className="fb-kpi-value">{stats.total}</div>
        </div>
      </div>

      {needsAttention.length > 0 && myEmail && (
        <div className="fb-callout" style={{ marginTop: 0, borderColor: "var(--chart-attn)" }}>
          <strong>{needsAttention.length} of your submissions need attention:</strong>{" "}
          {needsAttention
            .map((inv) => inv.supplier + (inv.status === "review" ? " — missing a field, please resubmit with the correction" : " — awaiting Finance Director approval"))
            .join("; ")}.
        </div>
      )}

      <div className="fb-unified-wrap" style={{ margin: "0 0 .8rem", maxWidth: "920px", padding: "0 1.5rem" }}>
        <button className="fb-link-toggle" type="button" onClick={() => setPdpaOpen((v) => !v)} aria-expanded={pdpaOpen}>
          <span className={"fb-link-toggle-caret" + (pdpaOpen ? " is-open" : "")}>▸</span>
          How is my receipt data protected? (PDPA compliance)
        </button>
        {pdpaOpen && (
          <div className="fb-callout" style={{ marginTop: ".6rem" }}>
            Personal identifiers (IC numbers, phone numbers) captured on a receipt are masked immediately after OCR — before any extracted field is stored or sent to an AI model. Only the fields MyInvois requires are retained, and the source photo is purged automatically after 30 days.
          </div>
        )}
      </div>

      <div className="fb-table-toolbar">
        <div className="fb-table-search">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" /></svg>
          <input type="text" placeholder="Search by supplier…" value={search} onChange={(event) => setSearch(event.target.value)} />
        </div>
        <div
          className="fb-table-legend"
          onBlur={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget as Node)) setLegendOpen(false);
          }}
        >
          <button className="fb-info-tip-trigger" type="button" onClick={() => setLegendOpen((v) => !v)} aria-expanded={legendOpen}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 16v-4M12 8h.01" /></svg>
            What do the statuses mean?
          </button>
          {legendOpen && (
            <div className="fb-info-tip-panel" role="tooltip">
              {STATUS_LEGEND.map((item) => (
                <div className="fb-info-tip-row" key={item.status}>
                  <span className={"fb-status-pill " + (item.status === "review" ? "is-review" : item.status === "pending" ? "" : "is-active")}>
                    <span className="fb-status-dot"></span>{FB_EINVOICE_STATUS_LABEL[item.status]}
                  </span>
                  <span>{item.note}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="fb-table-wrap">
        <table className="fb-table">
          <thead>
            <tr><th>Date</th><th>Supplier</th><th style={{ textAlign: "right" }}>Amount</th><th>Status</th><th>Submitted by</th><th>UIN</th><th aria-hidden="true"></th></tr>
          </thead>
          <tbody>
            {order.length === 0 ? (
              <tr><td colSpan={7} style={{ color: "var(--ink-soft)" }}>{scoped.length === 0 ? "No submissions from you yet — receipts you send via Telegram, email, or upload will show up here." : "No suppliers match your search."}</td></tr>
            ) : (
              order.map((id) => {
                const inv = einvoices[id];
                const pillClass = inv.status === "review" ? "is-review" : inv.status === "pending" ? "" : "is-active";
                return (
                  <tr key={id} className="fb-table-row-clickable" tabIndex={0} role="button" onClick={() => showEinvoiceDetail(id)} onKeyDown={(e) => { if (e.key === "Enter") showEinvoiceDetail(id); }}>
                    <td>{inv.date}</td>
                    <td>{inv.supplier}</td>
                    <td className="fb-num">{inv.amount}</td>
                    <td><span className={"fb-status-pill " + pillClass}><span className="fb-status-dot"></span>{FB_EINVOICE_STATUS_LABEL[inv.status]}</span></td>
                    <td>{inv.submitter === myEmail ? "You" : submitterName(inv.submitter)}</td>
                    <td>{inv.uin || "—"}</td>
                    <td className="fb-table-row-chevron" aria-hidden="true">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m9 18 6-6-6-6" /></svg>
                    </td>
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
