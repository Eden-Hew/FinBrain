import { useState } from "react";
import { useAuth } from "../auth/AuthProvider";
import { LogoMark } from "../components/Logo";
import { useAppState } from "../lib/appState";

export default function Login() {
  const { show, goToSecurity } = useAppState();
  const { signIn } = useAuth();
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
      show("agents");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Sign in failed.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fb-root">
      <div className="fb-login-wrap">
        <div className="fb-login-story" style={{ background: "#1a1a1a", color: "#f4f1ea" }}>
          <button className="fb-wordmark" style={{ color: "#f4f1ea", fontSize: "1rem" }} onClick={() => show("landing")}>
            <LogoMark large />FINBRAIN OS
          </button>
          <div>
            <div className="fb-eyebrow" style={{ color: "#b3ac99" }}>Verified access</div>
            <h1 style={{ fontSize: "1.7rem", fontWeight: 500, lineHeight: 1.35, margin: ".7rem 0" }}>Ask your business.<br />Get answers you can prove.</h1>
            <p className="fb-sans" style={{ fontSize: ".78rem", color: "#b3ac99", maxWidth: "340px", margin: 0 }}>Supabase verifies your identity. FinBrain applies your assigned role to every protected API call.</p>
          </div>
          <div className="fb-sans fb-trust-list">
            <div className="fb-trust-row"><div><strong>Signed requests</strong><span>Every protected API call carries a short-lived access token.</span></div></div>
            <div className="fb-trust-row"><div><strong>Server-owned roles</strong><span>The browser cannot select or elevate its own permissions.</span></div></div>
            <div className="fb-trust-row"><div><strong>Tamper-evident audit</strong><span>Disclosures and workflow decisions retain a privacy-safe actor reference.</span></div></div>
          </div>
          <div className="fb-sans" style={{ fontSize: ".68rem" }}>
            <span tabIndex={0} role="button" style={{ cursor: "pointer", color: "#b3ac99", textDecoration: "underline" }} onClick={() => goToSecurity("login")}>Learn more about our security and compliance approach →</span>
          </div>
        </div>
        <form className="fb-login-form" onSubmit={submit}>
          <div className="fb-eyebrow">Welcome back</div>
          <h2 style={{ fontSize: "1.2rem", fontWeight: 700, margin: ".2rem 0" }}>Enter the secure workspace</h2>
          <p style={{ fontSize: ".75rem", color: "var(--ink-soft)", margin: "0 0 .4rem" }}>Use a provisioned Supabase account. Your FinBrain role is assigned by an administrator.</p>
          <label className="fb-field-label" htmlFor="fb-login-username">Email
            <input className="fb-field-mock" id="fb-login-username" name="username" type="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} required />
          </label>
          <label className="fb-field-label" htmlFor="fb-login-password">Password
            <input className="fb-field-mock" id="fb-login-password" name="password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required />
          </label>
          {error && <div className="fb-callout" role="alert">{error}</div>}
          <button className="fb-btn fb-btn-solid" style={{ width: "100%", marginTop: ".3rem" }} type="submit" disabled={submitting}>
            {submitting ? "Authenticating…" : "Sign in to FINBRAIN"}
          </button>
          <div className="fb-fine">Accounts and roles are provisioned by the FinBrain administrator.</div>
        </form>
      </div>
    </div>
  );
}
