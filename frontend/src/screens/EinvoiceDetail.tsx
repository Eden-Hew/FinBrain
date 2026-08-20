import { useEffect, useState } from "react";
import { useAppState, submitterName } from "../lib/appState";
import { Sidebar, AppTopBar } from "../components/Nav";
import { PERSONAS } from "../lib/personas";
import { FB_EINVOICE_STATUS_LABEL } from "../data/sampleData";
import {
  approveEinvoiceRecord,
  fetchEinvoiceRecord,
  friendlyLoadError,
  markEinvoicePaid,
  uploadEinvoiceDocument,
  type EInvoiceApiRecord,
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

  if (loading) return <div className="fb-root fb-shell"><Sidebar backTo={() => show("einvoice")} backLabel="e-Invoicing" /><AppTopBar current="einvoice-detail" /><div className="fb-callout">Loading invoice…</div></div>;
  if (error || !record) return <div className="fb-root fb-shell"><Sidebar backTo={() => show("einvoice")} backLabel="e-Invoicing" /><AppTopBar current="einvoice-detail" /><div className="fb-callout" style={{ borderColor: "var(--chart-attn)", color: "var(--chart-attn)" }}>{error || "Invoice not found."}</div></div>;

  const canApprove = PERSONAS[askRole].capabilities.approveEinvoiceSubmission;
  const canManage = PERSONAS[askRole].capabilities.manageEinvoiceReadiness;
  const showApproveBtn = record.status === "pending";
  const isPaid = Boolean(record.paid_at);
  const showRecordPaymentBtn = record.status === "validated" && !isPaid && (canManage || canApprove);
  const showUinPanel = record.status === "validated";
  const displayUin = record.uin || ("MY29A" + (record.invoice_no ? record.invoice_no.replace(/[^A-Za-z0-9]/g, "").slice(-6).toUpperCase() : record.id));

  const fields: [string, string][] = [
    ["Supplier", record.supplier_name],
    ["Supplier TIN", record.supplier_tin ?? "—"],
    ["Buyer", record.buyer_name ?? "—"],
    ["Invoice No.", record.invoice_no ?? "—"],
    ["Issue date", record.issue_date ?? "—"],
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
          <div style={{ display: "flex", gap: ".6rem", alignItems: "center" }}>
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
        {record.status === "review" && (
          <div className="fb-callout" style={{ marginTop: "1rem" }}>
            <strong>This needs attention, not just approval:</strong> the flagged field above has to be corrected before this can move forward — approving is blocked until then.
          </div>
        )}
      </div>

      <div className="fb-detail-body">
        <div className="fb-detail-col">
          <h2>Extracted fields</h2>
          <p className="fb-sans" style={{ fontSize: ".68rem", color: "var(--ink-soft)", margin: "-.5rem 0 .8rem" }}>Fields captured from this invoice.</p>
          <div className="fb-settings-list">
            {fields.map((row) => <div className="fb-settings-row" key={row[0]}><span>{row[0]}</span><span>{row[1]}</span></div>)}
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
  const { einvoices, currentEinvoiceId, approveEinvoiceById, markEinvoicePaidById, show, askRole } = useAppState();
  const [showPaymentModal, setShowPaymentModal] = useState(false);
  const [payDate, setPayDate] = useState(new Date().toISOString().slice(0, 10));
  const [payMethod, setPayMethod] = useState("Bank Transfer");
  const [payRef, setPayRef] = useState("");

  if (currentEinvoiceId?.startsWith("real-")) {
    const recordId = Number(currentEinvoiceId.slice("real-".length));
    return <RealEinvoiceDetail key={recordId} recordId={recordId} />;
  }

  const inv = currentEinvoiceId ? einvoices[currentEinvoiceId] : null;

  if (!inv) return null;

  const isPaid = Boolean(inv.paid_at);
  const canApprove = PERSONAS[askRole].capabilities.approveEinvoiceSubmission;
  const canManage = PERSONAS[askRole].capabilities.manageEinvoiceReadiness;
  const showApproveBtn = inv.status !== "submitted" && inv.status !== "validated";
  const showRecordPaymentBtn = inv.status === "validated" && !isPaid && (canManage || canApprove);
  const showUinPanel = inv.status === "validated";
  const displayUin = inv.uin || ("MY29A" + inv.id.replace("-", "").toUpperCase());

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
          <div style={{ display: "flex", gap: ".6rem", alignItems: "center" }}>
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
