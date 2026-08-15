import { LogoMark } from "../components/Logo";
import { useAppState } from "../lib/appState";

export default function Signup() {
  const { show, goToSecurity } = useAppState();
  return (
    <div className="fb-root">
      <div className="fb-login-wrap">
        <div className="fb-login-story" style={{ background: "#1a1a1a", color: "#f4f1ea" }}>
          <button className="fb-wordmark" style={{ color: "#f4f1ea", fontSize: "1rem" }} onClick={() => show("landing")}>
            <LogoMark large />FINBRAIN OS
          </button>
          <div>
            <div className="fb-eyebrow" style={{ color: "#b3ac99" }}>Controlled provisioning</div>
            <h1 style={{ fontSize: "1.7rem", fontWeight: 500, lineHeight: 1.35, margin: ".7rem 0" }}>Workspace access follows verified identity and assigned responsibility.</h1>
            <p className="fb-sans" style={{ color: "#b3ac99" }}>Public self-registration is disabled for this protected demonstration workspace.</p>
          </div>
          <button className="fb-btn fb-btn-outline" type="button" onClick={() => goToSecurity("signup")}>Review the security model</button>
        </div>
        <div className="fb-login-form">
          <div className="fb-eyebrow">Request access</div>
          <h2>Ask the FinBrain administrator to provision your account.</h2>
          <p className="fb-fine">The administrator creates your Supabase Auth user and assigns one backend-controlled FinBrain role.</p>
          <button className="fb-btn fb-btn-solid" type="button" onClick={() => show("login")}>Return to login</button>
        </div>
      </div>
    </div>
  );
}
