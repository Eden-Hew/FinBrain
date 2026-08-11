import { useAppState, type Screen } from "../lib/appState";
import { useI18n } from "../lib/i18n";
import { FB_ROLE_IDENTITY } from "../data/sampleData";
import { Wordmark } from "./Logo";

export function LandingNav() {
  const { show } = useAppState();
  const scrollTo = (id: string) => document.getElementById(id)?.scrollIntoView();
  return (
    <nav className="fb-nav">
      <Wordmark onClick={() => show("landing")} />
      <div className="fb-nav-links">
        <span tabIndex={0} role="button" onClick={() => scrollTo("landing-flow")}>Product</span>
        <span tabIndex={0} role="button" onClick={() => scrollTo("landing-agents")}>AI Agents</span>
        <span tabIndex={0} role="button" onClick={() => scrollTo("landing-proof")}>Proof</span>
        <span tabIndex={0} role="button" onClick={() => scrollTo("landing-why")}>Why Us</span>
        <span tabIndex={0} role="button" onClick={() => scrollTo("landing-pricing")}>Pricing</span>
      </div>
      <div className="fb-nav-actions">
        <span style={{ cursor: "pointer", color: "var(--ink-soft)" }} tabIndex={0} role="button" onClick={() => show("login")}>Log in</span>
        <button className="fb-btn fb-btn-solid" onClick={() => show("signup")}>Get Started</button>
      </div>
    </nav>
  );
}

export function ContextNav() {
  const { contextBack, returnTo, show } = useAppState();
  const backLabel = returnTo === "login" ? "← Back to login" : returnTo === "signup" ? "← Back to sign up" : "← Back to site";
  const ctaLabel = returnTo === "signup" ? "Continue signing up" : "Start free trial";
  return (
    <nav className="fb-nav">
      <Wordmark onClick={() => show("landing")} />
      <div className="fb-nav-links">
        <span tabIndex={0} role="button" onClick={contextBack}>{backLabel}</span>
      </div>
      <div className="fb-nav-actions">
        <span style={{ cursor: "pointer", color: "var(--ink-soft)" }} tabIndex={0} role="button" onClick={() => show("login")}>Log in</span>
        <button className="fb-btn fb-btn-solid" onClick={() => show("signup")}>{ctaLabel}</button>
      </div>
    </nav>
  );
}

const NAV_LINKS: { screen: Screen; key: string }[] = [
  { screen: "agents", key: "nav.aiAgents" },
  { screen: "einvoice", key: "nav.einvoicing" },
  { screen: "finance", key: "nav.financeDashboard" },
  { screen: "audit", key: "nav.audit" },
  { screen: "approvals", key: "nav.approvals" },
];

export function AppNav({ current, backTo, backLabel }: { current?: Screen; backTo?: () => void; backLabel?: string }) {
  const { show, askRole, approvalsCount } = useAppState();
  const { lang, setLang, t } = useI18n();
  const identity = FB_ROLE_IDENTITY[askRole];

  return (
    <nav className="fb-app-nav">
      {backTo ? (
        <div style={{ display: "flex", alignItems: "center", gap: "1.2rem" }}>
          <Wordmark onClick={() => show("landing")} />
          <span className="fb-sans" style={{ cursor: "pointer", color: "var(--ink-soft)", fontSize: ".75rem" }} tabIndex={0} role="button" onClick={backTo}>
            {backLabel}
          </span>
        </div>
      ) : (
        <>
          <Wordmark onClick={() => show("landing")} />
          <div className="fb-app-nav-links">
            {NAV_LINKS.map((link) => (
              <span key={link.screen} className={current === link.screen ? "is-current" : undefined} onClick={() => show(link.screen)}>
                <span>{t(link.key)}</span>
                {link.screen === "approvals" && approvalsCount > 0 && (
                  <span className="fb-nav-badge">{approvalsCount}</span>
                )}
              </span>
            ))}
          </div>
        </>
      )}
      <div className="fb-app-nav-user">
        <div className="fb-role-switch" role="tablist" style={{ margin: 0 }}>
          <button className={"fb-role-btn fb-lang-btn" + (lang === "en" ? " is-current" : "")} type="button" onClick={() => setLang("en")}>EN</button>
          <button className={"fb-role-btn fb-lang-btn" + (lang === "ms" ? " is-current" : "")} type="button" onClick={() => setLang("ms")}>BM</button>
          <button className={"fb-role-btn fb-lang-btn" + (lang === "zh" ? " is-current" : "")} type="button" onClick={() => setLang("zh")}>中文</button>
        </div>
        <span className="fb-nav-user-name">{identity.name}</span>
        <span className="fb-nav-user-role">{identity.role}</span>
        <span style={{ cursor: "pointer" }} tabIndex={0} role="button" onClick={() => show("landing")}>{t("nav.logout")}</span>
      </div>
    </nav>
  );
}
