import { useState, type FormEvent } from "react";
import { ingestRecord, type IngestionResponse, type Role } from "../api/client";

const SOURCE_OPTIONS = [
  { value: "manual", label: "Manual entry" },
  { value: "whatsapp", label: "WhatsApp" },
  { value: "email", label: "Email" },
  { value: "bank_csv", label: "Bank CSV" },
  { value: "document", label: "Document / OCR" },
];

const RECORD_OPTIONS = [
  { value: "customer_note", label: "Customer note" },
  { value: "customer_message", label: "Customer message" },
  { value: "transaction", label: "Transaction" },
  { value: "document_note", label: "Document note" },
];

function newRecordId() {
  return `manual:${crypto.randomUUID()}`;
}

export function IngestionPanel({ role }: { role: Role }) {
  const [sourceRecordId, setSourceRecordId] = useState(newRecordId);
  const [sourceSystem, setSourceSystem] = useState("manual");
  const [recordType, setRecordType] = useState("customer_note");
  const [occurredAt, setOccurredAt] = useState("");
  const [channel, setChannel] = useState("manual_entry");
  const [reference, setReference] = useState("");
  const [text, setText] = useState("");
  const [refresh, setRefresh] = useState(false);
  const [submittedText, setSubmittedText] = useState("");
  const [result, setResult] = useState<IngestionResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  function reset() {
    setSourceRecordId(newRecordId());
    setOccurredAt("");
    setReference("");
    setText("");
    setRefresh(false);
    setSubmittedText("");
    setResult(null);
    setError("");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!text.trim() || loading) return;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const response = await ingestRecord({
        role,
        source_record_id: sourceRecordId.trim(),
        source_system: sourceSystem,
        record_type: recordType,
        text: text.trim(),
        occurred_at: occurredAt ? new Date(occurredAt).toISOString() : null,
        metadata: {
          ...(channel.trim() ? { channel: channel.trim() } : {}),
          ...(reference.trim() ? { reference: reference.trim() } : {}),
        },
        refresh,
      });
      setSubmittedText(text.trim());
      setResult(response);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Ingestion failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="card ingestion-card" aria-label="Protected record ingestion">
      <div className="card-heading">
        <div>
          <span className="eyebrow">Protected ingestion</span>
          <h2>Add a business record</h2>
        </div>
        <span className="demo-badge">Proof of concept</span>
      </div>

      <div className="demo-notice">
        The selected <strong>{role.replaceAll("_", " ")}</strong> role is trusted for this demo.
        Raw text goes only to FinBrain's backend; Gemini receives the tokenized version.
      </div>

      <form className="ingestion-form" onSubmit={submit}>
        <div className="form-grid">
          <label>
            <span>Source</span>
            <select value={sourceSystem} onChange={(event) => setSourceSystem(event.target.value)}>
              {SOURCE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Record type</span>
            <select value={recordType} onChange={(event) => setRecordType(event.target.value)}>
              {RECORD_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          <label className="wide-field">
            <span>Opaque record ID</span>
            <input
              value={sourceRecordId}
              onChange={(event) => setSourceRecordId(event.target.value)}
              required
              pattern="[A-Za-z0-9:_.-]+"
            />
            <small>Use an internal ID, never a customer name, phone number, or email.</small>
          </label>
          <label>
            <span>Occurred at</span>
            <input
              type="datetime-local"
              value={occurredAt}
              onChange={(event) => setOccurredAt(event.target.value)}
            />
          </label>
          <label>
            <span>Channel metadata</span>
            <input value={channel} onChange={(event) => setChannel(event.target.value)} />
          </label>
          <label className="wide-field">
            <span>Reference metadata</span>
            <input
              value={reference}
              onChange={(event) => setReference(event.target.value)}
              placeholder="Optional; sensitive values will also be tokenized"
            />
          </label>
          <label className="wide-field">
            <span>Source text</span>
            <textarea
              rows={7}
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder="Paste a customer message, transaction note, email, or extracted document text..."
              required
            />
          </label>
        </div>

        <div className="ingestion-actions">
          <label className="check-field">
            <input
              type="checkbox"
              checked={refresh}
              onChange={(event) => setRefresh(event.target.checked)}
            />
            Reprocess this ID
          </label>
          <div>
            {result && (
              <button type="button" className="secondary-button" onClick={reset}>New record</button>
            )}
            <button type="submit" className="primary-button" disabled={loading || !text.trim()}>
              {loading ? "Protecting and summarizing..." : "Protect and ingest"}
            </button>
          </div>
        </div>
      </form>

      {error && <div className="ingestion-error" role="alert">{error}</div>}

      {result && (
        <div className="ingestion-result" aria-live="polite">
          <div className="result-heading">
            <div>
              <span className={`status-pill ${result.processing_status}`}>
                {result.processing_status.replaceAll("_", " ")}
              </span>
              <strong>
                {result.created
                  ? "New record stored"
                  : result.refreshed
                    ? "Record refreshed"
                    : "Existing record unchanged"}
              </strong>
            </div>
            <small>{result.enrichment_mode ?? "enrichment pending"} · {result.authorization_mode}</small>
          </div>
          <div className="comparison-grid">
            <article>
              <span>User submitted</span>
              <p>{submittedText}</p>
            </article>
            <article className="protected-output">
              <span>Gemini and Supabase receive</span>
              <p>{result.content_text}</p>
            </article>
          </div>
          <div className="summary-output">
            <span>Protected summary</span>
            <p>{result.summary ?? "Summary is pending; the protected source was retained safely."}</p>
          </div>
        </div>
      )}
    </section>
  );
}
