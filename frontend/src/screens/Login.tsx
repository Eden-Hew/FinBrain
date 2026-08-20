import { useState } from "react";
import { useAuth } from "../auth/AuthProvider";
import { LogoMark } from "../components/Logo";
import { useAppState } from "../lib/appState";

export default function Login() {
  const { show, goToSecurity } = useAppState();
  const { authError, signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await signIn(email.trim(), password);
      show("home");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Sign in failed.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fb-root fb-mkt">
      <div className="fb-mkt-auth-wrap">
        <div className="fb-mkt-auth-story">
          <div className="fb-mkt-blob" style={{ width: 340, height: 340, top: -120, left: -100, background: "var(--a-accent)" }} aria-hidden="true" />
          <div className="fb-mkt-blob" style={{ width: 260, height: 260, bottom: -100, right: -80, background: "var(--a-purple)" }} aria-hidden="true" />
          <button className="fb-mkt-wordmark" style={{ position: "relative", zIndex: 1 }} onClick={() => show("landing")}>
            <LogoMark large />FINBRAIN OS
          </button>
          <div className="fb-mkt-auth-copy">
            <div className="fb-mkt-eyebrow" style={{ position: "relative", zIndex: 1 }}>Verified access</div>
            <h1>Ask your business.<br />Get answers you can prove.</h1>
            <p>Supabase verifies your identity. FinBrain applies your assigned role to every protected API call.</p>
          </div>
          <div className="fb-mkt-trust-list">
            <div className="fb-mkt-trust-row">
              <div className="fb-mkt-trust-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="4" y="10" width="16" height="10" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></svg></div>
              <div><strong>Signed requests</strong><span>Every protected API call carries a short-lived access token.</span></div>
            </div>
            <div className="fb-mkt-trust-row">
              <div className="fb-mkt-trust-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3 20 6.5v5.3c0 4.7-3.2 8.9-8 10.2-4.8-1.3-8-5.5-8-10.2V6.5z" /></svg></div>
              <div><strong>Server-owned roles</strong><span>The browser cannot select or elevate its own permissions.</span></div>
            </div>
            <div className="fb-mkt-trust-row">
              <div className="fb-mkt-trust-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M4 6h16M4 12h16M4 18h10" /></svg></div>
              <div><strong>Tamper-evident audit</strong><span>Disclosures and workflow decisions retain a privacy-safe actor reference.</span></div>
            </div>
          </div>
          <span className="fb-mkt-auth-link" tabIndex={0} role="button" onClick={() => goToSecurity("login")}>Learn more about our security and compliance approach →</span>
        </div>
        <div className="fb-mkt-auth-form-wrap">
          <form className="fb-mkt-auth-form" onSubmit={submit}>
            <div className="fb-mkt-eyebrow is-plain">Welcome back</div>
            <h2>Enter the secure workspace</h2>
            <p>Use a provisioned Supabase account. Your FinBrain role is assigned by an administrator.</p>
            <label className="fb-mkt-field" htmlFor="fb-login-username">Email
              <input className="fb-mkt-input" id="fb-login-username" name="username" type="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} required />
            </label>
            <label className="fb-mkt-field" htmlFor="fb-login-password">Password
              <input className="fb-mkt-input" id="fb-login-password" name="password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required />
            </label>
            {(error || authError) && (
              <div className="fb-mkt-callout" role="alert">{error || authError}</div>
            )}
            <button className="fb-mkt-btn is-accent is-lg" style={{ width: "100%", justifyContent: "center", marginTop: ".2rem" }} type="submit" disabled={submitting}>
              {submitting ? "Authenticating…" : "Sign in to FINBRAIN"}
            </button>
            <div className="fb-mkt-fine">Accounts and roles are provisioned by the FinBrain administrator.</div>
          </form>
        </div>
      </div>
    </div>
  );
}
