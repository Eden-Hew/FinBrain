import { useState, type CSSProperties, type ReactNode } from "react";
import { useAppState } from "../lib/appState";
import { MarketingNav } from "../components/Nav";
import { LogoMark, Wordmark } from "../components/Logo";
import { useControllableCycle, useCountUp, useInView, useParallax, useTilt, useTypewriterDemo, type TypewriterDemoItem } from "../lib/interactivity";
import { CookieConsentBanner, SupportWidget } from "../components/MarketingWidgets";

const HERO_NAV_ICONS: Record<string, ReactNode> = {
  home: <><path d="M3 11l9-7 9 7" /><path d="M5 10v9a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1v-9" /></>,
  agents: <path d="M4 4h13a3 3 0 0 1 3 3v7a3 3 0 0 1-3 3H9l-5 3v-3a3 3 0 0 1-3-3V7a3 3 0 0 1 3-3z" />,
  customers: <><circle cx="9" cy="7" r="3.2" /><path d="M2.5 20a6.5 6.5 0 0 1 13 0" /><circle cx="17.5" cy="8.5" r="2.4" /><path d="M15.3 12.3A5.2 5.2 0 0 1 21.5 17" /></>,
  einvoice: <path d="M6 2h9l3 3v17H6z M9 8h6M9 12h6M9 16h4" />,
  finance: <path d="M4 19V9M10 19V5M16 19v-7M22 19H2" />,
  audit: <path d="M12 3 20 6.5v5.3c0 4.7-3.2 8.9-8 10.2-4.8-1.3-8-5.5-8-10.2V6.5z" />,
  approvals: <path d="M9 12l2 2 4-4M12 3l8 4v5c0 4.5-3.2 8.5-8 10-4.8-1.5-8-5.5-8-10V7z" />,
  ingestion: <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 9l5-5 5 5M12 4v13" />,
};

const HERO_NAV_GROUPS: { label: string | null; items: { key: string; label: string }[] }[] = [
  { label: null, items: [{ key: "home", label: "Briefing" }, { key: "agents", label: "Ask" }, { key: "customers", label: "Customers" }] },
  { label: "Records", items: [{ key: "einvoice", label: "e-Invoicing" }, { key: "finance", label: "Financial Intelligence" }] },
  { label: "Oversight", items: [{ key: "approvals", label: "Workflows" }, { key: "ingestion", label: "Sources" }, { key: "audit", label: "Audit & Access" }] },
];

const HERO_SCREENS = ["customers", "agents", "finance", "audit"];

const HERO_DEMOS: TypewriterDemoItem[] = [
  {
    question: "Which accounts are overdue?",
    answer: "Meridian Corp (RM 18,400) and 2 other accounts are 30+ days past due. Draft a follow-up?",
    citation: "Bank statement reconciliation",
    pill: "Restricted",
  },
  {
    question: "Which invoices need review?",
    answer: "Office Supplies Sdn Bhd (RM 545.90) is flagged — missing a supplier TIN. Send back for correction?",
    citation: "MyInvois validation",
    pill: "Restricted",
  },
  {
    question: "Why are approvals delayed?",
    answer: "3 approvals have sat over 48 hours, all waiting on Finance Ops sign-off. Escalate to the owner?",
    citation: "Workflow audit trail",
    pill: "Restricted",
  },
  {
    question: "Who hasn't paid us this month?",
    answer: "4 customers show no payment against a validated invoice this month, totaling RM 12,600.",
    citation: "Financial Intelligence · AR aging",
    pill: "Restricted",
  },
];

const HERO_DEMO_CHIP_LABELS = ["Overdue accounts", "Invoices to review", "Delayed approvals", "Unpaid this month"];

const AGENTS = [
  {
    tone: "is-blue",
    title: "Ask",
    body: "Ask a question, get a cited answer instantly — drafts follow-ups and collections chases, permission-filtered to your role.",
    icon: <path d="M4 4h13a3 3 0 0 1 3 3v7a3 3 0 0 1-3 3H9l-5 3v-3a3 3 0 0 1-3-3V7a3 3 0 0 1 3-3z" />,
  },
  {
    tone: "is-green",
    title: "Customers",
    body: "Every customer ranked by real urgency — overdue amounts, verified cross-source signals — with outreach that always waits for your approval before it sends.",
    icon: <><circle cx="9" cy="7" r="3.2" /><path d="M2.5 20a6.5 6.5 0 0 1 13 0" /><circle cx="17.5" cy="8.5" r="2.4" /><path d="M15.3 12.3A5.2 5.2 0 0 1 21.5 17" /></>,
  },
  {
    tone: "is-purple",
    title: "e-Invoicing",
    body: "Snap a receipt → OCR → MyInvois-compliant e-invoice, PDPA-masked before it's ever stored.",
    icon: <path d="M6 2h9l3 3v17H6z M9 8h6M9 12h6M9 16h4" />,
  },
  {
    tone: "is-orange",
    title: "Financial Intelligence",
    body: "Interactive revenue, profit, and AR charts — hover for exact figures, jump straight into what's overdue.",
    icon: <path d="M4 19V9M10 19V5M16 19v-7M22 19H2" />,
  },
  {
    tone: "is-blue",
    title: "Workflows",
    body: "Every agent action — an invoice, a client email — waits for your confirmation. Nothing ships on its own.",
    icon: <path d="M9 12l2 2 4-4M12 3l8 4v5c0 4.5-3.2 8.5-8 10-4.8-1.5-8-5.5-8-10V7z" />,
  },
  {
    tone: "is-green",
    title: "Sources",
    body: "Telegram, email, and file uploads — captured live, protected before any text reaches an AI model.",
    icon: <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 9l5-5 5 5M12 4v13" />,
  },
  {
    tone: "is-purple",
    title: "Audit & Access",
    body: "Every access decision hash-chained, searchable by actor, grouped by day — nothing gets buried.",
    icon: <path d="M12 3 20 6.5v5.3c0 4.7-3.2 8.9-8 10.2-4.8-1.3-8-5.5-8-10.2V6.5z" />,
  },
];

const PRICING = [
  {
    tier: "Starter", highlighted: false, price: "RM 299", note: "For a single finance lead getting started.",
    features: ["1 seat", "100 AI queries / month", "Up to 50 e-invoices / month", "English only", "Email support"],
    cta: "Start free trial",
  },
  {
    tier: "Team · Most popular", highlighted: true, price: "RM 899", note: "For a finance team running invoicing, collections and reporting together.",
    features: ["5 seats", "Unlimited AI queries", "Up to 500 e-invoices / month", "English, Malay & Chinese", "Telegram receipt bot", "Priority support"],
    cta: "Start free trial",
  },
  {
    tier: "Enterprise", highlighted: false, price: "Custom", note: "For multi-entity finance functions with compliance requirements.",
    features: ["Unlimited seats", "SSO & role-based provisioning", "Extended audit retention", "Custom integrations", "Dedicated success manager"],
    cta: "Contact us",
  },
];

function buildSupportTopics(
  show: (screen: "signup" | "login") => void,
  goToSecurity: (from: "landing") => void,
): { label: string; reply: string; action?: { label: string; onClick: () => void } }[] {
  return [
    {
      label: "Pricing",
      reply: "Starter is RM 299/mo (1 seat, 100 AI queries), Team is RM 899/mo (5 seats, unlimited queries — most popular), and Enterprise is custom-priced.",
      action: { label: "Start free trial", onClick: () => show("signup") },
    },
    {
      label: "Security & PDPA",
      reply: "Personal identifiers are masked before they're ever stored, and every AI answer is permission-aware and cited back to its source record.",
      action: { label: "Read about security", onClick: () => goToSecurity("landing") },
    },
    {
      label: "Getting started",
      reply: "The fastest way in is a free trial — no card required for this prototype.",
      action: { label: "Start free trial", onClick: () => show("signup") },
    },
  ];
}

const FAQ_ITEMS = [
  {
    q: "Is this a real product, or a demo?",
    a: "It's a working prototype — the finance dashboard, audit trail, and e-invoicing flow are functional, not mockups. Pricing and billing are illustrative, not a live payment system, and that's stated wherever numbers appear.",
  },
  {
    q: "How is my data protected under PDPA?",
    a: "Personal identifiers like IC numbers and phone numbers are masked immediately after OCR — before any extracted field is stored or sent to an AI model. Only the fields MyInvois requires are retained.",
  },
  {
    q: "Can FinBrain actually submit e-invoices to LHDN?",
    a: "Yes — receipts and invoices are mapped to the MyInvois schema, validated for missing fields before submission, and tracked through the same status pipeline your finance team would use manually.",
  },
  {
    q: "What happens if someone asks for data outside their role?",
    a: "The AI agent enforces the same role-based access as the rest of the app. A request outside your role is declined and logged in the audit trail at the point of the request — not filtered out afterward.",
  },
  {
    q: "What languages does it support?",
    a: "English, Bahasa Malaysia, and Chinese for the AI agent and interface — switchable anytime from your profile menu, no separate setup required.",
  },
  {
    q: "Do I need to connect anything before I can try it?",
    a: "No — the free trial starts with a sample workspace so you can explore the dashboard, audit trail, and AI agent before connecting Telegram, email, or your own records.",
  },
];

function FaqAccordion() {
  const [openIndex, setOpenIndex] = useState<number | null>(0);
  return (
    <div className="fb-mkt-faq-list">
      {FAQ_ITEMS.map((item, i) => {
        const open = openIndex === i;
        return (
          <div className={"fb-mkt-faq-item" + (open ? " is-open" : "")} key={item.q}>
            <button
              className="fb-mkt-faq-question"
              type="button"
              onClick={() => setOpenIndex(open ? null : i)}
              aria-expanded={open}
            >
              {item.q}
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
            </button>
            <div className="fb-mkt-faq-answer-wrap" aria-hidden={!open}>
              <div className="fb-mkt-faq-answer-inner">
                <p className="fb-mkt-faq-answer">{item.a}</p>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Reveal({ children, className = "", id, style }: { children: ReactNode; className?: string; id?: string; style?: CSSProperties }) {
  const [ref, inView] = useInView<HTMLElement>();
  const cls = className + " fb-mkt-reveal" + (inView ? " is-visible" : "");
  return <section ref={ref} id={id} className={cls} style={style}>{children}</section>;
}

function AgentCard({ tone, title, body, icon, index, featured }: { tone: string; title: string; body: string; icon: ReactNode; index: number; featured?: boolean }) {
  const [ref, inView] = useInView<HTMLDivElement>();
  return (
    <div ref={ref} className={"fb-mkt-agent-card fb-mkt-reveal" + (featured ? " is-featured" : "") + (inView ? " is-visible" : "")} style={{ transitionDelay: inView ? `${index * 80}ms` : "0ms" }}>
      {featured && <span className="fb-mkt-agent-featured-tag">Start here</span>}
      <div className={"fb-mkt-icon-badge " + tone}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{icon}</svg>
      </div>
      <h3>{title}</h3>
      <p>{body}</p>
    </div>
  );
}

function PricingCard({ tier, highlighted, price, note, features, cta, onCta, index }: { tier: string; highlighted: boolean; price: string; note: string; features: string[]; cta: string; onCta: () => void; index: number }) {
  const [ref, inView] = useInView<HTMLDivElement>();
  return (
    <div ref={ref} className={"fb-mkt-pricing-card fb-mkt-reveal" + (highlighted ? " is-highlighted" : "") + (inView ? " is-visible" : "")} style={{ transitionDelay: inView ? `${index * 90}ms` : "0ms" }}>
      <div className={"fb-mkt-eyebrow" + (highlighted ? "" : " is-plain")}>{tier}</div>
      <div className="fb-mkt-pricing-amount">{price}{price !== "Custom" && <span>/month</span>}</div>
      <p className="fb-mkt-pricing-note">{note}</p>
      <ul className="fb-mkt-pricing-features">
        {features.map((f) => <li key={f}>{f}</li>)}
      </ul>
      {cta === "Contact us" ? (
        <a className="fb-mkt-btn is-outline" style={{ width: "100%", justifyContent: "center" }} href="mailto:hello@finbrainos.example">Contact us</a>
      ) : (
        <button className={"fb-mkt-btn " + (highlighted ? "is-accent" : "is-outline")} style={{ width: "100%", justifyContent: "center" }} type="button" onClick={onCta}>{cta}</button>
      )}
    </div>
  );
}

function AnimatedStat({ value, label, active }: { value: string; label: string; active: boolean }) {
  const match = value.match(/^([^\d]*)(\d+(?:\.\d+)?)(.*)$/);
  const prefix = match?.[1] ?? "";
  const numStr = match?.[2] ?? "0";
  const suffix = match?.[3] ?? "";
  const decimals = numStr.includes(".") ? numStr.split(".")[1].length : 0;
  const target = parseFloat(numStr);
  const current = useCountUp(target, active, 1200);
  return (
    <div className="fb-mkt-stat">
      <strong>{prefix}{current.toFixed(decimals)}{suffix}</strong>
      <span>{label}</span>
    </div>
  );
}

export default function Landing() {
  const { show, goToSecurity, goToLegal } = useAppState();
  // Destructured (rather than passed as `heroParallax.ref` etc.) because the
  // react-hooks/refs compiler rule treats any member access on a hook-returned
  // object holding a ref as a ref read, even for unrelated sibling fields.
  const {
    ref: heroParallaxRef,
    offset: heroParallaxOffset,
    onMouseMove: onHeroMouseMove,
    onMouseLeave: onHeroMouseLeave,
  } = useParallax<HTMLElement>(20);
  const {
    ref: previewTiltRef,
    style: previewTiltStyle,
    onMouseMove: onPreviewMouseMove,
    onMouseLeave: onPreviewMouseLeave,
  } = useTilt<HTMLDivElement>(9);
  const [statsRef, statsIn] = useInView<HTMLDivElement>({ threshold: 0.4 });
  const { demo, typed, phase, demoIndex, select: selectDemo } = useTypewriterDemo(HERO_DEMOS);
  const [screenIndex, selectScreen] = useControllableCycle(HERO_SCREENS.length, 4500);
  const activeScreen = HERO_SCREENS[screenIndex];

  const tryQuestion = (index: number) => {
    selectDemo(index);
    const agentsIndex = HERO_SCREENS.indexOf("agents");
    if (agentsIndex >= 0) selectScreen(agentsIndex);
  };

  const supportTopics = buildSupportTopics(show, goToSecurity);

  return (
    <div className="fb-root fb-mkt">
      <MarketingNav />

      <section className="fb-mkt-hero" ref={heroParallaxRef} onMouseMove={onHeroMouseMove} onMouseLeave={onHeroMouseLeave}>
        <div
          className="fb-mkt-blob"
          style={{ width: 460, height: 460, top: -160, left: -120, background: "var(--a-accent)", transform: `translate3d(${heroParallaxOffset.x}px, ${heroParallaxOffset.y}px, 0)` }}
          aria-hidden="true"
        />
        <div
          className="fb-mkt-blob"
          style={{ width: 360, height: 360, top: 60, right: -140, background: "var(--a-purple)", transform: `translate3d(${-heroParallaxOffset.x * 1.3}px, ${-heroParallaxOffset.y * 1.3}px, 0)` }}
          aria-hidden="true"
        />
        <div className="fb-mkt-hero-copy">
          <div className="fb-mkt-eyebrow">Permission-Aware AI for Finance Teams</div>
          <h1>Ask your business.<br />Get answers you can prove.</h1>
          <p>One knowledge base, cited answers, and AI agents that handle the busywork — invoicing, approvals, follow-ups — without touching data they shouldn't see.</p>
          <div className="fb-mkt-hero-ctas">
            <button className="fb-mkt-btn is-accent is-lg" onClick={() => show("signup")}>Start free trial</button>
            <button className="fb-mkt-btn is-outline is-lg" type="button" onClick={() => document.getElementById("landing-agents")?.scrollIntoView({ behavior: "smooth" })}>See it in action</button>
          </div>
          <div className="fb-mkt-try-row">
            <span className="fb-mkt-try-label">Try asking —</span>
            {HERO_DEMO_CHIP_LABELS.map((label, index) => (
              <button
                key={label}
                type="button"
                className={"fb-mkt-try-chip" + (activeScreen === "agents" && demoIndex === index ? " is-active" : "")}
                onClick={() => tryQuestion(index)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <div className="fb-mkt-preview">
          <div
            className="fb-mkt-preview-card"
            ref={previewTiltRef}
            onMouseMove={onPreviewMouseMove}
            onMouseLeave={onPreviewMouseLeave}
            style={previewTiltStyle}
          >
            <div className="fb-mkt-preview-chrome"><span /><span /><span /></div>
            <div className="fb-mkt-preview-shell">
              <div className="fb-mkt-preview-sidebar">
                <div className="fb-mkt-preview-sidebar-logo"><LogoMark /><span>FINBRAIN OS</span></div>
                {HERO_NAV_GROUPS.map((group) => (
                  <div className="fb-mkt-preview-nav-group" key={group.label ?? "primary"}>
                    {group.label && <div className="fb-mkt-preview-nav-label">{group.label}</div>}
                    {group.items.map((item) => (
                      <button
                        key={item.key}
                        type="button"
                        className={"fb-mkt-preview-nav-item" + (activeScreen === item.key ? " is-active" : "")}
                        onClick={() => {
                          const idx = HERO_SCREENS.indexOf(item.key);
                          if (idx >= 0) selectScreen(idx);
                          else show("signup");
                        }}
                      >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{HERO_NAV_ICONS[item.key]}</svg>
                        {item.label}
                      </button>
                    ))}
                  </div>
                ))}
              </div>

              <div className="fb-mkt-preview-content" key={activeScreen}>
                {activeScreen === "customers" && (
                  <div className="fb-mkt-preview-pane">
                    <div className="fb-mkt-eyebrow is-plain" style={{ marginBottom: ".8rem" }}>Customers · ranked by attention</div>
                    <div className="fb-mkt-preview-log-row"><span>Meridian Corp · RM 18,400 overdue</span><span className="fb-mkt-pill is-urgent">Urgent</span></div>
                    <div className="fb-mkt-preview-log-row"><span>Grab Malaysia · RM 6,100 overdue</span><span className="fb-mkt-pill is-restricted">High</span></div>
                    <div className="fb-mkt-preview-log-row"><span>TechHub Solutions · on schedule</span><span className="fb-mkt-pill is-allowed">Healthy</span></div>
                  </div>
                )}
                {activeScreen === "agents" && (
                  <div className="fb-mkt-preview-pane">
                    <div className="fb-mkt-ask">
                      <div className="fb-mkt-eyebrow is-plain">Question asked</div>
                      <p>"{typed}{phase === "typing" && <span className="fb-mkt-caret" aria-hidden="true" />}"</p>
                    </div>
                    <div className={"fb-mkt-answer" + (phase !== "typing" ? " is-visible" : "")}>
                      {phase === "thinking" ? (
                        <div className="fb-mkt-thinking-row"><span className="fb-mkt-thinking-dots"><span /><span /><span /></span>Thinking…</div>
                      ) : phase === "answered" ? (
                        <>
                          <p>{demo.answer}<sup>1</sup></p>
                          <div className="fb-mkt-citation"><span>{demo.citation}</span><span className="fb-mkt-pill is-restricted">{demo.pill}</span></div>
                        </>
                      ) : null}
                    </div>
                  </div>
                )}
                {activeScreen === "finance" && (
                  <div className="fb-mkt-preview-pane">
                    <div className="fb-mkt-eyebrow is-plain" style={{ marginBottom: ".8rem" }}>Financial Intelligence</div>
                    <div className="fb-mkt-preview-kpis">
                      <div>
                        <span>Total revenue</span>
                        <strong>RM 1.84M</strong>
                        <em className="is-good">▲ 12.4%</em>
                      </div>
                      <div>
                        <span>Outstanding AR</span>
                        <strong>RM 94K</strong>
                        <em className="is-attn">⚠ 4.2%</em>
                      </div>
                    </div>
                    <svg className="fb-mkt-preview-chart" viewBox="0 0 320 90" role="img" aria-label="Revenue trending upward">
                      <polyline points="4,70 45,60 86,55 127,48 168,42 209,30 250,26 296,18" fill="none" stroke="var(--a-green)" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
                      <circle cx="296" cy="18" r="4" fill="var(--a-green)" />
                      <polyline points="4,82 45,80 86,78 127,76 168,74 209,72 250,68 296,60" fill="none" stroke="var(--a-orange)" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
                      <circle cx="296" cy="60" r="4" fill="var(--a-orange)" />
                    </svg>
                  </div>
                )}
                {activeScreen === "audit" && (
                  <div className="fb-mkt-preview-pane">
                    <div className="fb-mkt-eyebrow is-plain" style={{ marginBottom: ".8rem" }}>Audit &amp; Access</div>
                    <div className="fb-mkt-preview-chain-ok"><span className="fb-mkt-dot" />Valid hash chain · 128 entries</div>
                    <div className="fb-mkt-preview-log-row"><span>chloe@finbrain.my · Chat Query</span><span className="fb-mkt-pill is-allowed">Allowed</span></div>
                    <div className="fb-mkt-preview-log-row"><span>invoicing-agent · Agent Run</span><span className="fb-mkt-pill is-allowed">Allowed</span></div>
                    <div className="fb-mkt-preview-log-row"><span>guest-7f2a · Chat Query</span><span className="fb-mkt-pill is-restricted">Denied</span></div>
                  </div>
                )}
              </div>
            </div>
          </div>
          <div className="fb-mkt-float-badge"><span className="fb-mkt-dot" /> Chain verified · 0 gaps</div>
        </div>
      </section>

      <div ref={statsRef}>
        <div className="fb-mkt-stats">
          <AnimatedStat value="RM 1.84M" label="Revenue tracked on the live dashboard" active={statsIn} />
          <AnimatedStat value="128" label="Hash-chained audit entries, 0 gaps" active={statsIn} />
          <AnimatedStat value="~2 min" label="Average invoice review time" active={statsIn} />
          <AnimatedStat value="3 languages" label="English, Bahasa Malaysia & Chinese" active={statsIn} />
        </div>
        <p className="fb-mkt-fineprint">Figures from an example workspace, illustrative for this prototype — not live or measured usage.</p>
      </div>

      <Reveal className="fb-mkt-section fb-mkt-section-alt" id="landing-flow">
        <div className="fb-mkt-section-head">
          <div className="fb-mkt-eyebrow is-plain">How it fits in</div>
          <h2>Agents embedded where the work already happens</h2>
          <p>Let AI agents handle your team's repetitive finance and ops work.</p>
        </div>
        <div className="fb-mkt-flow-grid">
          <div className="fb-mkt-flow-card">
            <div className="fb-mkt-icon-badge is-blue"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M21 8V6a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h6" /><path d="M17 14v6M14 17h6" /></svg></div>
            <h3>Receipt / invoice in →</h3>
            <p>Agent watches your Telegram bot and inbox for receipts and invoices.</p>
            <div className="fb-mkt-flow-chain">
              <span>Telegram · Email</span><span>→</span><strong>FINBRAIN Agent</strong><span>→</span><span>MyInvois · Finance</span>
            </div>
            <div className="fb-mkt-flow-note">OCR-extracts fields, masks PII, maps to a MyInvois e-invoice.</div>
          </div>
          <div className="fb-mkt-flow-card">
            <div className="fb-mkt-icon-badge is-purple"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3a9 9 0 1 0 9 9" /><path d="M12 3v9l6 3" /></svg></div>
            <h3>Question in →</h3>
            <p>Ask from the Ask screen — or the Ask FinBrain panel available on every screen.</p>
            <div className="fb-mkt-flow-chain">
              <span>Ask FinBrain</span><span>→</span><strong>FINBRAIN Agent</strong><span>→</span><span>Cited answer</span>
            </div>
            <div className="fb-mkt-flow-note">Every answer cites its source and respects your role's access.</div>
          </div>
        </div>
      </Reveal>

      <Reveal className="fb-mkt-section" id="landing-agents">
        <div className="fb-mkt-section-head">
          <div className="fb-mkt-eyebrow is-plain">AI Agents</div>
          <h2>Handle the repetitive operational work your team shouldn't have to</h2>
          <p>Every agent runs inside the same permission and audit boundaries as your team.</p>
        </div>
        <div className="fb-mkt-agent-grid">
          {AGENTS.map((agent, i) => (
            <AgentCard key={agent.title} tone={agent.tone} title={agent.title} body={agent.body} icon={agent.icon} index={i} featured={i === 0} />
          ))}
        </div>
      </Reveal>

      <Reveal className="fb-mkt-section fb-mkt-proof-dark" id="landing-proof">
        <div className="fb-mkt-section-head">
          <div className="fb-mkt-eyebrow is-plain">Proof, not just promises</div>
          <h2>The same screens your team sees after signing in</h2>
          <p>Real screenshots of the running app — not marketing mockups. Company names shown are illustrative examples, not live customer data.</p>
        </div>
        <div className="fb-mkt-proof-grid">
          <div className="fb-mkt-proof-panel">
            <div className="fb-mkt-eyebrow is-plain" style={{ marginBottom: "1rem" }}>Briefing</div>
            <div className="fb-mkt-proof-shot-frame">
              <img src="/screenshots/briefing.png" alt="FinBrain Briefing screen listing customers ranked by attention score, most urgent first" loading="lazy" />
            </div>
            <button className="fb-mkt-btn is-outline" style={{ width: "100%", justifyContent: "center" }} type="button" onClick={() => show("signup")}>See your own briefing</button>
          </div>
          <div className="fb-mkt-proof-panel">
            <div className="fb-mkt-eyebrow is-plain" style={{ marginBottom: "1rem" }}>Customers</div>
            <div className="fb-mkt-proof-shot-frame">
              <img src="/screenshots/customers.png" alt="FinBrain Customers screen showing every customer ranked by attention score, outstanding and overdue amounts" loading="lazy" />
            </div>
            <button className="fb-mkt-btn is-outline" style={{ width: "100%", justifyContent: "center" }} type="button" onClick={() => show("signup")}>See the full customer list</button>
          </div>
        </div>
      </Reveal>

      <Reveal className="fb-mkt-section" id="landing-why">
        <div className="fb-mkt-section-head">
          <div className="fb-mkt-eyebrow is-plain">Why FinBrain</div>
          <h2>Why finance teams choose FINBRAIN over a general AI tool</h2>
          <p>A general assistant can answer a question. It can't natively file with LHDN, mask PDPA-covered data, or gate a table by role.</p>
        </div>
        <div className="fb-mkt-compare-wrap">
          <table className="fb-mkt-compare">
            <thead>
              <tr><th>Capability</th><th>General AI assistant<br />(ChatGPT, Copilot + manual setup)</th><th>Generic accounting software</th><th className="is-highlight">FINBRAIN OS</th></tr>
            </thead>
            <tbody>
              <tr><td>MyInvois / LHDN e-invoicing</td><td className="fb-mkt-no">Not built in</td><td className="fb-mkt-partial">Varies by vendor</td><td className="fb-mkt-yes is-highlight">Native</td></tr>
              <tr><td>PDPA-aligned data masking</td><td className="fb-mkt-no">You'd build this yourself</td><td className="fb-mkt-partial">Rarely AI-aware</td><td className="fb-mkt-yes is-highlight">Masked before storage</td></tr>
              <tr><td>Bahasa Malaysia &amp; Chinese</td><td className="fb-mkt-partial">General language, not finance-tuned</td><td className="fb-mkt-partial">Usually UI translation only</td><td className="fb-mkt-yes is-highlight">Native to the AI agent</td></tr>
              <tr><td>Permission-aware retrieval</td><td className="fb-mkt-no">Sees whatever you paste in</td><td className="fb-mkt-partial">Role-gated UI, not retrieval</td><td className="fb-mkt-yes is-highlight">Enforced on every query</td></tr>
              <tr><td>Tamper-evident audit trail</td><td className="fb-mkt-no">None</td><td className="fb-mkt-partial">Transaction logs, not hash-chained</td><td className="fb-mkt-yes is-highlight">Append-only, hash-chained</td></tr>
              <tr><td>Human sign-off on agent actions</td><td className="fb-mkt-no">No workflow at all</td><td className="fb-mkt-partial">Sometimes, for invoices only</td><td className="fb-mkt-yes is-highlight">Approvals queue for every agent action</td></tr>
            </tbody>
          </table>
        </div>

        <div className="fb-mkt-kpi-row">
          <div className="fb-mkt-kpi-tile">
            <div className="fb-mkt-kpi-label">Invoice review time</div>
            <div className="fb-mkt-kpi-value">~15 min → ~2 min</div>
            <div className="fb-mkt-delta is-good">Manual entry vs. reviewing an OCR'd draft</div>
          </div>
          <div className="fb-mkt-kpi-tile">
            <div className="fb-mkt-kpi-label">Approval cycle</div>
            <div className="fb-mkt-kpi-value">Days → Same day</div>
            <div className="fb-mkt-delta is-good">Email chains vs. one Approvals queue</div>
          </div>
          <div className="fb-mkt-kpi-tile">
            <div className="fb-mkt-kpi-label">Missing-TIN catch rate</div>
            <div className="fb-mkt-kpi-value">Before submission</div>
            <div className="fb-mkt-delta is-good">Flagged automatically, not after LHDN rejects it</div>
          </div>
        </div>
        <p className="fb-mkt-fineprint">Illustrative estimates based on the workflow design above, not measured customer results — this is a prototype, not a case study.</p>
      </Reveal>

      <Reveal className="fb-mkt-section fb-mkt-section-alt" id="landing-pricing">
        <div className="fb-mkt-section-head is-left">
          <div className="fb-mkt-eyebrow is-plain">Pricing</div>
          <h2>Simple pricing, built for finance teams</h2>
          <p>Every plan includes permission-aware retrieval, the tamper-evident audit trail, and PDPA-aligned e-invoicing.</p>
        </div>
        <div className="fb-mkt-pricing-grid">
          {PRICING.map((p, i) => (
            <PricingCard key={p.tier} {...p} index={i} onCta={() => show("signup")} />
          ))}
        </div>
        <p className="fb-mkt-fineprint">Prices shown in MYR — illustrative for this prototype, not a live billing system. <span tabIndex={0} role="button" onClick={() => goToSecurity("landing")}>Read about our security &amp; compliance approach →</span></p>
      </Reveal>

      <Reveal className="fb-mkt-section" id="landing-faq">
        <div className="fb-mkt-section-head">
          <div className="fb-mkt-eyebrow is-plain">FAQ</div>
          <h2>Questions finance teams actually ask</h2>
          <p>Straight answers, including where this prototype's limits are.</p>
        </div>
        <FaqAccordion />
      </Reveal>

      <Reveal className="fb-mkt-closing">
        <div className="fb-mkt-blob" style={{ width: 500, height: 500, top: -220, left: "50%", transform: "translateX(-50%)", background: "var(--a-accent)", opacity: 0.28 }} aria-hidden="true" />
        <h2>Ready to give your team answers it can prove?</h2>
        <div className="fb-mkt-hero-ctas">
          <button className="fb-mkt-btn is-solid is-lg" onClick={() => show("signup")}>Start your free trial</button>
          <button className="fb-mkt-btn is-outline is-lg" type="button" onClick={() => show("login")}>Log in</button>
        </div>
      </Reveal>

      <footer className="fb-mkt-footer">
        <div className="fb-mkt-footer-top">
          <div>
            <Wordmark />
            <p>Permission-aware AI for finance teams. This site is a prototype.</p>
          </div>
          <div className="fb-mkt-footer-links">
            <span tabIndex={0} role="button" onClick={() => goToSecurity("landing")}>Security</span>
            <span tabIndex={0} role="button" onClick={() => goToLegal("privacy", "landing")}>Privacy Policy</span>
            <span tabIndex={0} role="button" onClick={() => goToLegal("terms", "landing")}>Terms of Service</span>
            <a href="mailto:hello@finbrainos.example">Contact us</a>
          </div>
        </div>
        <div className="fb-mkt-footer-bottom">© 2026 FINBRAIN OS. Prototype for demonstration purposes — not a live product.</div>
      </footer>

      <CookieConsentBanner onReadMore={() => goToLegal("privacy", "landing")} />
      <SupportWidget topics={supportTopics} onEmail={() => { window.location.href = "mailto:hello@finbrainos.example"; }} />
    </div>
  );
}
