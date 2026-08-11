import { useState, type FormEvent } from "react";
import { askQuestion, type Role } from "../api/client";

interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
  modelText?: string;
  meta?: string;
  error?: boolean;
}

type ConversationView = "user" | "model";

const SUGGESTIONS = [
  "Which customer payments need attention?",
  "Summarize overdue balances and their contacts.",
  "Show the account involved in the bounced payment.",
];

export function ChatWindow({ role, onAuditChange }: { role: Role; onAuditChange: () => void }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [conversationView, setConversationView] = useState<ConversationView>("user");

  async function send(event?: FormEvent, preset?: string) {
    event?.preventDefault();
    const question = (preset ?? input).trim();
    if (!question || loading) return;
    const questionId = crypto.randomUUID();
    setMessages((current) => [...current, { id: questionId, role: "user", text: question }]);
    setInput("");
    setLoading(true);
    try {
      const response = await askQuestion(question, role);
      setMessages((current) => [
        ...current.map((message) =>
          message.id === questionId
            ? { ...message, modelText: response.model_question }
            : message,
        ),
        {
          id: crypto.randomUUID(),
          role: "assistant",
          text: response.answer,
          modelText: response.model_answer,
          meta: `${response.sources_used} sources · ${response.mode}`,
        },
      ]);
      onAuditChange();
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          text: error instanceof Error ? error.message : "The request failed.",
          error: true,
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="card chat-card" aria-label="FinBrain assistant">
      <div className="card-heading">
        <div><span className="eyebrow">Protected workspace</span><h2>Ask FinBrain</h2></div>
        <div className="view-switcher" role="group" aria-label="Conversation data view">
          <button
            type="button"
            className={conversationView === "user" ? "active" : ""}
            aria-pressed={conversationView === "user"}
            onClick={() => setConversationView("user")}
          >
            User view
          </button>
          <button
            type="button"
            className={conversationView === "model" ? "active" : ""}
            aria-pressed={conversationView === "model"}
            onClick={() => setConversationView("model")}
          >
            Gemini view
          </button>
        </div>
      </div>

      <div className={`view-explainer ${conversationView}`}>
        <i />
        {conversationView === "user"
          ? "Role-authorized values shown to the user"
          : "Tokenized values exactly as Gemini sees them"}
      </div>

      <div className="messages" aria-live="polite">
        {messages.length === 0 && (
          <div className="empty-state">
            <div className="brain-mark">F</div>
            <h3>What needs your attention today?</h3>
            <p>Ask across customer conversations and financial records. Answers respect the selected role.</p>
            <div className="suggestions">
              {SUGGESTIONS.map((suggestion) => (
                <button key={suggestion} type="button" onClick={() => send(undefined, suggestion)}>{suggestion}</button>
              ))}
            </div>
          </div>
        )}
        {messages.map((message) => (
          <article key={message.id} className={`message ${message.role} ${message.error ? "error" : ""}`}>
            <div>
              {conversationView === "model" && message.modelText
                ? message.modelText
                : message.text}
            </div>
            {message.meta && (
              <small>
                {message.meta} · {conversationView === "model" ? "tokenized" : "authorized"}
              </small>
            )}
          </article>
        ))}
        {loading && <div className="thinking"><span /><span /><span /> Reasoning over protected records</div>}
      </div>

      <form className="composer" onSubmit={(event) => send(event)}>
        <textarea
          rows={2}
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void send();
            }
          }}
          placeholder="Ask about a customer, invoice, or account…"
          aria-label="Question"
        />
        <button type="submit" disabled={loading || !input.trim()} aria-label="Send question">↑</button>
      </form>
    </section>
  );
}
