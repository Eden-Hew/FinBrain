import { useState } from "react";

const COOKIE_CONSENT_KEY = "fb_cookie_consent";

/** Bottom-left notice for the marketing site. Nothing here is a live tracking
 * cookie today — the only cookies this prototype sets are Supabase's own
 * session cookies — so both choices just record a preference and dismiss;
 * neither one flips a real analytics switch that doesn't exist yet. */
export function CookieConsentBanner({ onReadMore }: { onReadMore: () => void }) {
  const [choice, setChoice] = useState<string | null>(() => localStorage.getItem(COOKIE_CONSENT_KEY));

  if (choice) return null;

  const decide = (value: "accepted" | "rejected") => {
    localStorage.setItem(COOKIE_CONSENT_KEY, value);
    setChoice(value);
  };

  return (
    <div className="fb-mkt-cookie-banner" role="dialog" aria-label="Cookie notice">
      <p>
        We use essential cookies to keep you signed in. This prototype doesn't set any tracking or advertising
        cookies. <span tabIndex={0} role="button" onClick={onReadMore}>Read our privacy policy</span>.
      </p>
      <div className="fb-mkt-cookie-actions">
        <button className="fb-mkt-btn is-solid" type="button" onClick={() => decide("accepted")}>Continue</button>
        <button className="fb-mkt-btn is-outline" type="button" onClick={() => decide("rejected")}>Reject</button>
      </div>
    </div>
  );
}

interface SupportMessage {
  id: number;
  from: "agent" | "user";
  text: string;
  action?: { label: string; onClick: () => void };
}

interface SupportTopic {
  label: string;
  reply: string;
  action?: { label: string; onClick: () => void };
}

let supportMsgId = 1;

/** Bottom-right chat launcher for the marketing site. This is a scripted FAQ
 * widget, not a live agent — the site already frames itself as a prototype
 * ("not a live product"), so replies stay honest about what they are instead
 * of impersonating a real support inbox. */
export function SupportWidget({ topics, onEmail }: { topics: SupportTopic[]; onEmail: () => void }) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<SupportMessage[]>([
    { id: supportMsgId++, from: "agent", text: "Hi — I'm the FinBrain prototype assistant. Pick a topic below, or email the team directly." },
  ]);
  const [input, setInput] = useState("");

  const ask = (topic: SupportTopic) => {
    setMessages((m) => [
      ...m,
      { id: supportMsgId++, from: "user", text: topic.label },
      { id: supportMsgId++, from: "agent", text: topic.reply, action: topic.action },
    ]);
  };

  const sendFreeform = () => {
    const trimmed = input.trim();
    if (!trimmed) return;
    setMessages((m) => [
      ...m,
      { id: supportMsgId++, from: "user", text: trimmed },
      {
        id: supportMsgId++,
        from: "agent",
        text: "This prototype doesn't have a live support inbox yet — email the team and a real person will get back to you.",
        action: { label: "Email hello@finbrainos.example", onClick: onEmail },
      },
    ]);
    setInput("");
  };

  return (
    <>
      {open && (
        <aside className="fb-mkt-support-panel" role="dialog" aria-label="FinBrain support">
          <div className="fb-mkt-support-head">
            <div>
              <strong>FinBrain Support</strong>
              <span>Prototype assistant — not a live team</span>
            </div>
            <button className="fb-mkt-btn is-ghost" type="button" onClick={() => setOpen(false)} aria-label="Close">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12" /></svg>
            </button>
          </div>
          <div className="fb-mkt-support-messages">
            {messages.map((msg) => (
              <div key={msg.id} className={"fb-mkt-support-msg from-" + msg.from}>
                <span>{msg.text}</span>
                {msg.action && (
                  <button className="fb-mkt-btn is-outline" type="button" onClick={msg.action.onClick}>{msg.action.label}</button>
                )}
              </div>
            ))}
          </div>
          <div className="fb-mkt-support-chips">
            {topics.map((topic) => (
              <button key={topic.label} className="fb-mkt-try-chip" type="button" onClick={() => ask(topic)}>{topic.label}</button>
            ))}
          </div>
          <div className="fb-mkt-support-input-row">
            <input
              type="text"
              placeholder="Message…"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => { if (event.key === "Enter") sendFreeform(); }}
            />
            <button className="fb-mkt-btn is-accent" type="button" onClick={sendFreeform} aria-label="Send">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7" /></svg>
            </button>
          </div>
        </aside>
      )}
      <button
        className="fb-mkt-support-launcher"
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={open ? "Close support chat" : "Open support chat"}
      >
        {open ? (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
        ) : (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>
        )}
      </button>
    </>
  );
}
