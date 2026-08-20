import { useState, type ReactNode } from "react";
import { useAppState, type Screen } from "../lib/appState";
import { useAuth } from "../auth/AuthProvider";
import { useI18n } from "../lib/i18n";
import { PERSONAS } from "../lib/personas";
import { useActiveSection, useScrollY } from "../lib/interactivity";
import { useUiChrome } from "../lib/uiChrome";
import { useTheme } from "../lib/theme";
import { LogoMark, Wordmark } from "./Logo";

const MARKETING_SECTIONS = ["landing-flow", "landing-agents", "landing-proof", "landing-why", "landing-pricing", "landing-faq"];

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

const MARKETING_NAV_ITEMS = [
  { id: "landing-flow", label: "Product" },
  { id: "landing-agents", label: "AI Agents" },
  { id: "landing-proof", label: "Proof" },
  { id: "landing-why", label: "Why Us" },
  { id: "landing-pricing", label: "Pricing" },
  { id: "landing-faq", label: "FAQ" },
];

export function MarketingNav() {
  const { show } = useAppState();
  const { theme, toggle } = useTheme();
  const scrollY = useScrollY();
  const active = useActiveSection(MARKETING_SECTIONS);
  const [menuOpen, setMenuOpen] = useState(false);
  const scrollTo = (id: string) => {
    setMenuOpen(false);
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
  };
  const linkClass = (id: string) => (active === id ? "is-current" : undefined);
  return (
    <nav className={"fb-mkt-nav" + (scrollY > 12 ? " is-scrolled" : "")}>
      <button className="fb-mkt-wordmark" onClick={() => show("landing")}>
        <LogoMark large />FINBRAIN OS
      </button>
      <div className="fb-mkt-nav-links">
        {MARKETING_NAV_ITEMS.map((item) => (
          <span key={item.id} className={linkClass(item.id)} tabIndex={0} role="button" onClick={() => scrollTo(item.id)}>{item.label}</span>
        ))}
      </div>
      <div className="fb-mkt-nav-actions">
        <button
          className="fb-mkt-theme-toggle"
          type="button"
          onClick={toggle}
          aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
        >
          {theme === "dark" ? "☀" : "☾"}
        </button>
        <span tabIndex={0} role="button" onClick={() => show("login")}>Log in</span>
        <button className="fb-mkt-btn is-accent" onClick={() => show("signup")}>Get Started</button>
        <button
          className={"fb-mkt-nav-toggle" + (menuOpen ? " is-open" : "")}
          type="button"
          aria-expanded={menuOpen}
          aria-label={menuOpen ? "Close menu" : "Open menu"}
          onClick={() => setMenuOpen((v) => !v)}
        >
          <span /><span /><span />
        </button>
      </div>
      {menuOpen && (
        <div className="fb-mkt-nav-mobile-menu" role="menu">
          {MARKETING_NAV_ITEMS.map((item) => (
            <span key={item.id} className={linkClass(item.id)} tabIndex={0} role="menuitem" onClick={() => scrollTo(item.id)}>{item.label}</span>
          ))}
        </div>
      )}
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

const NAV_ICONS: Record<string, ReactNode> = {
  home: <><path d="M3 11l9-7 9 7" /><path d="M5 10v9a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1v-9" /></>,
  agents: <path d="M4 4h13a3 3 0 0 1 3 3v7a3 3 0 0 1-3 3H9l-5 3v-3a3 3 0 0 1-3-3V7a3 3 0 0 1 3-3z" />,
  einvoice: <path d="M6 2h9l3 3v17H6z M9 8h6M9 12h6M9 16h4" />,
  finance: <path d="M4 19V9M10 19V5M16 19v-7M22 19H2" />,
  audit: <path d="M12 3 20 6.5v5.3c0 4.7-3.2 8.9-8 10.2-4.8-1.3-8-5.5-8-10.2V6.5z" />,
  approvals: <path d="M9 12l2 2 4-4M12 3l8 4v5c0 4.5-3.2 8.5-8 10-4.8-1.5-8-5.5-8-10V7z" />,
  ingestion: <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 9l5-5 5 5M12 4v13" />,
};

const NAV_GROUPS: { label: string | null; items: { screen: Screen; key: string }[] }[] = [
  { label: null, items: [{ screen: "home", key: "nav.home" }, { screen: "agents", key: "nav.aiAgents" }] },
  { label: "Records", items: [
    { screen: "einvoice", key: "nav.einvoicing" },
    { screen: "finance", key: "nav.financeDashboard" },
  ] },
  { label: "Oversight", items: [
    { screen: "audit", key: "nav.audit" },
    { screen: "approvals", key: "nav.approvals" },
    { screen: "ingestion", key: "nav.ingestion" },
  ] },
];

export function Sidebar({ current, backTo, backLabel }: { current?: Screen; backTo?: () => void; backLabel?: string }) {
  const { show, approvalsCount } = useAppState();
  const { t } = useI18n();
  const { sidebarOpen, openSidebar, closeSidebar } = useUiChrome();

  const navigate = (screen: Screen) => {
    closeSidebar();
    show(screen);
  };

  return (
    <>
      {!sidebarOpen && (
        <button
          className="fb-sidebar-toggle"
          type="button"
          onClick={openSidebar}
          aria-label="Open navigation"
          aria-expanded={sidebarOpen}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16" /></svg>
        </button>
      )}
      {sidebarOpen && <div className="fb-sidebar-backdrop" onClick={closeSidebar} />}

      <aside className={"fb-sidebar" + (sidebarOpen ? " is-open" : "")}>
        <div className="fb-sidebar-top">
          <Wordmark onClick={() => navigate("landing")} />
          <button className="fb-sidebar-close" type="button" onClick={closeSidebar} aria-label="Close navigation">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12" /></svg>
          </button>
        </div>

        {backTo ? (
          <button className="fb-sidebar-back" type="button" onClick={backTo}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M19 12H5M12 19l-7-7 7-7" /></svg>
            {backLabel}
          </button>
        ) : (
          <nav className="fb-sidebar-nav">
            {NAV_GROUPS.map((group) => (
              <div className="fb-sidebar-group" key={group.label ?? "primary"}>
                {group.label && <div className="fb-sidebar-group-label">{group.label}</div>}
                {group.items.map((link) => (
                  <button
                    key={link.screen}
                    className={"fb-sidebar-link" + (current === link.screen ? " is-current" : "")}
                    type="button"
                    onClick={() => navigate(link.screen)}
                  >
                    <span className="fb-sidebar-icon">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{NAV_ICONS[link.screen]}</svg>
                    </span>
                    <span className="fb-sidebar-label">{t(link.key)}</span>
                    {link.screen === "approvals" && approvalsCount > 0 && (
                      <span className="fb-nav-badge">{approvalsCount}</span>
                    )}
                  </button>
                ))}
              </div>
            ))}
          </nav>
        )}
      </aside>
    </>
  );
}

const SCREEN_TITLES: Partial<Record<Screen, string>> = {
  home: "Home",
  agents: "Customer Intelligence",
  einvoice: "e-Invoicing",
  "einvoice-detail": "e-Invoicing",
  finance: "Finance Dashboard",
  audit: "Audit Trail",
  approvals: "Approvals",
  ingestion: "Message Capture",
};

export function AppTopBar({ current }: { current: Screen }) {
  const { show, askRole, approvalsCount } = useAppState();
  const { openAsk, openPalette } = useUiChrome();
  const { identity, signOut } = useAuth();
  const { lang, setLang, t } = useI18n();
  const [profileOpen, setProfileOpen] = useState(false);
  const activeRole = identity?.role ?? askRole;
  const email = identity?.email ?? "Authenticated user";

  return (
    <div className="fb-topbar">
      <div className="fb-topbar-crumb">
        {current === "home" ? (
          <span className="fb-topbar-current">Home</span>
        ) : (
          <>
            <span tabIndex={0} role="button" onClick={() => show("home")}>Home</span>
            <span className="fb-topbar-sep">/</span>
            <span className="fb-topbar-current">{SCREEN_TITLES[current] ?? current}</span>
          </>
        )}
      </div>

      <button className="fb-topbar-search" type="button" onClick={openPalette}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" /></svg>
        <span>Search records, invoices, or ask FinBrain…</span>
        <span className="fb-topbar-kbd">⌘K</span>
      </button>

      <div className="fb-topbar-actions">
        <button className="fb-topbar-icon-btn" type="button" onClick={() => show("finance")} title="Upcoming invoice due dates" aria-label="Upcoming invoice due dates">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="18" rx="2" /><path d="M16 2v4M8 2v4M3 10h18" /></svg>
        </button>
        <button className="fb-topbar-icon-btn" type="button" onClick={() => show("approvals")} title="Pending approvals" aria-label="Pending approvals">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.73 21a2 2 0 0 1-3.46 0" /></svg>
          {approvalsCount > 0 && <span className="fb-nav-badge fb-topbar-badge">{approvalsCount}</span>}
        </button>
        <button className="fb-topbar-ask" type="button" onClick={openAsk}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 4h13a3 3 0 0 1 3 3v7a3 3 0 0 1-3 3H9l-5 3v-3a3 3 0 0 1-3-3V7a3 3 0 0 1 3-3z" /></svg>
          <span>Ask FinBrain</span>
        </button>

        <div
          className="fb-topbar-profile"
          onBlur={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget as Node)) setProfileOpen(false);
          }}
        >
          <button className="fb-topbar-profile-trigger" type="button" onClick={() => setProfileOpen((v) => !v)} aria-haspopup="true" aria-expanded={profileOpen}>
            <span className="fb-topbar-avatar" aria-hidden="true">{email[0]?.toUpperCase() ?? "?"}</span>
            <span className="fb-topbar-profile-text">
              <span className="fb-topbar-profile-email">{email}</span>
              <span className="fb-topbar-profile-role">{PERSONAS[activeRole].label}</span>
            </span>
            <svg className="fb-topbar-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
          </button>
          {profileOpen && (
            <div className="fb-topbar-profile-menu" role="menu">
              <div className="fb-sidebar-lang-row" role="tablist" aria-label="Language">
                <button className={lang === "en" ? "is-current" : undefined} type="button" onClick={() => setLang("en")}>EN</button>
                <button className={lang === "ms" ? "is-current" : undefined} type="button" onClick={() => setLang("ms")}>BM</button>
                <button className={lang === "zh" ? "is-current" : undefined} type="button" onClick={() => setLang("zh")}>中文</button>
              </div>
              <button className="fb-sidebar-logout" type="button" onClick={() => void signOut().then(() => show("landing"))}>{t("nav.logout")}</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
