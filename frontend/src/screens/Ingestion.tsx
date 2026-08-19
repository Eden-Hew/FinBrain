import { useEffect, useRef, useState, type FormEvent } from "react";
import { useI18n } from "../lib/i18n";
import { Sidebar, AppTopBar } from "../components/Nav";
import { PersonaSelector } from "../components/PersonaSelector";
import { useAppState } from "../lib/appState";
import { PERSONAS } from "../lib/personas";
import {
  fetchEmailRecords,
  fetchEmailStatus,
  fetchTelegramRecords,
  fetchTelegramStatus,
  commitUpload,
  ingestRecord,
  previewUpload,
  syncEmail,
  type EmailIntegrationStatus,
  type IngestionResponse,
  type ProcessingStatus,
  type ProtectedIngestionRecord,
  type TelegramIntegrationStatus,
  type UploadPreviewResponse,
} from "../api/client";

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

function wordDiff(raw: string, protectedText: string) {
  const a = raw.split(/(\s+)/);
  const b = protectedText.split(/(\s+)/);
  const m = a.length, n = b.length;
  const dp: number[][] = Array.from({ length: m + 1 }, () => new Array<number>(n + 1).fill(0));
  for (let i = m - 1; i >= 0; i--) {
    for (let j = n - 1; j >= 0; j--) {
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const rawTokens: { text: string; changed: boolean }[] = [];
  const protectedTokens: { text: string; changed: boolean }[] = [];
  let i = 0, j = 0;
  while (i < m && j < n) {
    if (a[i] === b[j]) { rawTokens.push({ text: a[i], changed: false }); protectedTokens.push({ text: b[j], changed: false }); i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) { rawTokens.push({ text: a[i], changed: true }); i++; }
    else { protectedTokens.push({ text: b[j], changed: true }); j++; }
  }
  while (i < m) { rawTokens.push({ text: a[i], changed: true }); i++; }
  while (j < n) { protectedTokens.push({ text: b[j], changed: true }); j++; }
  return { rawTokens, protectedTokens };
}

function DiffText({ tokens, mode }: { tokens: { text: string; changed: boolean }[]; mode: "removed" | "added" }) {
  return (
    <>
      {tokens.map((token, i) => (
        token.changed
          ? <mark key={i} className={"fb-diff-mark is-" + mode}>{token.text}</mark>
          : <span key={i}>{token.text}</span>
      ))}
    </>
  );
}

function ProtectedFilePanel() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<UploadPreviewResponse | null>(null);
  const [state, setState] = useState<"idle" | "previewing" | "protected" | "committing" | "done">("idle");
  const [message, setMessage] = useState("");

  const clear = () => {
    setFile(null);
    setPreview(null);
    setState("idle");
    setMessage("");
    if (inputRef.current) inputRef.current.value = "";
  };

  const select = async (selected: File | undefined) => {
    if (!selected) return;
    setFile(selected);
    setPreview(null);
    setMessage("");
    setState("previewing");
    try {
      setPreview(await previewUpload(selected));
      setState("protected");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Preview failed.");
      setState("idle");
    }
  };

  const commit = async () => {
    if (!file || !preview) return;
    setState("committing");
    setMessage("");
    try {
      const result = await commitUpload(file, preview.preview_digest);
      setMessage(`${result.ready_rows} of ${result.valid_rows} protected source(s) are ready.`);
      setFile(null);
      setState("done");
      if (inputRef.current) inputRef.current.value = "";
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Ingestion failed.");
      setState("protected");
    }
  };

  return (
    <section className="fb-upload-preview" style={{ margin: "0 0 1.4rem", maxWidth: "920px" }}>
      <div className="fb-upload-preview-head">
        <div>
          <strong>Protected file upload</strong>
          <div className="fb-fine">Preview TXT, Markdown, invoice CSV, EML, PDF, or DOCX before persistence.</div>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept=".txt,.md,.csv,.eml,.pdf,.docx,.png,.jpg,.jpeg,.webp,.bmp,.tiff"
          onChange={(event) => select(event.target.files?.[0])}
        />
      </div>
      {file && <div className="fb-fine">{file.type || "Unknown type"} · {(file.size / 1024).toFixed(1)} KB · {state}</div>}
      {preview && (
        <>
          <div className="fb-upload-stats">
            <span>{preview.schema_name ?? preview.input_kind}</span>
            <span>{preview.valid_rows} valid</span>
            <span>{preview.invalid_rows} invalid</span>
          </div>
          <div className="fb-upload-samples">
            {preview.protected_preview.slice(0, 3).map((item) => (
              <div key={item.source_record_id}>{item.content_text}</div>
            ))}
          </div>
          {preview.valid_rows > Math.min(3, preview.protected_preview.length) && (
            <div className="fb-fine">
              Showing {Math.min(3, preview.protected_preview.length)} of {preview.valid_rows} protected rows<br />
              + {preview.valid_rows - Math.min(3, preview.protected_preview.length)} additional row{preview.valid_rows - Math.min(3, preview.protected_preview.length) === 1 ? "" : "s"} will be ingested
            </div>
          )}
          <div className="fb-upload-actions">
            <button className="fb-btn fb-btn-solid" type="button" onClick={commit} disabled={state === "committing"}>
              {state === "committing" ? "Ingesting..." : "Protect and ingest"}
            </button>
            <button className="fb-btn fb-btn-outline" type="button" onClick={clear}>Cancel</button>
          </div>
        </>
      )}
      {message && <div className="fb-fine" role="status">{message}</div>}
      {state === "done" && <button className="fb-btn fb-btn-outline" type="button" onClick={clear}>Upload another</button>}
    </section>
  );
}

const STATUS_PILL_CLASS: Record<ProcessingStatus, string> = {
  ready: "is-active",
  protected: "",
  failed_enrichment: "is-review",
};

function newRecordId() {
  return `manual:${crypto.randomUUID()}`;
}

function shortReference(sourceRecordId: string) {
  const prefix = sourceRecordId.startsWith("email:") ? "EM" : "TG";
  return `${prefix}-${sourceRecordId.split(":").at(-1)?.slice(0, 6).toUpperCase() ?? "RECORD"}`;
}

function EmailCapturePanel() {
  const [status, setStatus] = useState<EmailIntegrationStatus | null>(null);
  const [records, setRecords] = useState<ProtectedIngestionRecord[]>([]);
  const [error, setError] = useState("");
  const [syncing, setSyncing] = useState(false);
  const [lastSync, setLastSync] = useState<Date | null>(null);

  const refresh = async () => {
    const [nextStatus, nextRecords] = await Promise.all([
      fetchEmailStatus(),
      fetchEmailRecords(),
    ]);
    setStatus(nextStatus);
    setRecords(nextRecords);
    setLastSync(new Date());
  };

  useEffect(() => {
    let active = true;
    const poll = async () => {
      try {
        const [nextStatus, nextRecords] = await Promise.all([
          fetchEmailStatus(),
          fetchEmailRecords(),
        ]);
        if (!active) return;
        setStatus(nextStatus);
        setRecords(nextRecords);
        setLastSync(new Date());
        setError("");
      } catch {
        if (active) setError("Email integration status is temporarily unavailable.");
      }
    };
    void poll();
    const timer = window.setInterval(poll, 5000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  const runSync = async () => {
    setSyncing(true);
    setError("");
    try {
      await syncEmail();
      await refresh();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Email sync failed.");
    } finally {
      setSyncing(false);
    }
  };

  return (
    <section style={{ marginBottom: "2rem" }} aria-labelledby="email-capture-title">
      <div className="fb-answer-card" style={{ marginBottom: "1rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap" }}>
          <div>
            <div className="fb-eyebrow">Connected source</div>
            <h2 id="email-capture-title" style={{ margin: ".35rem 0" }}>Email integration</h2>
            <p className="fb-fine" style={{ maxWidth: "650px" }}>
              Read-only IMAP synchronization converts email and supported attachments into protected records.
            </p>
          </div>
          <div style={{ textAlign: "right" }}>
            <span className={"fb-status-pill " + (status?.status === "healthy" ? "is-active" : "is-review")}>
              <span className="fb-status-dot"></span>{status?.status.replaceAll("_", " ") ?? "checking"}
            </span>
            <div className="fb-fine" style={{ marginTop: ".5rem" }}>
              {status?.folder_name ?? "INBOX"} · UID {status?.last_uid ?? 0}
            </div>
            <div className="fb-live-indicator">
              <span className="fb-live-dot" aria-hidden="true" />
              Polling every 5s · synced {lastSync ? lastSync.toLocaleTimeString() : "—"}
            </div>
            <button
              type="button"
              className="fb-btn fb-btn-outline"
              style={{ marginTop: ".6rem" }}
              disabled={!status?.configured || syncing}
              onClick={runSync}
            >
              {syncing ? "Synchronizing…" : "Sync now"}
            </button>
          </div>
        </div>
        {error && <div role="status" className="fb-fine" style={{ color: "var(--chart-attn)", marginTop: ".7rem" }}>{error}</div>}
      </div>
      <div className="fb-eyebrow" style={{ marginBottom: ".7rem" }}>Recent email records</div>
      {records.length === 0 ? (
        <div className="fb-callout">No protected email records yet. Configure IMAP and run a synchronization.</div>
      ) : (
        <div style={{ display: "grid", gap: ".65rem" }}>
          {records.map((record) => (
            <article className="fb-answer-card" key={record.source_record_id} style={{ padding: "1rem 1.1rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: ".8rem", flexWrap: "wrap" }}>
                <strong className="fb-sans">{shortReference(record.source_record_id)} · email</strong>
                <span className={"fb-status-pill " + STATUS_PILL_CLASS[record.processing_status]}>
                  <span className="fb-status-dot"></span>{record.processing_status.replaceAll("_", " ")}
                </span>
              </div>
              <p className="fb-fine" style={{ margin: ".65rem 0 0", overflowWrap: "anywhere" }}>
                {record.summary ?? record.content_excerpt}
              </p>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function TelegramCapturePanel() {
  const [status, setStatus] = useState<TelegramIntegrationStatus | null>(null);
  const [records, setRecords] = useState<ProtectedIngestionRecord[]>([]);
  const [error, setError] = useState("");
  const [lastSync, setLastSync] = useState<Date | null>(null);

  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const [nextStatus, nextRecords] = await Promise.all([
          fetchTelegramStatus(),
          fetchTelegramRecords(),
        ]);
        if (!active) return;
        setStatus(nextStatus);
        setRecords(nextRecords);
        setLastSync(new Date());
        setError("");
      } catch {
        if (active) setError("Telegram integration status is temporarily unavailable.");
      }
    };
    void refresh();
    const timer = window.setInterval(refresh, 3000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  const statusLabel = status?.status.replaceAll("_", " ") ?? "checking";
  return (
    <section style={{ marginBottom: "2rem" }} aria-labelledby="telegram-capture-title">
      <div className="fb-answer-card" style={{ marginBottom: "1rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap" }}>
          <div>
            <div className="fb-eyebrow">Remote capture</div>
            <h2 id="telegram-capture-title" style={{ margin: ".35rem 0" }}>Telegram integration</h2>
            <p className="fb-fine" style={{ maxWidth: "650px" }}>
              Capture records from a private Telegram chat. FinBrain stores and enriches only protected content.
            </p>
          </div>
          <div style={{ textAlign: "right" }}>
            <span className={"fb-status-pill " + (status?.status === "healthy" ? "is-active" : "is-review")}>
              <span className="fb-status-dot"></span>{statusLabel}
            </span>
            <div className="fb-fine" style={{ marginTop: ".5rem" }}>
              {status?.mode ?? "polling"} · detector {status?.detector_ready ? "ready" : "not ready"}
            </div>
            <div className="fb-live-indicator">
              <span className="fb-live-dot" aria-hidden="true" />
              Polling every 3s · synced {lastSync ? lastSync.toLocaleTimeString() : "—"}
            </div>
          </div>
        </div>
        {error && <div role="status" className="fb-fine" style={{ color: "var(--chart-attn)", marginTop: ".7rem" }}>{error}</div>}
      </div>

      <div className="fb-eyebrow" style={{ marginBottom: ".7rem" }}>Recent Telegram records</div>
      {records.length === 0 ? (
        <div className="fb-callout">No Telegram records yet. Open the bot, run /capture, and confirm a protected record.</div>
      ) : (
        <div style={{ display: "grid", gap: ".65rem" }}>
          {records.map((record) => (
            <article className="fb-answer-card" key={record.source_record_id} style={{ padding: "1rem 1.1rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: ".8rem", flexWrap: "wrap" }}>
                <strong className="fb-sans">{shortReference(record.source_record_id)} · {(record.record_type ?? "record").replaceAll("_", " ")}</strong>
                <span className={"fb-status-pill " + STATUS_PILL_CLASS[record.processing_status]}>
                  <span className="fb-status-dot"></span>{record.processing_status.replaceAll("_", " ")}
                </span>
              </div>
              <p className="fb-fine" style={{ margin: ".65rem 0 0", overflowWrap: "anywhere" }}>
                {record.summary ?? record.content_excerpt}
              </p>
              {record.structured_summary && (
                <div className="fb-fine" style={{ marginTop: ".55rem" }}>
                  {record.structured_summary.category ?? "uncategorized"} · {record.structured_summary.priority ?? "unknown"} priority
                  {record.structured_summary.action_required ? " · action required" : ""}
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

export default function Ingestion() {
  const { t } = useI18n();
  const { askRole: role } = useAppState();
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
  const [manualOpen, setManualOpen] = useState(false);

  const reset = () => {
    setSourceRecordId(newRecordId());
    setOccurredAt("");
    setReference("");
    setText("");
    setRefresh(false);
    setSubmittedText("");
    setResult(null);
    setError("");
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!text.trim() || loading) return;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const response = await ingestRecord({
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
  };

  return (
    <div className="fb-root fb-shell">
      <Sidebar current="ingestion" />
      <AppTopBar current="ingestion" />

      <header className="fb-app-header">
        <h1>{t("ingestion.title")}</h1>
        <p>{t("ingestion.desc")}</p>
      </header>

      <div className="fb-page-body">
        <TelegramCapturePanel />
        <EmailCapturePanel />
        <div className="fb-callout">
          The selected <strong>{PERSONAS[role].label}</strong> role is trusted for this demo.
          Raw text goes only to FinBrain's backend; AI services and Supabase receive only protected content.
        </div>

        <PersonaSelector />

        <ProtectedFilePanel />

        <button className="fb-link-toggle" type="button" onClick={() => setManualOpen((v) => !v)} aria-expanded={manualOpen} style={{ marginBottom: manualOpen ? "1rem" : "2rem" }}>
          <span className={"fb-link-toggle-caret" + (manualOpen ? " is-open" : "")}>▸</span>
          Add a record manually (power-user / testing)
        </button>

        {manualOpen && (
        <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: ".9rem", maxWidth: "760px", marginBottom: "2rem" }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "1rem" }}>
            <label className="fb-field-label">Source
              <select className="fb-field-mock" value={sourceSystem} onChange={(e) => setSourceSystem(e.target.value)}>
                {SOURCE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </label>
            <label className="fb-field-label">Record type
              <select className="fb-field-mock" value={recordType} onChange={(e) => setRecordType(e.target.value)}>
                {RECORD_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </label>
            <label className="fb-field-label" style={{ gridColumn: "1 / -1" }}>Opaque record ID
              <input
                className="fb-field-mock"
                value={sourceRecordId}
                onChange={(e) => setSourceRecordId(e.target.value)}
                required
                pattern="[A-Za-z0-9:_.\-]+"
              />
              <span className="fb-fine">Use an internal ID, never a customer name, phone number, or email.</span>
            </label>
            <label className="fb-field-label">Occurred at
              <input className="fb-field-mock" type="datetime-local" value={occurredAt} onChange={(e) => setOccurredAt(e.target.value)} />
            </label>
            <label className="fb-field-label">Channel metadata
              <input className="fb-field-mock" value={channel} onChange={(e) => setChannel(e.target.value)} />
            </label>
            <label className="fb-field-label" style={{ gridColumn: "1 / -1" }}>Reference metadata
              <input className="fb-field-mock" value={reference} onChange={(e) => setReference(e.target.value)} placeholder="Optional; sensitive values will also be tokenized" />
            </label>
            <label className="fb-field-label" style={{ gridColumn: "1 / -1" }}>Source text
              <textarea
                className="fb-field-mock"
                rows={7}
                style={{ resize: "vertical", lineHeight: 1.5 }}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Paste a customer message, transaction note, email, or extracted document text..."
                required
              />
            </label>
          </div>

          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap" }}>
            <label className="fb-sans" style={{ display: "inline-flex", alignItems: "center", gap: ".5rem", fontSize: ".75rem", color: "var(--ink-soft)" }}>
              <input type="checkbox" checked={refresh} onChange={(e) => setRefresh(e.target.checked)} />
              Reprocess this ID
            </label>
            <div style={{ display: "flex", gap: ".6rem" }}>
              {result && <button type="button" className="fb-btn fb-btn-outline" onClick={reset}>New record</button>}
              <button type="submit" className="fb-btn fb-btn-solid" disabled={loading || !text.trim()}>
                {loading ? "Protecting and summarizing..." : "Protect and ingest"}
              </button>
            </div>
          </div>
        </form>
        )}

        {error && (
          <div className="fb-callout" style={{ borderColor: "var(--chart-attn)", color: "var(--chart-attn)", marginTop: "1.2rem" }} role="alert">
            {error}
          </div>
        )}

        {result && (
          <div style={{ marginTop: "1.6rem", maxWidth: "920px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: ".8rem", flexWrap: "wrap", marginBottom: "1rem" }}>
              <span className={"fb-status-pill " + STATUS_PILL_CLASS[result.processing_status]}>
                <span className="fb-status-dot"></span>{result.processing_status.replaceAll("_", " ")}
              </span>
              <strong className="fb-sans" style={{ fontSize: ".8rem" }}>
                {result.created ? "New record stored" : result.refreshed ? "Record refreshed" : "Existing record unchanged"}
              </strong>
              <span className="fb-fine" style={{ marginTop: 0 }}>{result.enrichment_mode ?? "enrichment pending"} · {result.authorization_mode}</span>
            </div>

            <div className="fb-detail-body" style={{ padding: 0, margin: "0 0 1rem" }}>
              {(() => {
                const diff = wordDiff(submittedText, result.content_text);
                return (
                  <>
                    <div className="fb-detail-col">
                      <h2>User submitted</h2>
                      <div className="fb-rec-evidence fb-diff-text" style={{ margin: 0 }}><DiffText tokens={diff.rawTokens} mode="removed" /></div>
                      <p className="fb-fine" style={{ margin: ".5rem 0 0" }}><mark className="fb-diff-mark is-removed">Highlighted</mark> text never reaches AI services or Supabase.</p>
                    </div>
                    <div className="fb-detail-col">
                      <h2>AI services and Supabase receive</h2>
                      <div className="fb-rec-evidence fb-diff-text" style={{ margin: 0, fontFamily: "'Courier New', monospace" }}><DiffText tokens={diff.protectedTokens} mode="added" /></div>
                      <p className="fb-fine" style={{ margin: ".5rem 0 0" }}><mark className="fb-diff-mark is-added">Highlighted</mark> text was substituted by protection.</p>
                    </div>
                  </>
                );
              })()}
            </div>

            <div className="fb-answer-card">
              <div className="fb-eyebrow" style={{ marginBottom: ".5rem" }}>Protected summary</div>
              <p className="fb-answer-text" style={{ margin: 0 }}>{result.summary ?? "Summary is pending; the protected source was retained safely."}</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
