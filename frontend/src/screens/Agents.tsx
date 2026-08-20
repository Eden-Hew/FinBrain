import { useRef, useState } from "react";
import { useAppState } from "../lib/appState";
import { useI18n, FB_UI_STRINGS } from "../lib/i18n";
import { FB_UNIFIED_FALLBACK } from "../data/sampleData";
import { Sidebar, AppTopBar } from "../components/Nav";
import {
  IntelligenceExperience,
  StandaloneExposureReceipt,
  StructuredCitationResults,
} from "../components/intelligence/IntelligenceExperience";
import { matchEinvoiceReadinessEmbed, resolveChatReply, type ChatReply } from "../components/embeds/ChatEmbeds";
import {
  askQuestion,
  commitUpload,
  previewUpload,
  type QueryCitation,
  type CustomerIntelligenceBrief,
  type ExposureReceipt,
  type QueryIntent,
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
  queryIntent?: QueryIntent;
  rawQuestion?: string;
  modelQuestion?: string;
  turnId?: number;
  brief?: CustomerIntelligenceBrief;
  exposure?: ExposureReceipt;
  isFallback?: boolean;
}

interface ContextChip {
  label: string;
}

interface SpeechRecognitionResultLike {
  0: { transcript: string };
}
interface SpeechRecognitionEventLike {
  results: ArrayLike<SpeechRecognitionResultLike>;
}
interface SpeechRecognitionErrorEventLike {
  error: string;
}
interface SpeechRecognitionLike {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start: () => void;
  stop: () => void;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null;
  onend: (() => void) | null;
}

const VOICE_LANG: Record<string, string> = { en: "en-US", ms: "ms-MY", zh: "zh-CN" };

type UploadState = "idle" | "previewing" | "protected" | "committing" | "complete" | "failed";

const SUGGESTIONS = [
  { text: "Why are payment approvals being delayed, and what should we do next?", icon: "📋" },
  { text: "Summarize all approval-delay records and cite every source.", icon: "📋" },
  { text: "Which records have no assigned owner?", icon: "🔍" },
  { text: "How many high-priority approval delays came from email this week?", icon: "📋" },
  { text: "Which invoices need fixes before MyInvois submission?", icon: "🧾" },
];

let msgId = 1;

export default function Agents() {
  const {
    askRole,
    sampleBanner,
    dismissSampleBanner,
    openApprovalRecommendation,
    show,
    approvalsCount,
    einvoices,
  } = useAppState();
  const { lang, t } = useI18n();
  const [messages, setMessages] = useState<Message[]>([
    { id: msgId++, from: "agent", text: "Hi, I’m FinBrain. I can handle invoicing, spreadsheets, files, sales follow-ups, compliance checks, and more — ask me anything, or try one of the suggestions above." },
  ]);
  const [input, setInput] = useState("");
  const [chips, setChips] = useState<ContextChip[]>([]);
  const [recording, setRecording] = useState(false);
  const [voiceError, setVoiceError] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadState, setUploadState] = useState<UploadState>("idle");
  const [uploadPreview, setUploadPreview] = useState<UploadPreviewResponse | null>(null);
  const [uploadResult, setUploadResult] = useState<UploadCommitResponse | null>(null);
  const [uploadError, setUploadError] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [protectedTurnCount, setProtectedTurnCount] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const messagesRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const voiceTranscriptRef = useRef("");
  const voiceSupported = typeof window !== "undefined"
    && Boolean((window as unknown as { SpeechRecognition?: unknown; webkitSpeechRecognition?: unknown }).SpeechRecognition
      || (window as unknown as { webkitSpeechRecognition?: unknown }).webkitSpeechRecognition);

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
      attachedNote = chips.map((c) => "📄 " + c.label).join(" · ") + "\n";
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
      let queryIntent: QueryIntent | undefined;
      let embed = fallback.embed;
      let brief: CustomerIntelligenceBrief | undefined;
      let exposure: ExposureReceipt | undefined;
      let modelQuestion: string | undefined;
      let turnId: number | undefined;
      let isFallback = false;
      try {
        const response = await askQuestion(trimmed, conversationId);
        setConversationId(response.conversation_id);
        setProtectedTurnCount((count) => count + 1);
        finalText = response.answer;
        protectedText = response.model_answer;
        citations = response.citations;
        mode = response.mode;
        queryIntent = response.query_intent;
        brief = response.intelligence_brief ?? undefined;
        exposure = response.exposure_receipt ?? undefined;
        modelQuestion = response.model_question;
        turnId = response.turn_id ?? undefined;
        embed = matchEinvoiceReadinessEmbed(trimmed) ?? undefined;
      } catch {
        // Preserve the visual demonstration when the local backend is unavailable.
        isFallback = true;
      }

      setMessages((messages) => messages.map((message) => (
        message.id === thinkingId
          ? {
              ...message,
              thinking: false,
              text: finalText,
              protectedText,
              citations,
              mode,
              queryIntent,
              embed,
              rawQuestion: trimmed,
              modelQuestion,
              turnId,
              brief,
              exposure,
              isFallback,
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
      setUploadPreview(await previewUpload(file));
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
        uploadPreview.preview_digest,
      );
      setUploadResult(response);
      setUploadState("complete");
      setChips([{ label: `${response.ready_rows} protected source${response.ready_rows === 1 ? "" : "s"}` }]);
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (requestError) {
      setUploadError(requestError instanceof Error ? requestError.message : "Ingestion failed.");
      setUploadState("failed");
    }
  };

  const removeChip = (i: number) => setChips((c) => c.filter((_, idx) => idx !== i));

  const startRecording = () => {
    if (!voiceSupported || recording) return;
    const Ctor = ((window as unknown as { SpeechRecognition?: new () => SpeechRecognitionLike }).SpeechRecognition
      ?? (window as unknown as { webkitSpeechRecognition?: new () => SpeechRecognitionLike }).webkitSpeechRecognition)!;
    const recognition = new Ctor();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = VOICE_LANG[lang] ?? "en-US";
    voiceTranscriptRef.current = "";
    setVoiceError("");
    recognition.onresult = (event) => {
      let transcript = "";
      for (let i = 0; i < event.results.length; i++) transcript += event.results[i][0].transcript;
      voiceTranscriptRef.current = transcript;
      setInput(transcript);
    };
    recognition.onerror = (event) => {
      setVoiceError(event.error === "not-allowed" ? "Microphone access was blocked." : "Voice input failed — try again.");
      setRecording(false);
    };
    recognition.onend = () => {
      setRecording(false);
      const transcript = voiceTranscriptRef.current.trim();
      if (transcript) send(transcript);
    };
    recognitionRef.current = recognition;
    recognition.start();
    setRecording(true);
  };

  const stopRecording = () => {
    if (!recording) return;
    recognitionRef.current?.stop();
  };

  const einvoicesPending = Object.values(einvoices).filter((inv) => inv.status === "pending").length;
  const hasConversation = messages.length > 1;

  return (
    <div className="fb-root fb-shell fb-chat-shell">
      <Sidebar current="agents" />
      <AppTopBar current="agents" />

      <div className="fb-chat-page">
        {sampleBanner && (
          <div className="fb-callout fb-sample-banner">
            <span>You're exploring FinBrain with sample data from a demo workspace — connect your own sources anytime.</span>
            <button className="fb-icon-btn" type="button" onClick={dismissSampleBanner} aria-label="Dismiss">✕</button>
          </div>
        )}

        {!hasConversation && (
          <div className="fb-chat-welcome">
            <header className="fb-app-header" style={{ paddingBottom: "1rem" }}>
              <h1>{t("nav.aiAgents")}</h1>
              <p>{t("agents.desc")}</p>
            </header>

            <div className="fb-agents-overview">
              <button className="fb-overview-stat" type="button" onClick={() => show("approvals")}>
                <span className="fb-overview-value">{approvalsCount}</span>
                <span className="fb-overview-label">Pending approvals</span>
                <span className="fb-overview-arrow" aria-hidden="true">→</span>
              </button>
              <button className="fb-overview-stat" type="button" onClick={() => show("einvoice")}>
                <span className="fb-overview-value">{einvoicesPending}</span>
                <span className="fb-overview-label">e-Invoices to review</span>
                <span className="fb-overview-arrow" aria-hidden="true">→</span>
              </button>
              <button className="fb-overview-stat" type="button" onClick={() => show("finance")}>
                <span className="fb-overview-value">RM 94K</span>
                <span className="fb-overview-label">Outstanding AR</span>
                <span className="fb-overview-arrow" aria-hidden="true">→</span>
              </button>
            </div>
          </div>
        )}

        <div className={"fb-chat-transcript-wrap" + (hasConversation ? " is-active" : "")}>
          {!hasConversation && (
            <div className="fb-suggest-row">
              <span className="fb-eyebrow fb-suggest-label">Try asking</span>
              {SUGGESTIONS.map((s) => (
                <button key={s.text} className="fb-suggest-chip" type="button" onClick={() => handleSuggestion(s.text)}>
                  <span className="fb-suggest-chip-icon" aria-hidden="true">{s.icon}</span>{s.text}
                </button>
              ))}
            </div>
          )}

          <div className="fb-unified-chat-panel">
          <div className="fb-chat-messages fb-unified-messages" ref={messagesRef}>
            {messages.map((msg) => (
              <div key={msg.id} className={"fb-chat-bubble " + msg.from + (msg.embed ? " has-embed" : "") + (msg.brief ? " has-intelligence" : "") + (msg.queryIntent === "list_records" ? " has-structured-records" : "")}>
                {msg.thinking ? (
                  <div className="fb-intel-building" role="status">
                    <span className="fb-thinking"><span></span><span></span><span></span></span>
                    <span>Building protected brief…</span>
                  </div>
                ) : (
                  <>
                    {msg.isFallback && (
                      <div className="fb-intel-fallback" role="status">Sample response — the live backend is unavailable.</div>
                    )}
                    {!msg.brief && msg.queryIntent !== "list_records" && (
                      <span style={{ whiteSpace: "pre-wrap" }}>
                        {msg.showProtected && msg.protectedText ? msg.protectedText : msg.text}
                      </span>
                    )}
                    {msg.brief && msg.turnId && msg.rawQuestion && msg.modelQuestion && msg.protectedText && (
                      <IntelligenceExperience
                        brief={msg.brief}
                        citations={msg.citations ?? []}
                        exposure={msg.exposure ?? null}
                        turnId={msg.turnId}
                        rawQuestion={msg.rawQuestion}
                        modelQuestion={msg.modelQuestion}
                        protectedAnswer={msg.protectedText}
                        authorizedAnswer={msg.text}
                        role={askRole}
                        onOpenApprovals={openApprovalRecommendation}
                      />
                    )}
                    {msg.queryIntent === "list_records" && msg.turnId && msg.rawQuestion && msg.modelQuestion && msg.protectedText && (
                      <StructuredCitationResults
                        answer={msg.text}
                        citations={msg.citations ?? []}
                        exposure={msg.exposure ?? null}
                        turnId={msg.turnId}
                        rawQuestion={msg.rawQuestion}
                        modelQuestion={msg.modelQuestion}
                        protectedAnswer={msg.protectedText}
                      />
                    )}
                    {msg.from === "agent" && msg.protectedText && !msg.brief && msg.queryIntent !== "list_records" && (
                      <div style={{ display: "flex", gap: ".5rem", marginTop: ".7rem", flexWrap: "wrap" }}>
                        {msg.exposure && msg.rawQuestion && msg.modelQuestion && (
                          <StandaloneExposureReceipt exposure={msg.exposure} rawQuestion={msg.rawQuestion} modelQuestion={msg.modelQuestion} protectedAnswer={msg.protectedText} authorizedAnswer={msg.text} />
                        )}
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
                    {!!msg.citations?.length && !msg.brief && msg.queryIntent !== "list_records" && (
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
                  📄 {c.label}
                  <button type="button" onClick={() => removeChip(i)} aria-label={"Remove " + c.label}>✕</button>
                </span>
              ))}
            </div>
          )}
          {voiceError && <div className="fb-fine" role="alert" style={{ padding: "0 1.1rem", color: "var(--chart-attn)" }}>{voiceError}</div>}

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
                accept=".txt,.md,.csv,.eml,.pdf,.docx,.png,.jpg,.jpeg,.webp,.bmp,.tiff"
                ref={fileInputRef}
                style={{ display: "none" }}
                onChange={handleFile}
              />
              <button
                className={"fb-icon-btn" + (recording ? " is-recording" : "")}
                type="button"
                disabled={!voiceSupported}
                title={voiceSupported ? "Hold to speak — release to send" : "Voice input isn't supported in this browser"}
                aria-label={voiceSupported ? "Hold, or press Enter/Space, to speak your question" : "Voice input isn't supported in this browser"}
                onMouseDown={startRecording}
                onMouseUp={stopRecording}
                onMouseLeave={stopRecording}
                onTouchStart={startRecording}
                onTouchEnd={stopRecording}
                onKeyDown={(e) => { if ((e.key === "Enter" || e.key === " ") && !recording) { e.preventDefault(); startRecording(); } }}
                onKeyUp={(e) => { if (e.key === "Enter" || e.key === " ") stopRecording(); }}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="9" y="2" width="6" height="12" rx="3" /><path d="M5 10a7 7 0 0 0 14 0M12 19v3" /></svg>
              </button>
            </div>

            <div className="fb-composer2-toolbar-row">
              <div className="fb-composer2-tools">
                {hasConversation && (
                  <button
                    className="fb-btn fb-btn-outline"
                    type="button"
                    onClick={startNewConversation}
                    title="Clear this conversation and start a new one"
                  >
                    New chat
                  </button>
                )}
                <button className="fb-icon-btn" type="button" title="Upload a file" onClick={() => fileInputRef.current?.click()} aria-label="Upload from computer">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M21.44 11.05l-9.19 9.19a5 5 0 0 1-7.07-7.07l9.19-9.19a3.5 3.5 0 0 1 4.95 4.95l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" /></svg>
                </button>
                <button className="fb-icon-btn" type="button" disabled title="Web search isn't connected in this prototype" aria-label="Web search isn't connected in this prototype" aria-disabled="true">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M3 12h18" strokeLinecap="round" /><path d="M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18" strokeLinecap="round" /></svg>
                </button>
                <span className="fb-fine" title="FinBrain masks personal details before any question reaches the AI model.">
                  🔒 Privacy protected{protectedTurnCount > 0 ? ` · ${protectedTurnCount} ${protectedTurnCount === 1 ? "reply" : "replies"}` : ""}
                </span>
              </div>
              <button className="fb-send-btn2" type="button" onClick={() => send(input)} aria-label={FB_UI_STRINGS[lang].send}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7" /></svg>
              </button>
            </div>
          </div>
        </div>
      </div>
      </div>
    </div>
  );
}
