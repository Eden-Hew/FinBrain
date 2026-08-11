import { useAppState } from "../lib/appState";
import { LogoMark } from "../components/Logo";

export default function Login() {
  const { show, goToSecurity } = useAppState();

  return (
    <div className="fb-root">
      <div className="fb-login-wrap">
        <div className="fb-login-story" style={{ background: "#1a1a1a", color: "#f4f1ea" }}>
          <button className="fb-wordmark" style={{ color: "#f4f1ea", fontSize: "1rem" }} onClick={() => show("landing")}>
            <LogoMark large />FINBRAIN OS
          </button>
          <div>
            <div className="fb-eyebrow" style={{ color: "#b3ac99" }}>Security by Construction</div>
            <h1 style={{ fontSize: "1.7rem", fontWeight: 500, lineHeight: 1.35, margin: ".7rem 0" }}>Ask your business.<br />Get answers you can prove.</h1>
            <p className="fb-sans" style={{ fontSize: ".78rem", color: "#b3ac99", maxWidth: "340px", margin: 0 }}>One permission-aware workspace for finance, compliance and operations — plus agents that do the busywork for you.</p>
          </div>
          <div className="fb-sans fb-trust-list">
            <div className="fb-trust-row">
              <svg className="fb-trust-icon" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" /></svg>
              <div><strong>Token isolation</strong><span>Sensitive values never leave the vault ungated.</span></div>
            </div>
            <div className="fb-trust-row">
              <svg className="fb-trust-icon" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z" /><path d="M9.5 12l2 2 3.5-3.5" /></svg>
              <div><strong>Source-native permissions</strong><span>Access follows each source's own department and level.</span></div>
            </div>
            <div className="fb-trust-row">
              <svg className="fb-trust-icon" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="4" y="3" width="16" height="18" rx="2" /><path d="M8 8h8M8 12h8M8 16h5" /></svg>
              <div><strong>Tamper-evident audit</strong><span>Every decision is hash-chained and append-only.</span></div>
            </div>
          </div>
          <div className="fb-sans" style={{ fontSize: ".68rem" }}>
            <span tabIndex={0} role="button" style={{ cursor: "pointer", color: "#b3ac99", textDecoration: "underline" }} onClick={() => goToSecurity("login")}>Learn more about our security &amp; compliance approach →</span>
          </div>
        </div>
        <form className="fb-login-form" onSubmit={(e) => { e.preventDefault(); show("agents"); }}>
          <div className="fb-eyebrow">Welcome Back</div>
          <h2 style={{ fontSize: "1.2rem", fontWeight: 700, margin: ".2rem 0" }}>Enter the secure workspace</h2>
          <p style={{ fontSize: ".75rem", color: "var(--ink-soft)", margin: "0 0 .4rem" }}>Use a seeded demo account or continue with the limited public role.</p>

          <label className="fb-field-label" htmlFor="fb-login-role">Demo role
            <select className="fb-field-mock" id="fb-login-role" name="role" defaultValue="Finance Director — Restricted">
              <option>Finance Director — Restricted</option>
              <option>Employee — Internal</option>
              <option>Guest — Public</option>
            </select>
          </label>
          <label className="fb-field-label" htmlFor="fb-login-username">Username
            <input className="fb-field-mock" id="fb-login-username" name="username" type="email" autoComplete="username" defaultValue="chloe@finbrain.my" required />
          </label>
          <label className="fb-field-label" htmlFor="fb-login-password">Password
            <input className="fb-field-mock" id="fb-login-password" name="password" type="password" autoComplete="current-password" defaultValue="finbrain-demo" required />
          </label>

          <button className="fb-btn fb-btn-solid" style={{ width: "100%", marginTop: ".3rem" }} type="submit">Sign in to FINBRAIN</button>
          <div className="fb-or-divider"><span>or</span></div>
          <button className="fb-btn fb-btn-outline" style={{ width: "100%" }} type="button" onClick={() => show("agents")}>Continue as Guest</button>
          <div className="fb-fine">Local demo accounts use the password <code>finbrain-demo</code>.</div>
          <div className="fb-fine">New here? <span style={{ cursor: "pointer", textDecoration: "underline", color: "var(--ink)" }} tabIndex={0} role="button" onClick={() => show("signup")}>Create an account</span></div>
        </form>
      </div>
    </div>
  );
}
