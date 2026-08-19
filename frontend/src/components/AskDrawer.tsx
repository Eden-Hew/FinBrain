import { useRef, useState } from "react";
import { useAppState } from "../lib/appState";
import { useI18n } from "../lib/i18n";
import { useUiChrome } from "../lib/uiChrome";
import { FB_UNIFIED_FALLBACK } from "../data/sampleData";
import { resolveChatReply } from "./embeds/ChatEmbeds";
import { askQuestion, type QueryCitation } from "../api/client";

interface DrawerMessage {
  id: number;
  from: "user" | "agent";
  text: string;
  citations?: QueryCitation[];
  thinking?: boolean;
  isFallback?: boolean;
}

let drawerMsgId = 1;

export function AskDrawer() {
  const { askOpen, closeAsk } = useUiChrome();
  const { show } = useAppState();
  const { lang } = useI18n();
  const [messages, setMessages] = useState<DrawerMessage[]>([
    { id: drawerMsgId++, from: "agent", text: "Ask a quick question about your finance data — I'll pull cited answers from your protected records." },
  ]);
  const [input, setInput] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    requestAnimationFrame(() => {
      if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
    });
  };

  const send = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    setMessages((m) => [...m, { id: drawerMsgId++, from: "user", text: trimmed }]);
    setInput("");
    const thinkingId = drawerMsgId++;
    setMessages((m) => [...m, { id: thinkingId, from: "agent", text: "", thinking: true }]);
    scrollToBottom();

    let finalText: string;
    let citations: QueryCitation[] = [];
    let isFallback = false;
    try {
      const response = await askQuestion(trimmed, conversationId);
      setConversationId(response.conversation_id);
      finalText = response.answer;
      citations = response.citations;
    } catch {
      const fallback = resolveChatReply(trimmed, lang, FB_UNIFIED_FALLBACK[lang]);
      finalText = fallback.text;
      isFallback = true;
    }

    setMessages((m) => m.map((msg) => (msg.id === thinkingId ? { ...msg, thinking: false, text: finalText, citations, isFallback } : msg)));
    scrollToBottom();
  };

  if (!askOpen) return null;

  return (
    <div className="fb-drawer-backdrop" onClick={closeAsk}>
      <aside className="fb-drawer" role="dialog" aria-modal="true" aria-label="Ask FinBrain" onClick={(event) => event.stopPropagation()}>
        <div className="fb-drawer-head">
          <span className="fb-drawer-title">Ask FinBrain</span>
          <button className="fb-icon-btn" type="button" onClick={closeAsk} aria-label="Close">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12" /></svg>
          </button>
        </div>
        <div className="fb-drawer-messages" ref={listRef}>
          {messages.map((msg) => (
            <div key={msg.id} className={"fb-chat-bubble " + msg.from}>
              {msg.thinking ? (
                <div className="fb-thinking" role="status"><span></span><span></span><span></span></div>
              ) : (
                <>
                  {msg.isFallback && <div className="fb-intel-fallback" role="status">Sample response — the live backend is unavailable.</div>}
                  <span style={{ whiteSpace: "pre-wrap" }}>{msg.text}</span>
                  {!!msg.citations?.length && (
                    <div className="fb-fine" style={{ marginTop: ".5rem" }}>{msg.citations.length} cited source{msg.citations.length === 1 ? "" : "s"}</div>
                  )}
                </>
              )}
            </div>
          ))}
        </div>
        <div className="fb-drawer-footer">
          <button className="fb-btn fb-btn-outline" style={{ width: "100%", marginBottom: ".6rem" }} type="button" onClick={() => { closeAsk(); show("agents"); }}>
            Open full Customer Intelligence
          </button>
          <div className="fb-drawer-input-row">
            <input
              className="fb-composer2-input"
              type="text"
              placeholder="Ask anything…"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => { if (event.key === "Enter") send(input); }}
            />
            <button className="fb-send-btn2" type="button" onClick={() => send(input)} aria-label="Send">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7" /></svg>
            </button>
          </div>
        </div>
      </aside>
    </div>
  );
}
