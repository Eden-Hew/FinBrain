import { useEffect, useMemo, useState } from "react";
import { useI18n } from "../lib/i18n";
import { useAppState } from "../lib/appState";
import { Sidebar, AppTopBar } from "../components/Nav";
import { EmptyState } from "../components/EmptyState";
import { PERSONAS } from "../lib/personas";
import { FB_EINVOICE_STATUS_LABEL, type EinvoiceStatus } from "../data/sampleData";
import {
  createEinvoiceRecord,
  extractEinvoiceFields,
  fetchEinvoiceDocumentUrl,
  fetchEinvoicePdfBlob,
  fetchEinvoiceReadiness,
  fetchEinvoiceRecords,
  friendlyLoadError,
  requestEinvoiceFix,
  uploadEinvoiceDocument,
  type EInvoiceApiRecord,
  type EInvoiceCreatePayload,
  type EinvoiceReadinessResponse,
} from "../api/client";

const STATUS_LEGEND: { status: EinvoiceStatus; note: string }[] = [
  { status: "review", note: "A required field couldn't be read — needs a human fix before it can move forward." },
  { status: "pending", note: "OCR looks good; waiting on a Finance Director to approve submission." },
  { status: "submitted", note: "Signed and sent to the MyInvois sandbox — waiting on LHDN validation." },
  { status: "validated", note: "LHDN returned a UIN and QR code. Nothing further to do." },
];

function formatRm(total: number): string {
  return "RM " + total.toLocaleString("en-MY", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// "Submitted" (sent, awaiting LHDN) and "validated" (LHDN issued a UIN, done)
// used to share the same green pill — distinct enough states that a reviewer
// scanning the table should be able to tell them apart at a glance.
function statusPillClass(status: EinvoiceStatus): string {
  if (status === "review") return "is-review";
  if (status === "pending") return "";
  if (status === "submitted") return "is-submitted";
  return "is-active";
}

// The backend returns readiness_reason as one joined string (each issue is a
// complete sentence). Split it back into individual issues so a reviewer can
// scan them as a list instead of parsing a run-on paragraph.
function splitReadinessIssues(reason: string): string[] {
  return reason
    .split(/\.\s+/)
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) => (s.endsWith(".") ? s : s + "."));
}

type ReadinessCategoryKey = "critical" | "warning" | "passing";
type FixState = "idle" | "sending" | "sent" | "failed";
type DocumentState = "idle" | "loading" | "failed";

export async function openEinvoiceDocument(
  recordId: number,
  setDocumentState: (updater: (s: Record<number, DocumentState>) => Record<number, DocumentState>) => void,
) {
  const tab = window.open("", "_blank");
  setDocumentState((s) => ({ ...s, [recordId]: "loading" }));
  try {
    const blob = await fetchEinvoicePdfBlob(recordId);
    const blobUrl = URL.createObjectURL(blob);
    setDocumentState((s) => ({ ...s, [recordId]: "idle" }));
    if (tab) {
      tab.location.href = blobUrl;
    }
  } catch (err) {
    console.error("fetchEinvoicePdfBlob failed, attempting document URL fallback:", err);
    try {
      const { url } = await fetchEinvoiceDocumentUrl(recordId);
      setDocumentState((s) => ({ ...s, [recordId]: "idle" }));
      if (tab) tab.location.href = url;
    } catch (fallbackErr) {
      console.error("Failed to open invoice document:", fallbackErr);
      tab?.close();
      setDocumentState((s) => ({ ...s, [recordId]: "failed" }));
    }
  }
}

function ReadinessCheckPanel({ canManage }: { canManage: boolean }) {
  const [data, setData] = useState<EinvoiceReadinessResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<ReadinessCategoryKey | null>("critical");
  const [fixState, setFixState] = useState<Record<number, FixState>>({});
  const [documentState, setDocumentState] = useState<Record<number, DocumentState>>({});

  useEffect(() => {
    let active = true;
    fetchEinvoiceReadiness()
      .then((res) => { if (active) { setData(res); setLoading(false); } })
      .catch((err) => { if (active) { setError(err instanceof Error ? friendlyLoadError(err.message) : "Failed to load readiness check."); setLoading(false); } });
    return () => { active = false; };
  }, []);

  const requestFix = async (recordId: number) => {
    setFixState((s) => ({ ...s, [recordId]: "sending" }));
    try {
      await requestEinvoiceFix(recordId, "telegram");
      setFixState((s) => ({ ...s, [recordId]: "sent" }));
    } catch {
      setFixState((s) => ({ ...s, [recordId]: "failed" }));
    }
  };

  if (loading) return <div className="fb-callout">Loading readiness check…</div>;
  if (error) return <div className="fb-callout" style={{ borderColor: "var(--chart-attn)", color: "var(--chart-attn)" }}>{error}</div>;
  if (!data) return null;

  const categoryColor = (key: ReadinessCategoryKey) =>
    key === "critical" ? "var(--chart-attn)" : key === "passing" ? "var(--chart-good)" : undefined;

  return (
    <div>
      <div className="fb-readiness-score">
        <div className="fb-readiness-score-value">{Math.round(data.score * 100)}%</div>
        <div>
          <div className="fb-readiness-score-label">Ready for MyInvois submission</div>
          <div className="fb-fine">{data.passing_count} of {data.total_records} invoices pass all checks</div>
        </div>
      </div>

      <div className="fb-kpi-row" style={{ padding: "0 1.5rem", margin: "1.4rem 0" }}>
        {(["critical", "warning", "passing"] as const).map((key) => (
          <button
            key={key}
            className={"fb-kpi-tile fb-readiness-cat" + (expanded === key ? " is-open" : "")}
            type="button"
            onClick={() => setExpanded((current) => (current === key ? null : key))}
            aria-expanded={expanded === key}
          >
            <div className="fb-kpi-label">{key === "critical" ? "Critical" : key === "warning" ? "Warnings" : "Passing"}</div>
            <div className="fb-kpi-value" style={{ color: categoryColor(key) }}>{data[key].count}</div>
          </button>
        ))}
      </div>

      {expanded && (
        <div className="fb-table-wrap">
          <table className="fb-table">
            <thead>
              <tr><th>Supplier</th><th>Invoice</th><th style={{ textAlign: "right" }}>Amount</th><th>Document</th><th aria-hidden="true"></th></tr>
            </thead>
            <tbody>
              {data[expanded].records.length === 0 ? (
                <tr><td colSpan={5} style={{ color: "var(--ink-soft)" }}>Nothing in this category.</td></tr>
              ) : (
                data[expanded].records.map((record) => (
                  <tr key={record.id}>
                    <td>
                      <div>{record.supplier_name}</div>
                      {expanded !== "passing" && (
                        <ul className="fb-readiness-issue-list" style={{ maxWidth: "34ch" }}>
                          {splitReadinessIssues(record.readiness_reason).map((issue, i) => (
                            <li key={i} className="fb-fine">
                              <span className="fb-status-dot" aria-hidden="true" style={{ background: categoryColor(expanded) }} />
                              {issue}
                            </li>
                          ))}
                        </ul>
                      )}
                    </td>
                    <td>{record.invoice_no ?? "—"}</td>
                    <td className="fb-num">RM {record.total_amount}</td>
                    <td>
                      {record.document_available ? (
                        <button
                          className="fb-link-toggle"
                          type="button"
                          disabled={documentState[record.id] === "loading"}
                          onClick={() => openEinvoiceDocument(record.id, setDocumentState)}
                        >
                          {documentState[record.id] === "loading" ? "Opening…" : documentState[record.id] === "failed" ? "Retry" : "View invoice"}
                        </button>
                      ) : (
                        <span className="fb-fine">No document</span>
                      )}
                    </td>
                    <td>
                      {expanded === "critical" && canManage && (
                        fixState[record.id] === "sent" ? (
                          <span className="fb-fine">Draft sent to Approvals</span>
                        ) : (
                          <button
                            className="fb-btn fb-btn-outline"
                            type="button"
                            disabled={fixState[record.id] === "sending"}
                            onClick={() => requestFix(record.id)}
                          >
                            {fixState[record.id] === "sending" ? "Drafting…" : fixState[record.id] === "failed" ? "Retry" : "Request Fix"}
                          </button>
                        )
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function AddInvoiceForm({ onCreated, onCancel, onWarning }: { onCreated: (record: EInvoiceApiRecord) => void; onCancel: () => void; onWarning: (msg: string) => void }) {
  const [form, setForm] = useState({
    supplier_name: "",
    supplier_tin: "",
    buyer_name: "",
    invoice_no: "",
    issue_date: "",
    currency: "MYR",
    tax_type: "",
    tax_rate: "",
    total_amount: "",
  });
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [extractNotice, setExtractNotice] = useState("");
  const [error, setError] = useState("");

  const field = (key: keyof typeof form) => ({
    value: form[key],
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => setForm((f) => ({ ...f, [key]: e.target.value })),
  });

  const selectFile = async (selected: File | undefined) => {
    if (!selected) { setFile(null); return; }
    setFile(selected);
    setExtracting(true);
    setExtractNotice("");
    setError("");
    try {
      const extracted = await extractEinvoiceFields(selected);
      setForm((f) => ({
        supplier_name: extracted.supplier_name ?? f.supplier_name,
        supplier_tin: extracted.supplier_tin ?? f.supplier_tin,
        buyer_name: extracted.buyer_name ?? f.buyer_name,
        invoice_no: extracted.invoice_no ?? f.invoice_no,
        issue_date: extracted.issue_date ?? f.issue_date,
        currency: extracted.currency ?? f.currency,
        tax_type: extracted.tax_type ?? f.tax_type,
        tax_rate: extracted.tax_rate ?? f.tax_rate,
        total_amount: extracted.total_amount ?? f.total_amount,
      }));
      setExtractNotice("Fields auto-filled from the PDF — please review before saving.");
    } catch (err) {
      setExtractNotice(
        "Couldn't auto-fill from this PDF (" +
        (err instanceof Error ? err.message : "extraction failed") +
        "). You can still fill in the fields manually — the file will still be attached.",
      );
    } finally {
      setExtracting(false);
    }
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const payload: EInvoiceCreatePayload = {
        supplier_name: form.supplier_name.trim(),
        supplier_tin: form.supplier_tin.trim() || null,
        buyer_name: form.buyer_name.trim() || null,
        invoice_no: form.invoice_no.trim() || null,
        issue_date: form.issue_date || null,
        currency: form.currency.trim() || null,
        tax_type: form.tax_type.trim() || null,
        tax_rate: form.tax_rate.trim() || null,
        total_amount: form.total_amount.trim(),
      };
      const created = await createEinvoiceRecord(payload);
      if (!file) {
        onCreated(created);
        return;
      }
      try {
        onCreated(await uploadEinvoiceDocument(created.id, file));
      } catch (uploadErr) {
        onWarning(
          `${created.supplier_name} was saved, but the PDF failed to attach (` +
          (uploadErr instanceof Error ? uploadErr.message : "unknown error") +
          "). Open the invoice's detail page to retry.",
        );
        onCreated(created);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save invoice.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={submit} className="fb-answer-card" style={{ display: "flex", flexDirection: "column", gap: ".9rem", maxWidth: "760px", margin: "0 0 1.4rem", padding: "1.2rem 1.4rem" }}>
      <label className="fb-field-label">Invoice PDF (optional — auto-fills the fields below)
        <input
          className="fb-field-mock"
          type="file"
          accept="application/pdf"
          disabled={extracting}
          onChange={(e) => void selectFile(e.target.files?.[0])}
        />
      </label>
      {extracting && <div className="fb-fine">Reading the PDF and extracting fields…</div>}
      {extractNotice && !extracting && <div className="fb-fine">{extractNotice}</div>}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "1rem" }}>
        <label className="fb-field-label" style={{ gridColumn: "1 / -1" }}>Supplier name
          <input className="fb-field-mock" {...field("supplier_name")} required />
        </label>
        <label className="fb-field-label">Supplier TIN
          <input className="fb-field-mock" {...field("supplier_tin")} placeholder="Leave blank if unknown" />
        </label>
        <label className="fb-field-label">Buyer name
          <input className="fb-field-mock" {...field("buyer_name")} />
        </label>
        <label className="fb-field-label">Invoice no.
          <input className="fb-field-mock" {...field("invoice_no")} />
        </label>
        <label className="fb-field-label">Issue date
          <input className="fb-field-mock" type="date" {...field("issue_date")} />
        </label>
        <label className="fb-field-label">Currency
          <input className="fb-field-mock" {...field("currency")} />
        </label>
        <label className="fb-field-label">Tax type
          <input className="fb-field-mock" {...field("tax_type")} placeholder="e.g. SST" />
        </label>
        <label className="fb-field-label">Tax rate
          <input className="fb-field-mock" {...field("tax_rate")} placeholder="e.g. 6%" />
        </label>
        <label className="fb-field-label">Total amount (RM)
          <input className="fb-field-mock" type="number" step="0.01" min="0.01" {...field("total_amount")} required />
        </label>
      </div>
      {error && <div className="fb-fine" style={{ color: "var(--chart-attn)" }} role="alert">{error}</div>}
      <div style={{ display: "flex", gap: ".6rem" }}>
        <button type="submit" className="fb-btn fb-btn-solid" disabled={submitting || extracting}>
          {submitting ? "Saving…" : "Save invoice"}
        </button>
        <button type="button" className="fb-btn fb-btn-outline" onClick={onCancel} disabled={submitting}>Cancel</button>
      </div>
    </form>
  );
}

type InvoiceStatusFilter = "all" | "review" | "pending" | "processed";

function AllInvoicesPanel() {
  const { showEinvoiceDetail, askRole } = useAppState();
  const [records, setRecords] = useState<EInvoiceApiRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<InvoiceStatusFilter>("all");
  const [legendOpen, setLegendOpen] = useState(false);
  const [pdpaOpen, setPdpaOpen] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [banner, setBanner] = useState("");
  const canAdd = PERSONAS[askRole].capabilities.manageEinvoiceReadiness;

  useEffect(() => {
    let active = true;
    fetchEinvoiceRecords()
      .then((res) => { if (active) { setRecords(res); setLoading(false); } })
      .catch((err) => { if (active) { setError(err instanceof Error ? friendlyLoadError(err.message) : "Failed to load invoices."); setLoading(false); } });
    return () => { active = false; };
  }, []);

  const matchesStatusFilter = (r: EInvoiceApiRecord) => {
    if (statusFilter === "all") return true;
    if (statusFilter === "processed") return r.status === "submitted" || r.status === "validated";
    return r.status === statusFilter;
  };

  const order = records
    .filter((r) => r.supplier_name.toLowerCase().includes(search.trim().toLowerCase()))
    .filter(matchesStatusFilter);

  const stats = useMemo(() => ({
    review: records.filter((r) => r.status === "review").length,
    pending: records.filter((r) => r.status === "pending").length,
    processed: records.filter((r) => r.status === "submitted" || r.status === "validated").length,
    total: formatRm(records.reduce((sum, r) => sum + Number(r.total_amount), 0)),
  }), [records]);

  const toggleFilter = (key: InvoiceStatusFilter) => setStatusFilter((current) => (current === key ? "all" : key));

  if (loading) return <div className="fb-callout">Loading invoices…</div>;
  if (error) return <div className="fb-callout" style={{ borderColor: "var(--chart-attn)", color: "var(--chart-attn)" }}>{error}</div>;

  return (
    <>
      <div className="fb-kpi-row" style={{ paddingBottom: "1.4rem" }}>
        <button
          className={"fb-kpi-tile fb-readiness-cat" + (statusFilter === "review" ? " is-open" : "")}
          type="button"
          onClick={() => toggleFilter("review")}
          aria-pressed={statusFilter === "review"}
        >
          <div className="fb-kpi-label">Needs review</div>
          <div className="fb-kpi-value" style={{ color: stats.review > 0 ? "var(--chart-attn)" : undefined }}>{stats.review}</div>
        </button>
        <button
          className={"fb-kpi-tile fb-readiness-cat" + (statusFilter === "pending" ? " is-open" : "")}
          type="button"
          onClick={() => toggleFilter("pending")}
          aria-pressed={statusFilter === "pending"}
        >
          <div className="fb-kpi-label">Pending approval</div>
          <div className="fb-kpi-value">{stats.pending}</div>
        </button>
        <button
          className={"fb-kpi-tile fb-readiness-cat" + (statusFilter === "processed" ? " is-open" : "")}
          type="button"
          onClick={() => toggleFilter("processed")}
          aria-pressed={statusFilter === "processed"}
        >
          <div className="fb-kpi-label">Submitted / validated</div>
          <div className="fb-kpi-value" style={{ color: "var(--chart-good)" }}>{stats.processed}</div>
        </button>
        <div className="fb-kpi-tile">
          <div className="fb-kpi-label">Total in view</div>
          <div className="fb-kpi-value">{stats.total}</div>
        </div>
      </div>
      {statusFilter !== "all" && (
        <div style={{ padding: "0 1.5rem", margin: "-1rem 0 1rem" }}>
          <button className="fb-link-toggle" type="button" onClick={() => setStatusFilter("all")}>
            Showing {statusFilter === "processed" ? "submitted / validated" : statusFilter === "review" ? "needs review" : "pending approval"} only — clear filter
          </button>
        </div>
      )}

      {canAdd && (
        <div style={{ padding: "0 1.5rem", margin: "0 0 1.2rem" }}>
          {banner && <div className="fb-callout" style={{ marginBottom: "1rem" }} role="status">{banner}</div>}
          {addOpen ? (
            <AddInvoiceForm
              onCreated={(created) => {
                setRecords((r) => [created, ...r]);
                setAddOpen(false);
              }}
              onCancel={() => setAddOpen(false)}
              onWarning={setBanner}
            />
          ) : (
            <button className="fb-btn fb-btn-solid" type="button" onClick={() => setAddOpen(true)}>+ Add invoice</button>
          )}
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
                  <span className={"fb-status-pill " + statusPillClass(item.status)}>
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
            <tr><th>Date</th><th>Supplier</th><th style={{ textAlign: "right" }}>Amount</th><th>Status</th><th>UIN</th><th aria-hidden="true"></th></tr>
          </thead>
          <tbody>
            {order.length === 0 ? (
              <tr><td colSpan={6}>
                <EmptyState
                  icon={
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 3v4a1 1 0 0 0 1 1h4" /><path d="M17 21H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7l5 5v11a2 2 0 0 1-2 2Z" /><path d="M9 13h6M9 17h6" /></svg>
                  }
                  title={records.length === 0 ? "No invoices on file yet" : "No invoices match your filters"}
                  description={
                    records.length === 0
                      ? "Add your first invoice to start tracking e-invoice readiness."
                      : "Try a different supplier name, or clear the search/status filter to see all invoices."
                  }
                  action={
                    records.length === 0 && canAdd
                      ? { label: "+ Add invoice", onClick: () => setAddOpen(true) }
                      : records.length > 0 && (search.trim() !== "" || statusFilter !== "all")
                        ? { label: "Clear filters", onClick: () => { setSearch(""); setStatusFilter("all"); } }
                        : undefined
                  }
                />
              </td></tr>
            ) : (
              order.map((record) => {
                const pillClass = statusPillClass(record.status);
                return (
                  <tr
                    key={record.id}
                    className="fb-table-row-clickable"
                    tabIndex={0}
                    role="button"
                    onClick={() => showEinvoiceDetail(`real-${record.id}`)}
                    onKeyDown={(e) => { if (e.key === "Enter") showEinvoiceDetail(`real-${record.id}`); }}
                  >
                    <td>{record.issue_date ?? "—"}</td>
                    <td>{record.supplier_name}</td>
                    <td className="fb-num">RM {record.total_amount}</td>
                    <td><span className={"fb-status-pill " + pillClass}><span className="fb-status-dot"></span>{FB_EINVOICE_STATUS_LABEL[record.status]}</span></td>
                    <td>{record.uin || "—"}</td>
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
    </>
  );
}

export default function Einvoice() {
  const { t } = useI18n();
  const { askRole } = useAppState();
  const [activeTab, setActiveTab] = useState<"all" | "readiness">("all");

  return (
    <div className="fb-root fb-shell">
      <Sidebar current="einvoice" />
      <AppTopBar current="einvoice" />

      <header className="fb-app-header">
        <div>
          <h1>{t("einvoice.title")}</h1>
          <p>{t("einvoice.desc")}</p>
        </div>
        <div className="fb-role-switch" role="tablist" style={{ marginTop: "1rem" }}>
          <button className={"fb-role-btn" + (activeTab === "all" ? " is-current" : "")} type="button" onClick={() => setActiveTab("all")}>All invoices</button>
          <button className={"fb-role-btn" + (activeTab === "readiness" ? " is-current" : "")} type="button" onClick={() => setActiveTab("readiness")}>Readiness Check</button>
        </div>
      </header>

      {activeTab === "readiness" ? (
        <ReadinessCheckPanel canManage={PERSONAS[askRole].capabilities.manageEinvoiceReadiness} />
      ) : (
        <AllInvoicesPanel />
      )}
    </div>
  );
}
