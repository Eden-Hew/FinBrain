import { useRef, useState } from "react";
import { useAppState } from "../lib/appState";
import { useI18n, FB_UI_STRINGS } from "../lib/i18n";
import { FB_UNIFIED_FALLBACK } from "../data/sampleData";
import { AppNav } from "../components/Nav";
import { PersonaSelector } from "../components/PersonaSelector";
import { resolveChatReply, type ChatReply } from "../components/embeds/ChatEmbeds";
import {
  askQuestion,
  commitUpload,
  previewUpload,
  type QueryCitation,
  type UploadCommitResponse,
  type UploadPreviewResponse,
} from "../api/client";

interface Message {
  id: number;
  from: "user" | "agent";
  text: string;
  embed?: React.ReactNode;
  thinking?: boolean;
  protectedText?: string;
  citations?: QueryCitation[];
  showProtected?: boolean;
  mode?: string;
  rawQuestion?: string;
}

interface ContextChip {
  kind: "file" | "context";
  label: string;
}

type UploadState = "idle" | "previewing" | "protected" | "committing" | "complete" | "failed";

const SUGGESTIONS = [
  "What e-invoices need my approval?",
  "Which accounts are overdue?",
  "Show me open process recommendations",
  "What's our cash flow looking like?",
];

let msgId = 1;

export default function Agents() {
  const { askRole, sampleBanner, dismissSampleBanner } = useAppState();
  const { lang, t } = useI18n();
  const [messages, setMessages] = useState<Message[]>([
    { id: msgId++, from: "agent", text: "Hi, I’m FINBRAIN. I can handle invoicing, spreadsheets, files, sales follow-ups, compliance checks, and more — ask me anything, or try one of the suggestions above." },
  ]);
  const [input, setInput] = useState("");
  const [chips, setChips] = useState<ContextChip[]>([]);
  const [contextMenuOpen, setContextMenuOpen] = useState(false);
  const [webSearchOn, setWebSearchOn] = useState(false);
  const [recording, setRecording] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadState, setUploadState] = useState<UploadState>("idle");
  const [uploadPreview, setUploadPreview] = useState<UploadPreviewResponse | null>(null);
  const [uploadResult, setUploadResult] = useState<UploadCommitResponse | null>(null);
  const [uploadError, setUploadError] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [protectedTurnCount, setProtectedTurnCount] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const messagesRef = useRef<HTMLDivElement>(null);
  const voiceIndexRef = useRef(0);

  const scrollToBottom = () => {
    requestAnimationFrame(() => {
      if (messagesRef.current) messagesRef.current.scrollTop = messagesRef.current.scrollHeight;
    });
  };

  const send = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;

    let attachedNote = "";
    if (chips.length) {
      attachedNote = chips.map((c) => (c.kind === "file" ? "📄 " : "🔗 ") + c.label).join(" · ") + "\n";
      setChips([]);
    }

    setMessages((m) => [...m, { id: msgId++, from: "user", text: attachedNote + trimmed }]);
    setInput("");
    const thinkingId = msgId++;
    setMessages((m) => [...m, { id: thinkingId, from: "agent", text: "", thinking: true }]);
    scrollToBottom();

    setTimeout(async () => {
      const fallback: ChatReply = resolveChatReply(trimmed, lang, FB_UNIFIED_FALLBACK[lang]);
      let finalText = fallback.text;
      let protectedText: string | undefined;
      let citations: QueryCitation[] = [];
      let mode = "scripted-demo";
      let embed = fallback.embed;
      try {
        const response = await askQuestion(trimmed, askRole, conversationId);
        setConversationId(response.conversation_id);
        setProtectedTurnCount((count) => count + 1);
        finalText = response.answer;
        protectedText = response.model_answer;
        citations = response.citations;
        mode = response.mode;
        embed = undefined;
      } catch {
        // Preserve the visual demonstration when the local backend is unavailable.
      }

      const webNote = webSearchOn
        ? "Web search is not connected in this prototype. The answer below uses FinBrain records only.\n\n"
        : "";
      setMessages((messages) => messages.map((message) => (
        message.id === thinkingId
          ? {
              ...message,
              thinking: false,
              text: webNote + finalText,
              protectedText,
              citations,
              mode,
              embed,
              rawQuestion: trimmed,
            }
          : message
      )));
      scrollToBottom();
    }, 650);
  };

  const handleSuggestion = (text: string) => send(text);

  const startNewConversation = () => {
    setConversationId(null);
    setProtectedTurnCount(0);
    setChips([]);
    setMessages([
      {
        id: msgId++,
        from: "agent",
        text: "New protected conversation started. What would you like to investigate?",
      },
    ]);
  };

  const clearUpload = () => {
    setSelectedFile(null);
    setUploadPreview(null);
    setUploadResult(null);
    setUploadError("");
    setUploadState("idle");
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setSelectedFile(file);
    setUploadPreview(null);
    setUploadResult(null);
    setUploadError("");
    setUploadState("previewing");
    try {
      setUploadPreview(await previewUpload(file, askRole));
      setUploadState("protected");
    } catch (requestError) {
      setUploadError(requestError instanceof Error ? requestError.message : "Preview failed.");
      setUploadState("failed");
    }
  };

  const protectAndIngestFile = async () => {
    if (!selectedFile || !uploadPreview || uploadState === "committing") return;
    setUploadState("committing");
    setUploadError("");
    try {
      const response = await commitUpload(
        selectedFile,
        askRole,
        uploadPreview.preview_digest,
      );
      setUploadResult(response);
      setUploadState("complete");
      setChips((current) => [
        ...current.filter((chip) => chip.kind !== "file"),
        { kind: "file", label: `${response.ready_rows} protected source${response.ready_rows === 1 ? "" : "s"}` },
      ]);
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (requestError) {
      setUploadError(requestError instanceof Error ? requestError.message : "Ingestion failed.");
      setUploadState("failed");
    }
  };

  const addContext = (label: string) => {
    setChips((c) => [...c, { kind: "context", label }]);
    setContextMenuOpen(false);
  };

  const removeChip = (i: number) => setChips((c) => c.filter((_, idx) => idx !== i));

  const stopRecording = () => {
    if (!recording) return;
    setRecording(false);
    const phrase = SUGGESTIONS[voiceIndexRef.current % SUGGESTIONS.length];
    voiceIndexRef.current += 1;
    send(phrase);
  };

  return (
    <div className="fb-root">
      <AppNav current="agents" />

      {sampleBanner && (
        <div className="fb-callout fb-sample-banner">
          <span>You're exploring FINBRAIN with sample data from a demo workspace — connect your own sources anytime.</span>
          <button className="fb-icon-btn" type="button" onClick={dismissSampleBanner} aria-label="Dismiss">✕</button>
        </div>
      )}

      <header className="fb-app-header" style={{ paddingBottom: "1rem" }}>
        <h1>{t("nav.aiAgents")}</h1>
        <p>{t("agents.desc")}</p>
        <PersonaSelector compact />
      </header>

      <div className="fb-unified-wrap">
        <div className="fb-suggest-row">
          <span className="fb-eyebrow fb-suggest-label">Try asking</span>
          {SUGGESTIONS.map((s) => (
            <button key={s} className="fb-suggest-chip" type="button" onClick={() => handleSuggestion(s)}>{s}</button>
          ))}
        </div>

        <div className="fb-unified-chat-panel">
          <div className="fb-chat-messages fb-unified-messages" ref={messagesRef}>
            {messages.map((msg) => (
              <div key={msg.id} className={"fb-chat-bubble " + msg.from + (msg.embed ? " has-embed" : "")}>
                {msg.thinking ? (
                  <span className="fb-thinking"><span></span><span></span><span></span></span>
                ) : (
                  <>
                    <span style={{ whiteSpace: "pre-wrap" }}>
                      {msg.showProtected && msg.protectedText ? msg.protectedText : msg.text}
                    </span>
                    {msg.from === "agent" && msg.protectedText && (
                      <div style={{ display: "flex", gap: ".5rem", marginTop: ".7rem", flexWrap: "wrap" }}>
                        <button
                          type="button"
                          className="fb-btn fb-btn-outline"
                          onClick={() => setMessages((messages) => messages.map((message) => (
                            message.id === msg.id
                              ? { ...message, showProtected: !message.showProtected }
                              : message
                          )))}
                        >
                          {msg.showProtected ? "Show authorized answer" : "Show model view"}
                        </button>
                        <span className="fb-fine" style={{ marginTop: ".45rem" }}>
                          {msg.mode} · {msg.citations?.length ?? 0} cited sources
                        </span>
                        {msg.rawQuestion && (
                          <button
                            type="button"
                            className="fb-btn fb-btn-outline"
                            onClick={() => send(msg.rawQuestion ?? "")}
                          >
                            Re-run as selected persona
                          </button>
                        )}
                      </div>
                    )}
                    {!!msg.citations?.length && (
                      <div style={{ display: "grid", gap: ".5rem", marginTop: ".8rem" }}>
                        {msg.citations.map((citation) => (
                          <div className="fb-rec-evidence" key={citation.citation_id}>
                            <strong>{citation.citation_id}</strong> · {citation.source_system} · {citation.record_type ?? "record"}
                            {citation.occurred_at ? ` · ${new Date(citation.occurred_at).toLocaleDateString()}` : ""}
                            <div style={{ marginTop: ".35rem" }}>{citation.protected_excerpt}</div>
                          </div>
                        ))}
                      </div>
                    )}
                    {msg.embed && <div className="fb-chat-embed">{msg.embed}</div>}
                  </>
                )}
              </div>
            ))}
          </div>

          {uploadState !== "idle" && (
            <section className="fb-upload-preview" aria-live="polite">
              <div className="fb-upload-preview-head">
                <div>
                  <strong>
                    {uploadState === "previewing" ? "Protecting preview..." :
                      uploadState === "committing" ? "Protecting and ingesting..." :
                        uploadState === "complete" ? "Upload complete" :
                          uploadState === "failed" ? "Upload needs attention" :
                            "Protected preview"}
                  </strong>
                  {selectedFile && (
                    <div className="fb-fine">
                      {selectedFile.type || "Unknown type"} · {(selectedFile.size / 1024).toFixed(1)} KB
                    </div>
                  )}
                </div>
                <span className={`fb-status-pill ${uploadState === "complete" ? "is-active" : "is-review"}`}>
                  <span className="fb-status-dot"></span>{uploadState}
                </span>
              </div>

              {uploadPreview && (
                <>
                  <div className="fb-upload-stats">
                    <span>{uploadPreview.schema_name ?? uploadPreview.input_kind}</span>
                    <span>{uploadPreview.valid_rows} valid</span>
                    <span>{uploadPreview.invalid_rows} invalid</span>
                  </div>
                  <div className="fb-upload-samples">
                    {uploadPreview.protected_preview.slice(0, 3).map((item) => (
                      <div key={`${item.source_record_id}-${item.row_number ?? 0}`}>
                        {item.row_number ? `Row ${item.row_number}: ` : ""}{item.content_text}
                      </div>
                    ))}
                  </div>
                  {uploadPreview.valid_rows > Math.min(3, uploadPreview.protected_preview.length) && (
                    <div className="fb-fine">
                      Showing {Math.min(3, uploadPreview.protected_preview.length)} of {uploadPreview.valid_rows} protected rows<br />
                      + {uploadPreview.valid_rows - Math.min(3, uploadPreview.protected_preview.length)} additional row{uploadPreview.valid_rows - Math.min(3, uploadPreview.protected_preview.length) === 1 ? "" : "s"} will be ingested
                    </div>
                  )}
                  {[...uploadPreview.issues.map((issue) => issue.code), ...uploadPreview.warnings]
                    .map((notice) => <div className="fb-fine" key={notice}>{notice.replaceAll("_", " ")}</div>)}
                </>
              )}

              {uploadResult && (
                <div className="fb-upload-stats">
                  <span>{uploadResult.ready_rows} ready</span>
                  <span>{uploadResult.protected_rows} protected</span>
                  <span>{uploadResult.failed_rows} failed</span>
                </div>
              )}
              {uploadError && <div className="fb-upload-error" role="alert">{uploadError}</div>}

              <div className="fb-upload-actions">
                {uploadPreview && uploadState !== "complete" && (
                  <button
                    className="fb-btn fb-btn-solid"
                    type="button"
                    disabled={uploadState === "committing"}
                    onClick={protectAndIngestFile}
                  >
                    {uploadState === "committing" ? "Ingesting..." : "Protect and ingest"}
                  </button>
                )}
                <button className="fb-btn fb-btn-outline" type="button" onClick={clearUpload}>
                  {uploadState === "complete" ? "Close" : "Cancel"}
                </button>
              </div>
            </section>
          )}

          {chips.length > 0 && (
            <div className="fb-composer-chips">
              {chips.map((c, i) => (
                <span className="fb-composer-chip" key={i}>
                  {c.kind === "file" ? "📄" : "🔗"} {c.label}
                  <button type="button" onClick={() => removeChip(i)} aria-label={"Remove " + c.label}>✕</button>
                </span>
              ))}
            </div>
          )}

          <div className="fb-composer2">
            <div className="fb-composer2-input-row">
              <input
                className="fb-composer2-input"
                type="text"
                placeholder={FB_UI_STRINGS[lang].placeholder}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") send(input); }}
              />
              <input
                type="file"
                accept=".txt,.md,.csv,.eml,.pdf,.docx"
                ref={fileInputRef}
                style={{ display: "none" }}
                onChange={handleFile}
              />
              <button
                className={"fb-icon-btn" + (recording ? " is-recording" : "")}
                type="button"
                aria-label="Hold, or press Enter/Space, to record"
                onMouseDown={() => setRecording(true)}
                onMouseUp={stopRecording}
                onMouseLeave={() => setRecording(false)}
                onTouchStart={() => setRecording(true)}
                onTouchEnd={stopRecording}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="9" y="2" width="6" height="12" rx="3" /><path d="M5 10a7 7 0 0 0 14 0M12 19v3" /></svg>
              </button>
            </div>

            <div className="fb-composer2-toolbar-row">
              <div className="fb-composer2-tools">
                <button
                  className="fb-btn fb-btn-outline"
                  type="button"
                  onClick={startNewConversation}
                  title={conversationId ? "Clear protected conversation context" : "Start a new conversation"}
                >
                  New chat
                </button>
                <div style={{ position: "relative" }}>
                  <button className="fb-icon-btn" type="button" onClick={() => setContextMenuOpen((v) => !v)} aria-haspopup="true" aria-label="Add context">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
                  </button>
                  {contextMenuOpen && (
                    <div className="fb-context-menu" role="menu">
                      {["Q3 Financials", "SOP Library", "Recent Invoices", "Cash Flow Report"].map((label) => (
                        <div className="fb-context-menu-item" key={label} tabIndex={0} role="menuitem" onClick={() => addContext(label)}>{label}</div>
                      ))}
                    </div>
                  )}
                </div>
                <button className="fb-icon-btn" type="button" onClick={() => fileInputRef.current?.click()} aria-label="Upload from computer">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M21.44 11.05l-9.19 9.19a5 5 0 0 1-7.07-7.07l9.19-9.19a3.5 3.5 0 0 1 4.95 4.95l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" /></svg>
                </button>
                <button className={"fb-icon-btn" + (webSearchOn ? " is-active" : "")} type="button" onClick={() => setWebSearchOn((v) => !v)} aria-label="Browse the internet" aria-pressed={webSearchOn}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M3 12h18" strokeLinecap="round" /><path d="M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18" strokeLinecap="round" /></svg>
                </button>
                <span className="fb-fine">Context: {protectedTurnCount} protected turns</span>
              </div>
              <button className="fb-send-btn2" type="button" onClick={() => send(input)} aria-label={FB_UI_STRINGS[lang].send}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7" /></svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
