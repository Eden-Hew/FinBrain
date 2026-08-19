import { useEffect, useState } from "react";
import { useAppState, submitterName } from "../lib/appState";
import { Sidebar, AppTopBar } from "../components/Nav";
import { PERSONAS } from "../lib/personas";
import { FB_EINVOICE_STATUS_LABEL } from "../data/sampleData";
import {
  approveEinvoiceRecord,
  fetchEinvoiceRecord,
  uploadEinvoiceDocument,
  type EInvoiceApiRecord,
} from "../api/client";
import { openEinvoiceDocument } from "./Einvoice";

function RealEinvoiceDetail({ recordId }: { recordId: number }) {
  const { askRole, show } = useAppState();
  const [record, setRecord] = useState<EInvoiceApiRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [approving, setApproving] = useState(false);
  const [documentState, setDocumentState] = useState<Record<number, "idle" | "loading" | "failed">>({});
  const [attaching, setAttaching] = useState(false);
  const [attachError, setAttachError] = useState("");

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
      .catch((err) => { setError(err instanceof Error ? err.message : "Failed to load invoice."); setLoading(false); });
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

  if (loading) return <div className="fb-root fb-shell"><Sidebar backTo={() => show("einvoice")} backLabel="e-Invoicing" /><AppTopBar current="einvoice-detail" /><div className="fb-callout">Loading invoice…</div></div>;
  if (error || !record) return <div className="fb-root fb-shell"><Sidebar backTo={() => show("einvoice")} backLabel="e-Invoicing" /><AppTopBar current="einvoice-detail" /><div className="fb-callout" style={{ borderColor: "var(--chart-attn)", color: "var(--chart-attn)" }}>{error || "Invoice not found."}</div></div>;

  const canApprove = PERSONAS[askRole].capabilities.approveEinvoiceSubmission;
  const showApproveBtn = record.status === "pending";
  const showUinPanel = record.status === "validated";

  const fields: [string, string][] = [
    ["Supplier", record.supplier_name],
    ["Supplier TIN", record.supplier_tin ?? "—"],
    ["Buyer", record.buyer_name ?? "—"],
    ["Invoice No.", record.invoice_no ?? "—"],
    ["Issue date", record.issue_date ?? "—"],
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
            <div className="fb-eyebrow" style={{ marginBottom: ".5rem" }}>{FB_EINVOICE_STATUS_LABEL[record.status]}</div>
            <h1>{record.supplier_name} · RM {record.total_amount}</h1>
            <p>{record.readiness_reason}</p>
          </div>
          {showApproveBtn && canApprove && (
            <button className="fb-btn fb-btn-solid" type="button" disabled={approving} onClick={approve}>
              {approving ? "Submitting…" : "Approve & Submit to MyInvois"}
            </button>
          )}
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
          <h2>Document</h2>
          {record.document_available ? (
            <button
              className="fb-btn fb-btn-outline"
              type="button"
              disabled={documentState[record.id] === "loading"}
              onClick={() => openEinvoiceDocument(record.id, setDocumentState)}
            >
              {documentState[record.id] === "loading" ? "Opening…" : documentState[record.id] === "failed" ? "Retry" : "View invoice"}
            </button>
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
            src={`https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=${encodeURIComponent(`https://myinvois.hasil.gov.my/${record.uin ?? "MY29A000000"}`)}`}
            alt="MyInvois Verification QR Code"
            style={{ width: "64px", height: "64px", flex: "0 0 auto", borderRadius: "8px", border: "1px solid var(--line)", background: "#fff" }}
          />
          <div>
            <div className="fb-eyebrow" style={{ marginBottom: ".3rem" }}>Verified by LHDN MyInvois (Sandbox)</div>
            <div className="fb-uin-code">UIN {record.uin}</div>
            <div className="fb-sans" style={{ fontSize: ".68rem", color: "var(--ink-soft)", marginTop: ".3rem" }}>Validated and cryptographically signed by IRBM MyInvois &bull; Scan QR code to verify.</div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function EinvoiceDetail() {
  const { einvoices, currentEinvoiceId, approveEinvoiceById, show } = useAppState();

  if (currentEinvoiceId?.startsWith("real-")) {
    const recordId = Number(currentEinvoiceId.slice("real-".length));
    return <RealEinvoiceDetail key={recordId} recordId={recordId} />;
  }

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
          <img
            src={`https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=${encodeURIComponent(`https://myinvois.hasil.gov.my/${inv.uin ?? "MY29A000000"}`)}`}
            alt="MyInvois Verification QR Code"
            style={{ width: "64px", height: "64px", flex: "0 0 auto", borderRadius: "8px", border: "1px solid var(--line)", background: "#fff" }}
          />
          <div>
            <div className="fb-eyebrow" style={{ marginBottom: ".3rem" }}>Verified by LHDN MyInvois (Sandbox)</div>
            <div className="fb-uin-code">UIN {inv.uin}</div>
            <div className="fb-sans" style={{ fontSize: ".68rem", color: "var(--ink-soft)", marginTop: ".3rem" }}>Validated and cryptographically signed by IRBM MyInvois &bull; Scan QR code to verify.</div>
          </div>
        </div>
      )}
    </div>
  );
}
