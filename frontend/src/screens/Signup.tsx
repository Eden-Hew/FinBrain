import { useState } from "react";
import { useAppState } from "../lib/appState";
import { LogoMark } from "../components/Logo";

export default function Signup() {
  const { show, goToSecurity, setSignupInfo } = useAppState();
  const [step, setStep] = useState<"form" | "success">("form");
  const [name, setName] = useState("");
  const [company, setCompany] = useState("");
  const [email, setEmail] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setSignupInfo(name.trim(), company.trim());
    setStep("success");
  };

  return (
    <div className="fb-root">
      <div className="fb-login-wrap">
        <div className="fb-login-story" style={{ background: "#1a1a1a", color: "#f4f1ea" }}>
          <button className="fb-wordmark" style={{ color: "#f4f1ea", fontSize: "1rem" }} onClick={() => show("landing")}>
            <LogoMark large />FINBRAIN OS
          </button>
          <div>
            <div className="fb-eyebrow" style={{ color: "#b3ac99" }}>Start your free trial</div>
            <h1 style={{ fontSize: "1.7rem", fontWeight: 500, lineHeight: 1.35, margin: ".7rem 0" }}>Set up your workspace in minutes.</h1>
            <p className="fb-sans" style={{ fontSize: ".78rem", color: "#b3ac99", maxWidth: "340px", margin: 0 }}>No credit card required for the trial. Connect Gmail, Drive, and Sheets once you're in.</p>
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
          </div>
          <div className="fb-sans" style={{ fontSize: ".68rem" }}>
            <span tabIndex={0} role="button" style={{ cursor: "pointer", color: "#b3ac99", textDecoration: "underline" }} onClick={() => goToSecurity("signup")}>Learn more about our security &amp; compliance approach →</span>
          </div>
        </div>
        <div className="fb-login-form">
          {step === "form" ? (
            <form onSubmit={handleSubmit}>
              <div className="fb-eyebrow">Create your account</div>
              <h2 style={{ fontSize: "1.2rem", fontWeight: 700, margin: ".2rem 0" }}>Get started with FINBRAIN OS</h2>
              <p style={{ fontSize: ".75rem", color: "var(--ink-soft)", margin: "0 0 .4rem" }}>This is a prototype — no account is actually created, but the flow behaves like a real one.</p>

              <label className="fb-field-label" htmlFor="fb-signup-name">Full name
                <input className="fb-field-mock" id="fb-signup-name" name="name" type="text" autoComplete="name" required value={name} onChange={(e) => setName(e.target.value)} />
              </label>
              <label className="fb-field-label" htmlFor="fb-signup-company">Company name
                <input className="fb-field-mock" id="fb-signup-company" name="company" type="text" autoComplete="organization" required value={company} onChange={(e) => setCompany(e.target.value)} />
              </label>
              <label className="fb-field-label" htmlFor="fb-signup-email">Work email
                <input className="fb-field-mock" id="fb-signup-email" name="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
              </label>
              <label className="fb-field-label" htmlFor="fb-signup-password">Password
                <input className="fb-field-mock" id="fb-signup-password" name="password" type="password" autoComplete="new-password" minLength={8} required />
              </label>

              <button className="fb-btn fb-btn-solid" style={{ width: "100%", marginTop: ".3rem" }} type="submit">Create account</button>
              <div className="fb-fine">Already have an account? <span style={{ cursor: "pointer", textDecoration: "underline", color: "var(--ink)" }} tabIndex={0} role="button" onClick={() => show("login")}>Log in</span></div>
            </form>
          ) : (
            <div>
              <div className="fb-eyebrow">You're almost in</div>
              <h2 style={{ fontSize: "1.2rem", fontWeight: 700, margin: ".2rem 0 .8rem" }}>Check your email</h2>
              <p style={{ fontSize: ".8rem", color: "var(--ink-soft)", margin: "0 0 1.3rem" }}>
                We've sent a verification link to {email}. While that arrives, let's set up your workspace.
              </p>
              <button className="fb-btn fb-btn-solid" style={{ width: "100%" }} type="button" onClick={() => show("onboarding")}>Continue to workspace setup</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
