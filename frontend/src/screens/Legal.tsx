import { useAppState } from "../lib/appState";
import { ContextNav } from "../components/Nav";
import { Wordmark } from "../components/Logo";

const pStyle: React.CSSProperties = { fontSize: ".82rem", lineHeight: 1.7, color: "var(--ink-soft)", fontFamily: "Arial,Helvetica,sans-serif", margin: "0 0 1rem" };
const h1Style: React.CSSProperties = { fontFamily: "Georgia,'Times New Roman',serif", fontSize: "1.5rem", fontWeight: 500, margin: "0 0 .4rem" };

export default function Legal() {
  const { goToSecurity, goToLegal } = useAppState();
  const scrollTo = (id: string) => document.getElementById(id)?.scrollIntoView();

  return (
    <div className="fb-root">
      <ContextNav />

      <div className="fb-page-body" style={{ maxWidth: "720px", paddingTop: "2.8rem" }}>
        <div className="fb-legal-nav">
          <span tabIndex={0} role="button" onClick={() => scrollTo("legal-privacy")}>Privacy Policy</span>
          <span tabIndex={0} role="button" onClick={() => scrollTo("legal-terms")}>Terms of Service</span>
        </div>

        <section id="legal-privacy">
          <h1 style={h1Style}>Privacy Policy</h1>
          <p className="fb-fine" style={{ marginBottom: "1.2rem" }}>Last updated 10 August 2026 · Placeholder content for this prototype — not a binding legal document.</p>
          <p style={pStyle}>We collect the account information you give us (name, work email, company) and the data you connect (email, documents, spreadsheets) solely to operate your workspace — retrieve answers, run agents, and maintain the audit trail described on our Security page.</p>
          <p style={pStyle}>We don't sell your data, and we don't use your connected content to train models shared with other customers. Access within your workspace follows the permission model described on the Security page — your role determines what you can retrieve, not what plan you're on.</p>
          <p style={{ ...pStyle, margin: 0 }}>You can request an export or deletion of your account data at any time by contacting <a href="mailto:hello@finbrainos.example" style={{ color: "var(--ink)" }}>hello@finbrainos.example</a>.</p>
        </section>

        <section id="legal-terms" style={{ marginTop: "3rem" }}>
          <h1 style={h1Style}>Terms of Service</h1>
          <p className="fb-fine" style={{ marginBottom: "1.2rem" }}>Last updated 10 August 2026 · Placeholder content for this prototype — not a binding legal document.</p>
          <p style={pStyle}>By creating a workspace, you agree to use FINBRAIN OS for legitimate business purposes and to keep your login credentials confidential. You're responsible for reviewing and approving any action an AI agent prepares before it's submitted or sent — that sign-off step exists precisely so responsibility stays with your team.</p>
          <p style={pStyle}>Subscriptions renew monthly unless cancelled before the next billing date. You can cancel at any time from your account settings; access continues until the end of the current billing period.</p>
          <p style={{ ...pStyle, margin: 0 }}>FINBRAIN OS is provided "as is" during this trial/prototype phase without uptime guarantees. See our Security page for how we handle your data in the meantime.</p>
        </section>
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
