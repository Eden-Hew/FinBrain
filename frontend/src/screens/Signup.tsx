import { LogoMark } from "../components/Logo";
import { useAppState } from "../lib/appState";
import { useParallax } from "../lib/interactivity";

export default function Signup() {
  const { show, goToSecurity } = useAppState();
  const { ref: storyRef, offset: storyOffset, onMouseMove: onStoryMouseMove, onMouseLeave: onStoryMouseLeave } = useParallax<HTMLDivElement>(16);
  return (
    <div className="fb-root fb-mkt">
      <div className="fb-mkt-auth-wrap">
        <div className="fb-mkt-auth-story" ref={storyRef} onMouseMove={onStoryMouseMove} onMouseLeave={onStoryMouseLeave}>
          <div
            className="fb-mkt-blob"
            style={{ width: 340, height: 340, top: -120, left: -100, background: "var(--a-accent)", transform: `translate3d(${storyOffset.x}px, ${storyOffset.y}px, 0)` }}
            aria-hidden="true"
          />
          <div
            className="fb-mkt-blob"
            style={{ width: 260, height: 260, bottom: -100, right: -80, background: "var(--a-purple)", transform: `translate3d(${-storyOffset.x * 1.2}px, ${-storyOffset.y * 1.2}px, 0)` }}
            aria-hidden="true"
          />
          <button className="fb-mkt-wordmark" style={{ position: "relative", zIndex: 1 }} onClick={() => show("landing")}>
            <LogoMark large />FINBRAIN OS
          </button>
          <div className="fb-mkt-auth-copy">
            <div className="fb-mkt-eyebrow" style={{ position: "relative", zIndex: 1 }}>Controlled provisioning</div>
            <h1>Workspace access follows verified identity and assigned responsibility.</h1>
            <p>Public self-registration is disabled for this protected demonstration workspace.</p>
          </div>
          <button className="fb-mkt-btn is-outline" style={{ position: "relative", zIndex: 1, alignSelf: "flex-start" }} type="button" onClick={() => goToSecurity("signup")}>Review the security model</button>
        </div>
        <div className="fb-mkt-auth-form-wrap">
          <div className="fb-mkt-auth-form">
            <div className="fb-mkt-eyebrow is-plain">Request access</div>
            <h2>Ask the FinBrain administrator to provision your account.</h2>
            <p className="fb-mkt-fine">The administrator creates your Supabase Auth user and assigns one backend-controlled FinBrain role.</p>
            <button className="fb-mkt-btn is-accent is-lg" style={{ width: "100%", justifyContent: "center" }} type="button" onClick={() => show("login")}>Return to login</button>
          </div>
        </div>
      </div>
    </div>
  );
}
