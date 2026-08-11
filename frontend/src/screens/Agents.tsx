import { useRef, useState } from "react";
import { useAppState } from "../lib/appState";
import { useI18n, FB_UI_STRINGS } from "../lib/i18n";
import { FB_UNIFIED_FALLBACK } from "../data/sampleData";
import { AppNav } from "../components/Nav";
import { resolveChatReply, type ChatReply } from "../components/embeds/ChatEmbeds";
import { askQuestion, type Role } from "../api/client";

interface Message {
  id: number;
  from: "user" | "agent";
  text: string;
  embed?: React.ReactNode;
  thinking?: boolean;
}

interface ContextChip {
  kind: "file" | "context";
  label: string;
}

const SUGGESTIONS = [
  "What e-invoices need my approval?",
  "Which accounts are overdue?",
  "Show me open process recommendations",
  "What's our cash flow looking like?",
];

const ASK_ROLE_TO_BACKEND: Record<string, Role> = {
  finance_director: "owner_director",
  employee: "general_employee",
  guest: "compliance",
};

let msgId = 1;

export default function Agents() {
  const { askRole, setAskRole, sampleBanner, dismissSampleBanner } = useAppState();
  const { lang, t } = useI18n();
  const [messages, setMessages] = useState<Message[]>([
    { id: msgId++, from: "agent", text: "Hi, I’m FINBRAIN. I can handle invoicing, spreadsheets, files, sales follow-ups, compliance checks, and more — ask me anything, or try one of the suggestions above." },
  ]);
  const [input, setInput] = useState("");
  const [chips, setChips] = useState<ContextChip[]>([]);
  const [contextMenuOpen, setContextMenuOpen] = useState(false);
  const [webSearchOn, setWebSearchOn] = useState(false);
  const [recording, setRecording] = useState(false);
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
      const reply: ChatReply = resolveChatReply(trimmed, lang, FB_UNIFIED_FALLBACK[lang]);
      let finalText = reply.text;

      if (!reply.embed && finalText === FB_UNIFIED_FALLBACK[lang]) {
        try {
          const backendRole = ASK_ROLE_TO_BACKEND[askRole] ?? "general_employee";
          const res = await askQuestion(trimmed, backendRole);
          finalText = res.answer;
        } catch {
          // backend unavailable — keep the scripted fallback
        }
      }

      const webNote = webSearchOn ? "🌐 Also checked recent web sources for this.\n\n" : "";
      setMessages((m) => m.map((msg) => (msg.id === thinkingId ? { ...msg, thinking: false, text: webNote + finalText, embed: reply.embed } : msg)));
      scrollToBottom();
    }, 650);
  };

  const handleSuggestion = (text: string) => send(text);

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setChips((c) => [...c, { kind: "file", label: file.name }]);
    e.target.value = "";
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
        <div className="fb-lang-row">
          <span className="fb-eyebrow">{t("agents.viewingAs")}</span>
          <div className="fb-role-switch" role="tablist" style={{ margin: 0 }}>
            <button className={"fb-role-btn" + (askRole === "finance_director" ? " is-current" : "")} type="button" onClick={() => setAskRole("finance_director")}>Finance Director</button>
            <button className={"fb-role-btn" + (askRole === "employee" ? " is-current" : "")} type="button" onClick={() => setAskRole("employee")}>Employee</button>
            <button className={"fb-role-btn" + (askRole === "guest" ? " is-current" : "")} type="button" onClick={() => setAskRole("guest")}>Guest</button>
          </div>
        </div>
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
                    <span style={{ whiteSpace: "pre-wrap" }}>{msg.text}</span>
                    {msg.embed && <div className="fb-chat-embed">{msg.embed}</div>}
                  </>
                )}
              </div>
            ))}
          </div>

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
              <input type="file" ref={fileInputRef} style={{ display: "none" }} onChange={handleFile} />
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
