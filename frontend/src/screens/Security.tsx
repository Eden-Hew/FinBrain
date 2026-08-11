import { useAppState } from "../lib/appState";
import { ContextNav } from "../components/Nav";
import { Wordmark } from "../components/Logo";

const ITEMS = [
  {
    title: "Tokenized secrets vault",
    desc: "Sensitive values — approval thresholds, account details — are stored as AES-GCM encrypted tokens and only resolved after a permission check, never sent to the AI model in the clear.",
    path: <><rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" /></>,
  },
  {
    title: "Source-native permissions",
    desc: "Every record inherits the department and access level of where it came from. A role can only retrieve what it was already allowed to see — enforced on every query, not just at login.",
    path: <><path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z" /><path d="M9.5 12l2 2 3.5-3.5" /></>,
  },
  {
    title: "Tamper-evident audit trail",
    desc: "Every access and agent action is hash-chained and append-only — edits and deletions are rejected at the database level, not just hidden by the interface.",
    path: <><rect x="4" y="3" width="16" height="18" rx="2" /><path d="M8 8h8M8 12h8M8 16h5" /></>,
  },
  {
    title: "Human sign-off on agent actions",
    desc: "Anything an agent drafts that touches money or a customer — an invoice, a collections email — waits in your Approvals queue until you say yes.",
    path: <><circle cx="12" cy="8" r="4" /><path d="M4 21c0-4 4-6 8-6s8 2 8 6" /><path d="M15 14.5l2 2 3.5-3.5" /></>,
  },
];

export default function Security() {
  const { goToSecurity, goToLegal } = useAppState();

  return (
    <div className="fb-root">
      <ContextNav />

      <div className="fb-page-body" style={{ maxWidth: "760px", paddingTop: "2.8rem" }}>
        <div className="fb-eyebrow">Security &amp; Compliance</div>
        <h1 style={{ fontFamily: "Georgia,'Times New Roman',serif", fontSize: "1.7rem", fontWeight: 500, margin: ".6rem 0 1rem", textWrap: "balance" }}>How we protect your financial data</h1>
        <p style={{ color: "var(--ink-soft)", fontSize: ".85rem", margin: "0 0 2rem", fontFamily: "Arial,Helvetica,sans-serif" }}>FINBRAIN OS is under active development. This page describes our current security architecture and our compliance roadmap as it actually stands — we'd rather be precise about where we are than overclaim.</p>

        <div className="fb-security-grid">
          {ITEMS.map((item) => (
            <div className="fb-security-item" key={item.title}>
              <svg className="fb-security-icon" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{item.path}</svg>
              <h3>{item.title}</h3>
              <p>{item.desc}</p>
            </div>
          ))}
        </div>

        <h2 style={{ fontFamily: "Georgia,'Times New Roman',serif", fontSize: "1.1rem", fontWeight: 500, margin: "2rem 0 1rem" }}>Compliance roadmap</h2>
        <div className="fb-settings-list">
          <div className="fb-settings-row"><span>PDPA-aligned data handling</span><span>Implemented</span></div>
          <div className="fb-settings-row"><span>SOC 2 Type II</span><span>In progress</span></div>
          <div className="fb-settings-row"><span>ISO/IEC 27001</span><span>Planned</span></div>
        </div>

        <p style={{ fontSize: ".72rem", color: "var(--ink-soft)", marginTop: "2rem", fontFamily: "Arial,Helvetica,sans-serif" }}>Questions about our security posture? <a href="mailto:security@finbrainos.example" style={{ color: "var(--ink)" }}>security@finbrainos.example</a></p>
      </div>

      <footer className="fb-footer">
        <div className="fb-footer-top">
          <div>
            <Wordmark />
            <p>Permission-aware AI for finance teams. This site is a prototype.</p>
          </div>
          <div className="fb-footer-links">
            <span tabIndex={0} role="button" onClick={() => goToSecurity()}>Security</span>
            <span tabIndex={0} role="button" onClick={() => goToLegal("privacy")}>Privacy Policy</span>
            <span tabIndex={0} role="button" onClick={() => goToLegal("terms")}>Terms of Service</span>
            <a href="mailto:hello@finbrainos.example">Contact us</a>
          </div>
        </div>
        <div className="fb-footer-bottom">© 2026 FINBRAIN OS. Prototype for demonstration purposes — not a live product.</div>
      </footer>
    </div>
  );
}
