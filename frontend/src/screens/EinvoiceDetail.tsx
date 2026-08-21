import { useEffect, useState } from "react";
import { useAppState } from "../lib/appState";
import { Sidebar, AppTopBar } from "../components/Nav";
import { PERSONAS } from "../lib/personas";
import { FB_EINVOICE_STATUS_LABEL } from "../data/sampleData";
import {
  approveEinvoiceRecord,
  fetchEinvoiceRecord,
  friendlyLoadError,
  markEinvoicePaid,
  requestEinvoiceFix,
  updateEinvoiceRecord,
  uploadEinvoiceDocument,
  type EInvoiceApiRecord,
  type EInvoiceUpdatePayload,
} from "../api/client";
import { openEinvoiceDocument, openEinvoiceReceipt } from "./Einvoice";

function RealEinvoiceDetail({ recordId }: { recordId: number }) {
  const { askRole, show } = useAppState();
  const [record, setRecord] = useState<EInvoiceApiRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [approving, setApproving] = useState(false);
  const [documentState, setDocumentState] = useState<Record<number, "idle" | "loading" | "failed">>({});
  const [receiptState, setReceiptState] = useState<Record<number, "idle" | "loading" | "failed">>({});
  const [attaching, setAttaching] = useState(false);
  const [attachError, setAttachError] = useState("");

  const [showPaymentModal, setShowPaymentModal] = useState(false);
  const [payDate, setPayDate] = useState(new Date().toISOString().slice(0, 10));
  const [payMethod, setPayMethod] = useState("Bank Transfer");
  const [payRef, setPayRef] = useState("");
  const [recordingPayment, setRecordingPayment] = useState(false);

  const [showEditModal, setShowEditModal] = useState(false);
  const [editForm, setEditForm] = useState({
    supplier_name: "",
    supplier_tin: "",
    buyer_name: "",
    invoice_no: "",
    issue_date: "",
    due_date: "",
    total_amount: "",
    currency: "MYR",
    tax_type: "SST",
    tax_rate: "6%",
  });
  const [savingEdit, setSavingEdit] = useState(false);
  const [editError, setEditError] = useState("");

  const [requestingFix, setRequestingFix] = useState(false);
  const [fixSuccessNotice, setFixSuccessNotice] = useState("");
  const [fixErrorNotice, setFixErrorNotice] = useState("");

  const attachDocument = async (file: File) => {
    setAttaching(true);
    setAttachError("");
    try {
      setRecord(await uploadEinvoiceDocument(recordId, file));
    } catch (err) {
      setAttachError(err instanceof Error ? err.message : "Failed to attach PDF.");
    } finally {
      setAttaching(false);
    }
  };

  useEffect(() => {
    fetchEinvoiceRecord(recordId)
      .then((res) => { setRecord(res); setLoading(false); })
      .catch((err) => { setError(err instanceof Error ? friendlyLoadError(err.message) : "Failed to load invoice."); setLoading(false); });
  }, [recordId]);

  const approve = async () => {
    setApproving(true);
    try {
      const updated = await approveEinvoiceRecord(recordId);
      setRecord(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Approve failed.");
    } finally {
      setApproving(false);
    }
  };

  const submitPayment = async () => {
    setRecordingPayment(true);
    try {
      const updated = await markEinvoicePaid(recordId, payDate);
      setRecord(updated);
      setShowPaymentModal(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Payment recording failed.");
    } finally {
      setRecordingPayment(false);
    }
  };

  const openEdit = () => {
    if (!record) return;
    setEditForm({
      supplier_name: record.supplier_name || "",
      supplier_tin: record.supplier_tin || "",
      buyer_name: record.buyer_name || "",
      invoice_no: record.invoice_no || "",
      issue_date: record.issue_date || "",
      due_date: record.due_date || "",
      total_amount: record.total_amount ? String(record.total_amount) : "",
      currency: record.currency || "MYR",
      tax_type: record.tax_type || "SST",
      tax_rate: record.tax_rate || "6%",
    });
    setEditError("");
    setShowEditModal(true);
  };

  const saveEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingEdit(true);
    setEditError("");
    try {
      const payload: EInvoiceUpdatePayload = {
        supplier_name: editForm.supplier_name.trim(),
        supplier_tin: editForm.supplier_tin.trim() || null,
        buyer_name: editForm.buyer_name.trim() || null,
        invoice_no: editForm.invoice_no.trim() || null,
        issue_date: editForm.issue_date || null,
        due_date: editForm.due_date || null,
        currency: editForm.currency.trim() || null,
        tax_type: editForm.tax_type.trim() || null,
        tax_rate: editForm.tax_rate.trim() || null,
        total_amount: editForm.total_amount.trim(),
      };
      const updated = await updateEinvoiceRecord(recordId, payload);
      setRecord(updated);
      setShowEditModal(false);
    } catch (err) {
      setEditError(err instanceof Error ? err.message : "Failed to save invoice changes.");
    } finally {
      setSavingEdit(false);
    }
  };

  const handleRequestFix = async () => {
    setRequestingFix(true);
    setFixSuccessNotice("");
    setFixErrorNotice("");
    try {
      await requestEinvoiceFix(recordId, "telegram");
      setFixSuccessNotice("Fix request sent to Approvals");
    } catch (err) {
      setFixErrorNotice(err instanceof Error ? err.message : "Failed to send fix request.");
    } finally {
      setRequestingFix(false);
    }
  };

  if (loading) return <div className="fb-root fb-shell"><Sidebar backTo={() => show("einvoice")} backLabel="e-Invoicing" /><AppTopBar current="einvoice-detail" /><div className="fb-callout">Loading invoice…</div></div>;
  if (error || !record) return <div className="fb-root fb-shell"><Sidebar backTo={() => show("einvoice")} backLabel="e-Invoicing" /><AppTopBar current="einvoice-detail" /><div className="fb-callout" style={{ borderColor: "var(--chart-attn)", color: "var(--chart-attn)" }}>{error || "Invoice not found."}</div></div>;

  const canApprove = PERSONAS[askRole].capabilities.approveEinvoiceSubmission;
  const canManage = PERSONAS[askRole].capabilities.manageEinvoiceReadiness;
  const needsAction = record.status === "review" || (!record.supplier_tin || !record.supplier_tin.trim());
  const showApproveBtn = record.status === "pending" && !needsAction;
  const isPaid = Boolean(record.paid_at);
  const showRecordPaymentBtn = record.status === "validated" && !isPaid && (canManage || canApprove);
  const showUinPanel = record.status === "validated";
  const displayUin = record.uin || ("MY29A" + (record.invoice_no ? record.invoice_no.replace(/[^A-Za-z0-9]/g, "").slice(-6).toUpperCase() : record.id));

  const fields: [string, React.ReactNode][] = [
    ["Supplier", record.supplier_name ? record.supplier_name : <span className="fb-badge-warning" style={{ color: "var(--chart-attn, #ef4444)" }}>Missing — Action Required</span>],
    ["Supplier TIN", record.supplier_tin && record.supplier_tin.trim() ? record.supplier_tin : <span className="fb-badge-warning" style={{ color: "var(--chart-attn, #ef4444)" }}>Missing — Action Required</span>],
    ["Buyer", record.buyer_name ?? "—"],
    ["Invoice No.", record.invoice_no && record.invoice_no.trim() ? record.invoice_no : <span className="fb-badge-warning" style={{ color: "var(--chart-attn, #ef4444)" }}>Missing</span>],
    ["Issue date", record.issue_date && record.issue_date.trim() ? record.issue_date : <span className="fb-badge-warning" style={{ color: "var(--chart-attn, #ef4444)" }}>Missing</span>],
    ["Due date", record.due_date ?? "—"],
    ["Payment status", isPaid ? `Paid on ${record.paid_at}` : "Unpaid / Outstanding"],
    ["Currency", record.currency ?? "—"],
    ["Tax type", record.tax_type ?? "—"],
    ["Tax rate", record.tax_rate ?? "—"],
  ];

  return (
    <div className="fb-root fb-shell">
      <Sidebar backTo={() => show("einvoice")} backLabel="e-Invoicing" />
      <AppTopBar current="einvoice-detail" />

      <div className="fb-detail-header">
        <div className="fb-detail-header-top">
          <div>
            <div className="fb-eyebrow" style={{ marginBottom: ".5rem", display: "flex", alignItems: "center", gap: ".5rem" }}>
              <span>{FB_EINVOICE_STATUS_LABEL[record.status]}</span>
              {isPaid && <span className="fb-status-pill is-active">Paid &bull; {record.paid_at}</span>}
            </div>
            <h1>{record.supplier_name} · RM {record.total_amount}</h1>
            <p>{record.readiness_reason}</p>
          </div>
          <div style={{ display: "flex", gap: ".6rem", alignItems: "center", flexWrap: "wrap" }}>
            {needsAction && (
              <button className="fb-btn fb-btn-outline" type="button" onClick={openEdit}>
                ✏️ Fix &amp; Edit Details
              </button>
            )}
            {needsAction && (
              <button
                className="fb-btn fb-btn-outline"
                type="button"
                disabled={requestingFix || fixSuccessNotice !== ""}
                onClick={handleRequestFix}
              >
                {requestingFix ? "Sending request…" : fixSuccessNotice ? "✓ Fix Requested" : "📩 Request Fix from Supplier"}
              </button>
            )}
            {showApproveBtn && canApprove && (
              <button className="fb-btn fb-btn-solid" type="button" disabled={approving} onClick={approve}>
                {approving ? "Submitting…" : "Approve & Submit to MyInvois"}
              </button>
            )}
            {showRecordPaymentBtn && (
              <button
                className="fb-btn fb-btn-solid"
                type="button"
                onClick={() => {
                  setPayRef(record.invoice_no ? `PAY-${record.invoice_no}` : `PAY-${record.id}`);
                  setShowPaymentModal(true);
                }}
              >
                Record Payment
              </button>
            )}
          </div>
        </div>

        {needsAction && (
          <div
            className="fb-callout"
            style={{
              marginTop: "1rem",
              borderColor: "var(--chart-attn, #ef4444)",
              background: "rgba(239, 68, 68, 0.05)",
            }}
          >
            <div style={{ fontWeight: 700, color: "var(--chart-attn, #ef4444)", marginBottom: ".25rem", display: "flex", alignItems: "center", gap: ".4rem" }}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ width: "16px", height: "16px" }}><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
              Compliance Review Required
            </div>
            <div style={{ color: "var(--ink)" }}>{record.readiness_reason}</div>
          </div>
        )}

        {fixSuccessNotice && (
          <div className="fb-callout" style={{ marginTop: ".8rem", borderColor: "var(--chart-good, #10b981)", color: "var(--chart-good, #10b981)", background: "rgba(16, 185, 129, 0.05)" }}>
            <strong>✓ Fix request submitted:</strong> {fixSuccessNotice}. You can track or approve the outreach in the Approvals queue.
          </div>
        )}

        {fixErrorNotice && (
          <div className="fb-callout" style={{ marginTop: ".8rem", borderColor: "var(--chart-attn, #ef4444)", color: "var(--chart-attn, #ef4444)" }}>
            {fixErrorNotice}
          </div>
        )}
      </div>

      <div className="fb-detail-body">
        <div className="fb-detail-col">
          <h2>Extracted fields</h2>
          <p className="fb-sans" style={{ fontSize: ".68rem", color: "var(--ink-soft)", margin: "-.5rem 0 .8rem" }}>Fields captured from this invoice.</p>
          <div className="fb-settings-list">
            {fields.map((row) => (
              <div className="fb-settings-row" key={row[0]}>
                <span>{row[0]}</span>
                <span>{row[1]}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="fb-detail-col">
          <h2>Documents</h2>
          {record.document_available ? (
            <div style={{ display: "flex", flexDirection: "column", gap: ".6rem", alignItems: "flex-start" }}>
              <button
                className="fb-btn fb-btn-outline"
                type="button"
                disabled={documentState[record.id] === "loading"}
                onClick={() => openEinvoiceDocument(record.id, setDocumentState)}
              >
                {documentState[record.id] === "loading" ? "Opening…" : isPaid ? "View invoice (Paid)" : "View invoice"}
              </button>
              {isPaid && (
                <button
                  className="fb-btn fb-btn-outline"
                  type="button"
                  disabled={receiptState[record.id] === "loading"}
                  onClick={() => openEinvoiceReceipt(record.id, setReceiptState)}
                >
                  {receiptState[record.id] === "loading" ? "Opening receipt…" : receiptState[record.id] === "failed" ? "Retry receipt" : "View payment receipt"}
                </button>
              )}
            </div>
          ) : (
            <>
              <p className="fb-fine">No document on file for this invoice.</p>
              {PERSONAS[askRole].capabilities.manageEinvoiceReadiness && (
                <label className="fb-field-label" style={{ marginTop: ".5rem", maxWidth: "320px" }}>
                  Attach PDF
                  <input
                    className="fb-field-mock"
                    type="file"
                    accept="application/pdf"
                    disabled={attaching}
                    onChange={(e) => { const f = e.target.files?.[0]; if (f) void attachDocument(f); }}
                  />
                </label>
              )}
              {attachError && <div className="fb-fine" style={{ color: "var(--chart-attn)" }} role="alert">{attachError}</div>}
            </>
          )}
        </div>
      </div>

      {showUinPanel && (
        <div className="fb-uin-panel" style={{ maxWidth: "920px", margin: "1.4rem auto 0" }}>
          <img
            src={`https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=${encodeURIComponent(`https://myinvois.hasil.gov.my/${displayUin}`)}`}
            alt="MyInvois Verification QR Code"
            style={{ width: "64px", height: "64px", flex: "0 0 auto", borderRadius: "8px", border: "1px solid var(--line)", background: "#fff" }}
          />
          <div>
            <div className="fb-eyebrow" style={{ marginBottom: ".3rem" }}>Verified by LHDN MyInvois (Sandbox)</div>
            <div className="fb-uin-code">UIN {displayUin}</div>
            <div className="fb-sans" style={{ fontSize: ".68rem", color: "var(--ink-soft)", marginTop: ".3rem" }}>Validated and cryptographically signed by IRBM MyInvois &bull; Scan QR code to verify.</div>
          </div>
        </div>
      )}

      {showEditModal && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ background: "var(--card)", border: "1px solid var(--line)", borderRadius: "14px", padding: "1.5rem", maxWidth: "600px", width: "90%", maxHeight: "90vh", overflowY: "auto", boxShadow: "0 20px 50px -10px rgba(0,0,0,0.4)" }}>
            <h2 style={{ fontSize: "1.2rem", marginBottom: ".3rem" }}>Fix &amp; Edit Invoice Details</h2>
            <p className="fb-fine" style={{ marginBottom: "1rem" }}>
              Update invoice fields to resolve compliance issues and enable MyInvois validation.
            </p>

            <form onSubmit={saveEdit}>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: ".9rem", marginBottom: "1rem" }}>
                <label className="fb-field-label">
                  Supplier Name *
                  <input
                    className="fb-field-mock"
                    type="text"
                    required
                    value={editForm.supplier_name}
                    onChange={(e) => setEditForm({ ...editForm, supplier_name: e.target.value })}
                    style={{ width: "100%", marginTop: ".3rem", borderColor: !editForm.supplier_name.trim() ? "var(--chart-attn, #ef4444)" : undefined }}
                  />
                  {!editForm.supplier_name.trim() && <span className="fb-fine" style={{ color: "var(--chart-attn, #ef4444)" }}>Required</span>}
                </label>

                <label className="fb-field-label">
                  Supplier TIN *
                  <input
                    className="fb-field-mock"
                    type="text"
                    placeholder="e.g. C1234567890"
                    value={editForm.supplier_tin}
                    onChange={(e) => setEditForm({ ...editForm, supplier_tin: e.target.value })}
                    style={{ width: "100%", marginTop: ".3rem", borderColor: !editForm.supplier_tin.trim() ? "var(--chart-attn, #ef4444)" : undefined }}
                  />
                  {!editForm.supplier_tin.trim() ? (
                    <span className="fb-fine" style={{ color: "var(--chart-attn, #ef4444)" }}>Mandatory for MyInvois validation</span>
                  ) : (
                    <span className="fb-fine" style={{ color: "var(--chart-good, #10b981)" }}>✓ Compliant TIN</span>
                  )}
                </label>

                <label className="fb-field-label">
                  Buyer Name
                  <input
                    className="fb-field-mock"
                    type="text"
                    value={editForm.buyer_name}
                    onChange={(e) => setEditForm({ ...editForm, buyer_name: e.target.value })}
                    style={{ width: "100%", marginTop: ".3rem" }}
                  />
                </label>

                <label className="fb-field-label">
                  Invoice No.
                  <input
                    className="fb-field-mock"
                    type="text"
                    value={editForm.invoice_no}
                    onChange={(e) => setEditForm({ ...editForm, invoice_no: e.target.value })}
                    style={{ width: "100%", marginTop: ".3rem" }}
                  />
                </label>

                <label className="fb-field-label">
                  Issue Date
                  <input
                    className="fb-field-mock"
                    type="date"
                    value={editForm.issue_date}
                    onChange={(e) => setEditForm({ ...editForm, issue_date: e.target.value })}
                    style={{ width: "100%", marginTop: ".3rem" }}
                  />
                </label>

                <label className="fb-field-label">
                  Due Date
                  <input
                    className="fb-field-mock"
                    type="date"
                    value={editForm.due_date}
                    onChange={(e) => setEditForm({ ...editForm, due_date: e.target.value })}
                    style={{ width: "100%", marginTop: ".3rem" }}
                  />
                </label>

                <label className="fb-field-label">
                  Total Amount (RM) *
                  <input
                    className="fb-field-mock"
                    type="number"
                    step="0.01"
                    min="0.01"
                    required
                    value={editForm.total_amount}
                    onChange={(e) => setEditForm({ ...editForm, total_amount: e.target.value })}
                    style={{ width: "100%", marginTop: ".3rem", borderColor: !editForm.total_amount.trim() ? "var(--chart-attn, #ef4444)" : undefined }}
                  />
                </label>

                <label className="fb-field-label">
                  Currency
                  <input
                    className="fb-field-mock"
                    type="text"
                    value={editForm.currency}
                    onChange={(e) => setEditForm({ ...editForm, currency: e.target.value })}
                    style={{ width: "100%", marginTop: ".3rem" }}
                  />
                </label>

                <label className="fb-field-label">
                  Tax Type
                  <input
                    className="fb-field-mock"
                    type="text"
                    value={editForm.tax_type}
                    onChange={(e) => setEditForm({ ...editForm, tax_type: e.target.value })}
                    style={{ width: "100%", marginTop: ".3rem" }}
                  />
                </label>

                <label className="fb-field-label">
                  Tax Rate
                  <input
                    className="fb-field-mock"
                    type="text"
                    value={editForm.tax_rate}
                    onChange={(e) => setEditForm({ ...editForm, tax_rate: e.target.value })}
                    style={{ width: "100%", marginTop: ".3rem" }}
                  />
                </label>
              </div>

              {editError && <div className="fb-fine" style={{ color: "var(--chart-attn, #ef4444)", marginBottom: ".8rem" }} role="alert">{editError}</div>}

              <div style={{ display: "flex", gap: ".6rem", justifyContent: "flex-end" }}>
                <button className="fb-btn fb-btn-outline" type="button" disabled={savingEdit} onClick={() => setShowEditModal(false)}>Cancel</button>
                <button className="fb-btn fb-btn-solid" type="submit" disabled={savingEdit}>
                  {savingEdit ? "Saving Changes…" : "Save & Verify"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showPaymentModal && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ background: "var(--card)", border: "1px solid var(--line)", borderRadius: "14px", padding: "1.5rem", maxWidth: "420px", width: "90%", boxShadow: "0 20px 50px -10px rgba(0,0,0,0.4)" }}>
            <h2 style={{ fontSize: "1.1rem", marginBottom: ".4rem" }}>Record Payment Settlement</h2>
            <p className="fb-fine" style={{ marginBottom: "1rem" }}>Record payment for invoice <strong>{record.invoice_no || record.id}</strong> (RM {record.total_amount}).</p>
            
            <label className="fb-field-label" style={{ marginBottom: ".8rem", display: "block" }}>
              Payment Date
              <input className="fb-field-mock" type="date" value={payDate} onChange={(e) => setPayDate(e.target.value)} style={{ width: "100%", marginTop: ".3rem" }} />
            </label>
            
            <label className="fb-field-label" style={{ marginBottom: ".8rem", display: "block" }}>
              Payment Method
              <select className="fb-field-mock" value={payMethod} onChange={(e) => setPayMethod(e.target.value)} style={{ width: "100%", marginTop: ".3rem" }}>
                <option value="Bank Transfer">Bank Transfer</option>
                <option value="DuitNow / QR">DuitNow / QR</option>
                <option value="Credit / Debit Card">Credit / Debit Card</option>
                <option value="Cheque">Cheque</option>
                <option value="Cash">Cash</option>
              </select>
            </label>
            
            <label className="fb-field-label" style={{ marginBottom: "1.2rem", display: "block" }}>
              Payment Reference / Txn ID
              <input className="fb-field-mock" type="text" value={payRef} onChange={(e) => setPayRef(e.target.value)} placeholder="e.g. MBB-998822" style={{ width: "100%", marginTop: ".3rem" }} />
            </label>
            
            <div style={{ display: "flex", gap: ".6rem", justifyContent: "flex-end" }}>
              <button className="fb-btn fb-btn-outline" type="button" disabled={recordingPayment} onClick={() => setShowPaymentModal(false)}>Cancel</button>
              <button className="fb-btn fb-btn-solid" type="button" disabled={recordingPayment} onClick={submitPayment}>
                {recordingPayment ? "Recording…" : "Confirm Payment"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function EinvoiceDetail() {
  const { einvoices, currentEinvoiceId, approveEinvoiceById, markEinvoicePaidById, updateEinvoiceById, show, askRole } = useAppState();
  const [showPaymentModal, setShowPaymentModal] = useState(false);
  const [payDate, setPayDate] = useState(new Date().toISOString().slice(0, 10));
  const [payMethod, setPayMethod] = useState("Bank Transfer");
  const [payRef, setPayRef] = useState("");

  const [showEditModal, setShowEditModal] = useState(false);
  const [editForm, setEditForm] = useState({
    supplier_name: "",
    supplier_tin: "",
    buyer_name: "",
    invoice_no: "",
    issue_date: "",
    due_date: "",
    total_amount: "",
    currency: "MYR",
    tax_type: "SST",
    tax_rate: "6%",
  });
  const [requestingFix, setRequestingFix] = useState(false);
  const [fixSuccessNotice, setFixSuccessNotice] = useState("");

  if (currentEinvoiceId?.startsWith("real-")) {
    const recordId = Number(currentEinvoiceId.slice("real-".length));
    return <RealEinvoiceDetail key={recordId} recordId={recordId} />;
  }

  const inv = currentEinvoiceId ? einvoices[currentEinvoiceId] : null;

  if (!inv) return null;

  const isPaid = Boolean(inv.paid_at);
  const canApprove = PERSONAS[askRole].capabilities.approveEinvoiceSubmission;
  const canManage = PERSONAS[askRole].capabilities.manageEinvoiceReadiness;

  const getFieldVal = (name: string) => {
    const found = inv.fields.find(([k]) => k.toLowerCase().includes(name.toLowerCase()));
    return found ? found[1] : "";
  };

  const rawTin = getFieldVal("tin");
  const isTinMissing = !rawTin || rawTin.toLowerCase().includes("missing") || rawTin === "—";
  const needsAction = inv.status === "review" || isTinMissing;

  const showApproveBtn = inv.status !== "submitted" && inv.status !== "validated";
  const showRecordPaymentBtn = inv.status === "validated" && !isPaid && (canManage || canApprove);
  const showUinPanel = inv.status === "validated";
  const displayUin = inv.uin || ("MY29A" + inv.id.replace("-", "").toUpperCase());

  const openEdit = () => {
    const rawTin = getFieldVal("tin");
    const isTinMissing = rawTin.toLowerCase().includes("missing") || rawTin === "—";
    setEditForm({
      supplier_name: inv.supplier || getFieldVal("supplier name"),
      supplier_tin: isTinMissing ? "" : rawTin,
      buyer_name: getFieldVal("buyer name") || "FINBRAIN Sdn Bhd",
      invoice_no: getFieldVal("invoice no") || "",
      issue_date: getFieldVal("issue date") || inv.date,
      due_date: getFieldVal("due date") || "",
      total_amount: inv.amount.replace(/[^0-9.]/g, ""),
      currency: getFieldVal("currency") || "MYR",
      tax_type: "SST",
      tax_rate: "6%",
    });
    setShowEditModal(true);
  };

  const saveMockEdit = (e: React.FormEvent) => {
    e.preventDefault();
    const isTinProvided = Boolean(editForm.supplier_tin.trim());
    const updatedStatus = isTinProvided ? "pending" : inv.status;
    const numAmt = Number(editForm.total_amount || 0);
    const formattedAmount = `RM ${numAmt.toLocaleString("en-MY", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    const updatedFields: [string, string][] = [
      ["Supplier name", editForm.supplier_name.trim()],
      ["Supplier TIN", editForm.supplier_tin.trim() || "— missing —"],
      ["Buyer name", editForm.buyer_name.trim() || "FINBRAIN Sdn Bhd"],
      ["Invoice no.", editForm.invoice_no.trim() || "—"],
      ["Issue date", editForm.issue_date || inv.date],
      ["Currency", editForm.currency.trim() || "MYR"],
      ["Tax type / rate", `${editForm.tax_type.trim()} ${editForm.tax_rate.trim()}`.trim()],
      ["Total (incl. tax)", formattedAmount],
    ];
    const updatedCompliance: [string, string][] = [
      ...inv.compliance,
      ["Manual fix applied", `Invoice details updated by ${PERSONAS[askRole].label}. Missing compliance fields resolved; pending approval.`],
    ];
    updateEinvoiceById(inv.id, {
      supplier: editForm.supplier_name.trim(),
      amount: formattedAmount,
      status: updatedStatus,
      description: isTinProvided ? "Details verified and updated; ready for MyInvois approval." : inv.description,
      fields: updatedFields,
      compliance: updatedCompliance,
    });
    setShowEditModal(false);
  };

  const handleMockRequestFix = () => {
    setRequestingFix(true);
    setFixSuccessNotice("");
    setTimeout(() => {
      setRequestingFix(false);
      setFixSuccessNotice("Fix request sent to Approvals");
    }, 350);
  };

  return (
    <div className="fb-root fb-shell">
      <Sidebar backTo={() => show("einvoice")} backLabel="e-Invoicing" />
      <AppTopBar current="einvoice-detail" />

      <div className="fb-detail-header">
        <div className="fb-detail-header-top">
          <div>
            <div className="fb-eyebrow" style={{ marginBottom: ".5rem", display: "flex", alignItems: "center", gap: ".5rem" }}>
              <span>{FB_EINVOICE_STATUS_LABEL[inv.status]}</span>
              {isPaid && <span className="fb-status-pill is-active">Paid &bull; {inv.paid_at}</span>}
            </div>
            <h1>{inv.supplier} · {inv.amount}</h1>
            <p>{inv.description}</p>
          </div>
          <div style={{ display: "flex", gap: ".6rem", alignItems: "center", flexWrap: "wrap" }}>
            {needsAction && (
              <button className="fb-btn fb-btn-outline" type="button" onClick={openEdit}>
                ✏️ Fix &amp; Edit Details
              </button>
            )}
            {needsAction && (
              <button
                className="fb-btn fb-btn-outline"
                type="button"
                disabled={requestingFix || fixSuccessNotice !== ""}
                onClick={handleMockRequestFix}
              >
                {requestingFix ? "Sending request…" : fixSuccessNotice ? "✓ Fix Requested" : "📩 Request Fix from Supplier"}
              </button>
            )}
            {showApproveBtn && !needsAction && (
              <button
                className="fb-btn fb-btn-solid"
                type="button"
                onClick={() => approveEinvoiceById(inv.id)}
              >
                Approve &amp; Submit to MyInvois
              </button>
            )}
            {showRecordPaymentBtn && (
              <button
                className="fb-btn fb-btn-solid"
                type="button"
                onClick={() => {
                  setPayRef(`PAY-${inv.id}`);
                  setShowPaymentModal(true);
                }}
              >
                Record Payment
              </button>
            )}
          </div>
        </div>

        {needsAction && (
          <div
            className="fb-callout"
            style={{
              marginTop: "1rem",
              borderColor: "var(--chart-attn, #ef4444)",
              background: "rgba(239, 68, 68, 0.05)",
            }}
          >
            <div style={{ fontWeight: 700, color: "var(--chart-attn, #ef4444)", marginBottom: ".25rem", display: "flex", alignItems: "center", gap: ".4rem" }}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ width: "16px", height: "16px" }}><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
              Compliance Review Required
            </div>
            <div style={{ color: "var(--ink)" }}>
              Missing supplier Tax Identification Number (TIN). LHDN MyInvois requires a valid TIN to validate and digitally sign this invoice — approving is blocked until corrected.
            </div>
          </div>
        )}

        {fixSuccessNotice && (
          <div className="fb-callout" style={{ marginTop: ".8rem", borderColor: "var(--chart-good, #10b981)", color: "var(--chart-good, #10b981)", background: "rgba(16, 185, 129, 0.05)" }}>
            <strong>✓ Fix request submitted:</strong> {fixSuccessNotice}. You can track or approve the outreach in the Approvals queue.
          </div>
        )}
      </div>

      <div className="fb-detail-body">
        <div className="fb-detail-col">
          <h2>Extracted fields</h2>
          <p className="fb-sans" style={{ fontSize: ".68rem", color: "var(--ink-soft)", margin: "-.5rem 0 .8rem" }}>Showing 8 of the 55 mandatory MyInvois UBL fields.</p>
          <div className="fb-settings-list">
            {inv.fields.map((row) => {
              const isMissing = row[1].toLowerCase().includes("missing") || row[1] === "—";
              const isTin = row[0].toLowerCase().includes("tin");
              return (
                <div className="fb-settings-row" key={row[0]}>
                  <span>{row[0]}</span>
                  <span>
                    {isMissing && isTin ? (
                      <span className="fb-badge-warning" style={{ color: "var(--chart-attn, #ef4444)" }}>
                        Missing — Action Required
                      </span>
                    ) : isMissing ? (
                      <span className="fb-badge-warning" style={{ color: "var(--chart-attn, #ef4444)" }}>
                        Missing
                      </span>
                    ) : (
                      row[1]
                    )}
                  </span>
                </div>
              );
            })}
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
          <img
            src={`https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=${encodeURIComponent(`https://myinvois.hasil.gov.my/${displayUin}`)}`}
            alt="MyInvois Verification QR Code"
            style={{ width: "64px", height: "64px", flex: "0 0 auto", borderRadius: "8px", border: "1px solid var(--line)", background: "#fff" }}
          />
          <div>
            <div className="fb-eyebrow" style={{ marginBottom: ".3rem" }}>Verified by LHDN MyInvois (Sandbox)</div>
            <div className="fb-uin-code">UIN {displayUin}</div>
            <div className="fb-sans" style={{ fontSize: ".68rem", color: "var(--ink-soft)", marginTop: ".3rem" }}>Validated and cryptographically signed by IRBM MyInvois &bull; Scan QR code to verify.</div>
          </div>
        </div>
      )}

      {showEditModal && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ background: "var(--card)", border: "1px solid var(--line)", borderRadius: "14px", padding: "1.5rem", maxWidth: "600px", width: "90%", maxHeight: "90vh", overflowY: "auto", boxShadow: "0 20px 50px -10px rgba(0,0,0,0.4)" }}>
            <h2 style={{ fontSize: "1.2rem", marginBottom: ".3rem" }}>Fix &amp; Edit Invoice Details</h2>
            <p className="fb-fine" style={{ marginBottom: "1rem" }}>
              Update invoice fields to resolve compliance issues and enable MyInvois validation.
            </p>

            <form onSubmit={saveMockEdit}>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: ".9rem", marginBottom: "1rem" }}>
                <label className="fb-field-label">
                  Supplier Name *
                  <input
                    className="fb-field-mock"
                    type="text"
                    required
                    value={editForm.supplier_name}
                    onChange={(e) => setEditForm({ ...editForm, supplier_name: e.target.value })}
                    style={{ width: "100%", marginTop: ".3rem", borderColor: !editForm.supplier_name.trim() ? "var(--chart-attn, #ef4444)" : undefined }}
                  />
                  {!editForm.supplier_name.trim() && <span className="fb-fine" style={{ color: "var(--chart-attn, #ef4444)" }}>Required</span>}
                </label>

                <label className="fb-field-label">
                  Supplier TIN *
                  <input
                    className="fb-field-mock"
                    type="text"
                    placeholder="e.g. C1234567890"
                    value={editForm.supplier_tin}
                    onChange={(e) => setEditForm({ ...editForm, supplier_tin: e.target.value })}
                    style={{ width: "100%", marginTop: ".3rem", borderColor: !editForm.supplier_tin.trim() ? "var(--chart-attn, #ef4444)" : undefined }}
                  />
                  {!editForm.supplier_tin.trim() ? (
                    <span className="fb-fine" style={{ color: "var(--chart-attn, #ef4444)" }}>Mandatory for MyInvois validation</span>
                  ) : (
                    <span className="fb-fine" style={{ color: "var(--chart-good, #10b981)" }}>✓ Compliant TIN</span>
                  )}
                </label>

                <label className="fb-field-label">
                  Buyer Name
                  <input
                    className="fb-field-mock"
                    type="text"
                    value={editForm.buyer_name}
                    onChange={(e) => setEditForm({ ...editForm, buyer_name: e.target.value })}
                    style={{ width: "100%", marginTop: ".3rem" }}
                  />
                </label>

                <label className="fb-field-label">
                  Invoice No.
                  <input
                    className="fb-field-mock"
                    type="text"
                    value={editForm.invoice_no}
                    onChange={(e) => setEditForm({ ...editForm, invoice_no: e.target.value })}
                    style={{ width: "100%", marginTop: ".3rem" }}
                  />
                </label>

                <label className="fb-field-label">
                  Issue Date
                  <input
                    className="fb-field-mock"
                    type="text"
                    value={editForm.issue_date}
                    onChange={(e) => setEditForm({ ...editForm, issue_date: e.target.value })}
                    style={{ width: "100%", marginTop: ".3rem" }}
                  />
                </label>

                <label className="fb-field-label">
                  Due Date
                  <input
                    className="fb-field-mock"
                    type="text"
                    value={editForm.due_date}
                    onChange={(e) => setEditForm({ ...editForm, due_date: e.target.value })}
                    style={{ width: "100%", marginTop: ".3rem" }}
                  />
                </label>

                <label className="fb-field-label">
                  Total Amount (RM) *
                  <input
                    className="fb-field-mock"
                    type="number"
                    step="0.01"
                    min="0.01"
                    required
                    value={editForm.total_amount}
                    onChange={(e) => setEditForm({ ...editForm, total_amount: e.target.value })}
                    style={{ width: "100%", marginTop: ".3rem", borderColor: !editForm.total_amount.trim() ? "var(--chart-attn, #ef4444)" : undefined }}
                  />
                </label>

                <label className="fb-field-label">
                  Currency
                  <input
                    className="fb-field-mock"
                    type="text"
                    value={editForm.currency}
                    onChange={(e) => setEditForm({ ...editForm, currency: e.target.value })}
                    style={{ width: "100%", marginTop: ".3rem" }}
                  />
                </label>

                <label className="fb-field-label">
                  Tax Type
                  <input
                    className="fb-field-mock"
                    type="text"
                    value={editForm.tax_type}
                    onChange={(e) => setEditForm({ ...editForm, tax_type: e.target.value })}
                    style={{ width: "100%", marginTop: ".3rem" }}
                  />
                </label>

                <label className="fb-field-label">
                  Tax Rate
                  <input
                    className="fb-field-mock"
                    type="text"
                    value={editForm.tax_rate}
                    onChange={(e) => setEditForm({ ...editForm, tax_rate: e.target.value })}
                    style={{ width: "100%", marginTop: ".3rem" }}
                  />
                </label>
              </div>

              <div style={{ display: "flex", gap: ".6rem", justifyContent: "flex-end" }}>
                <button className="fb-btn fb-btn-outline" type="button" onClick={() => setShowEditModal(false)}>Cancel</button>
                <button className="fb-btn fb-btn-solid" type="submit">
                  Save &amp; Verify
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showPaymentModal && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ background: "var(--card)", border: "1px solid var(--line)", borderRadius: "14px", padding: "1.5rem", maxWidth: "420px", width: "90%", boxShadow: "0 20px 50px -10px rgba(0,0,0,0.4)" }}>
            <h2 style={{ fontSize: "1.1rem", marginBottom: ".4rem" }}>Record Payment Settlement</h2>
            <p className="fb-fine" style={{ marginBottom: "1rem" }}>Record payment for invoice <strong>{inv.id}</strong> ({inv.amount}).</p>
            
            <label className="fb-field-label" style={{ marginBottom: ".8rem", display: "block" }}>
              Payment Date
              <input className="fb-field-mock" type="date" value={payDate} onChange={(e) => setPayDate(e.target.value)} style={{ width: "100%", marginTop: ".3rem" }} />
            </label>
            
            <label className="fb-field-label" style={{ marginBottom: ".8rem", display: "block" }}>
              Payment Method
              <select className="fb-field-mock" value={payMethod} onChange={(e) => setPayMethod(e.target.value)} style={{ width: "100%", marginTop: ".3rem" }}>
                <option value="Bank Transfer">Bank Transfer</option>
                <option value="DuitNow / QR">DuitNow / QR</option>
                <option value="Credit / Debit Card">Credit / Debit Card</option>
                <option value="Cheque">Cheque</option>
                <option value="Cash">Cash</option>
              </select>
            </label>
            
            <label className="fb-field-label" style={{ marginBottom: "1.2rem", display: "block" }}>
              Payment Reference / Txn ID
              <input className="fb-field-mock" type="text" value={payRef} onChange={(e) => setPayRef(e.target.value)} placeholder="e.g. MBB-998822" style={{ width: "100%", marginTop: ".3rem" }} />
            </label>
            
            <div style={{ display: "flex", gap: ".6rem", justifyContent: "flex-end" }}>
              <button className="fb-btn fb-btn-outline" type="button" onClick={() => setShowPaymentModal(false)}>Cancel</button>
              <button
                className="fb-btn fb-btn-solid"
                type="button"
                onClick={() => {
                  markEinvoicePaidById(inv.id, payDate);
                  setShowPaymentModal(false);
                }}
              >
                Confirm Payment
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
