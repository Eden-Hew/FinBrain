import { useAppState } from "../lib/appState";
import { LandingNav } from "../components/Nav";
import { Wordmark } from "../components/Logo";

export default function Landing() {
  const { show, goToSecurity, goToLegal } = useAppState();

  return (
    <div className="fb-root">
      <LandingNav />

      <section className="fb-hero fb-reveal is-visible">
        <div className="fb-hero-copy">
          <div className="fb-eyebrow">Permission-Aware AI for Finance Teams</div>
          <h1>Ask your business.<br />Get answers you can prove.</h1>
          <p>One knowledge base, cited answers, and AI agents that handle the busywork — invoicing, spreadsheets, follow-ups — without touching data they shouldn't see.</p>
          <div className="fb-hero-ctas">
            <button className="fb-btn fb-btn-solid" onClick={() => show("signup")}>Start free trial</button>
            <button className="fb-btn fb-btn-outline" type="button" onClick={() => document.getElementById("landing-agents")?.scrollIntoView()}>See it in action</button>
          </div>
        </div>
        <div className="fb-hero-preview" aria-hidden="true">
          <div className="fb-ask-question"><div className="fb-eyebrow">Question asked</div><p>"Which accounts are overdue?"</p></div>
          <div className="fb-answer-card">
            <p className="fb-answer-text">Meridian Corp (RM 18,400) and 2 other accounts are 30+ days past due.<sup>1</sup> Draft a follow-up?</p>
            <div className="fb-citation-list">
              <div className="fb-citation-row"><span>Bank statement reconciliation</span><span>Restricted</span></div>
            </div>
          </div>
        </div>
      </section>

      <section className="fb-section fb-section-alt fb-reveal is-visible" id="landing-flow">
        <div className="fb-section-head">
          <h2>Agents embedded where the work already happens</h2>
          <p>Let AI agents handle your team's repetitive finance and ops work.</p>
        </div>
        <div className="fb-flow-row">
          <div className="fb-flow-card">
            <h3>Receipt / invoice in →</h3>
            <p>Agent watches inbox, Slack, and photo uploads for invoices.</p>
            <div className="fb-flow-chain">
              <span>Gmail · Slack</span><span>→</span><strong>FINBRAIN Agent</strong><span>→</span><span>MyInvois · Sheets</span>
            </div>
            <div className="fb-flow-note">OCR-extracts fields, maps to e-invoice, logs the row.</div>
          </div>
          <div className="fb-flow-card">
            <h3>Question in →</h3>
            <p>Agent answers from your knowledge base, permission-filtered.</p>
            <div className="fb-flow-chain">
              <span>Chat · Drive</span><span>→</span><strong>FINBRAIN Agent</strong><span>→</span><span>Cited answer</span>
            </div>
            <div className="fb-flow-note">Updates Drive folders and Sheets logs automatically.</div>
          </div>
        </div>
      </section>

      <section className="fb-section fb-reveal is-visible" id="landing-agents">
        <div className="fb-section-head">
          <h2>AI Agents</h2>
          <p>Handle the repetitive operational work your team shouldn't have to.</p>
        </div>
        <div className="fb-agent-grid">
          <div className="fb-agent-card">
            <svg className="fb-agent-icon" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M6 2h9l3 3v17H6z" /><path d="M9 8h6M9 12h6M9 16h4" /></svg>
            <h3>Invoicing Agent</h3><p>Snap a receipt → OCR → MyInvois-compliant e-invoice, submitted after approval.</p>
          </div>
          <div className="fb-agent-card">
            <svg className="fb-agent-icon" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 10h18M9 10v10" /></svg>
            <h3>Sheets Logger</h3><p>Every transaction, ticket, or approval logged into Google Sheets automatically.</p>
          </div>
          <div className="fb-agent-card">
            <svg className="fb-agent-icon" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></svg>
            <h3>Drive Organizer</h3><p>Keeps Drive folders current — files, renames, and archives without manual upkeep.</p>
          </div>
          <div className="fb-agent-card">
            <svg className="fb-agent-icon" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 4h13a3 3 0 0 1 3 3v7a3 3 0 0 1-3 3H9l-5 3v-3a3 3 0 0 1-3-3V7a3 3 0 0 1 3-3z" /></svg>
            <h3>Sales &amp; Finance Bot</h3><p>Answers pipeline and finance questions, drafts follow-ups and collections chases.</p>
          </div>
        </div>
      </section>

      <section className="fb-section fb-reveal is-visible" id="landing-proof">
        <div className="fb-section-head">
          <h2>Proof, not just promises</h2>
          <p>The same dashboard and audit trail your team sees after signing in — not marketing screenshots.</p>
        </div>
        <div className="fb-proof-grid">
          <div className="fb-proof-panel">
            <div className="fb-eyebrow" style={{ marginBottom: ".9rem" }}>Finance Dashboard</div>
            <div className="fb-proof-kpi-row">
              <div>
                <div className="fb-kpi-label">Total revenue</div>
                <div className="fb-kpi-value">RM 1.84M</div>
                <div className="fb-kpi-delta is-good">▲ 12.4% vs last quarter</div>
              </div>
              <div>
                <div className="fb-kpi-label">Outstanding AR</div>
                <div className="fb-kpi-value">RM 94K</div>
                <div className="fb-kpi-delta is-attn">⚠ 4.2% vs last quarter — review</div>
              </div>
            </div>
            <button className="fb-btn fb-btn-outline" style={{ width: "100%" }} type="button" onClick={() => show("signup")}>See the full dashboard</button>
          </div>
          <div className="fb-proof-panel">
            <div className="fb-eyebrow" style={{ marginBottom: ".9rem" }}>Audit Trail</div>
            <div className="fb-callout" style={{ margin: "0 0 1rem" }}>Chain verified — 128 entries, 0 gaps.</div>
            <div className="fb-proof-audit-rows">
              <div className="fb-log-row"><div className="fb-log-row-time">chloe@finbrain.my · Chat Query</div><div className="fb-log-row-text">Board Meeting — 14 Jul 2026 minutes <span className="fb-status-pill is-active" style={{ marginLeft: ".4rem" }}><span className="fb-status-dot"></span>Allowed</span></div></div>
              <div className="fb-log-row"><div className="fb-log-row-time">guest-7f2a · Chat Query</div><div className="fb-log-row-text">Board Meeting — 14 Jul 2026 minutes <span className="fb-status-pill is-review" style={{ marginLeft: ".4rem" }}><span className="fb-status-dot"></span>Denied</span></div></div>
              <div className="fb-log-row"><div className="fb-log-row-time">invoicing-agent · Agent Run</div><div className="fb-log-row-text">Receipt OCR — Grab Malaysia <span className="fb-status-pill is-active" style={{ marginLeft: ".4rem" }}><span className="fb-status-dot"></span>Allowed</span></div></div>
            </div>
            <button className="fb-btn fb-btn-outline" style={{ width: "100%" }} type="button" onClick={() => show("signup")}>See the full audit trail</button>
          </div>
        </div>
      </section>

      <section className="fb-section fb-reveal is-visible" id="landing-why">
        <div className="fb-section-head">
          <h2>Why finance teams choose FINBRAIN over a general AI tool</h2>
          <p>A general assistant can answer a question. It can't natively file with LHDN, mask PDPA-covered data, or gate a table by role.</p>
        </div>
        <div className="fb-table-wrap" style={{ maxWidth: "820px" }}>
          <table className="fb-table fb-compare-table">
            <thead>
              <tr><th>Capability</th><th>General AI assistant<br />(ChatGPT, Copilot + manual setup)</th><th>Generic accounting software</th><th>FINBRAIN OS</th></tr>
            </thead>
            <tbody>
              <tr><td>MyInvois / LHDN e-invoicing</td><td className="fb-compare-no">Not built in</td><td className="fb-compare-partial">Varies by vendor</td><td className="fb-compare-yes">Native</td></tr>
              <tr><td>PDPA-aligned data masking</td><td className="fb-compare-no">You'd build this yourself</td><td className="fb-compare-partial">Rarely AI-aware</td><td className="fb-compare-yes">Masked before storage</td></tr>
              <tr><td>Bahasa Malaysia &amp; Chinese</td><td className="fb-compare-partial">General language, not finance-tuned</td><td className="fb-compare-partial">Usually UI translation only</td><td className="fb-compare-yes">Native to the AI agent</td></tr>
              <tr><td>Permission-aware retrieval</td><td className="fb-compare-no">Sees whatever you paste in</td><td className="fb-compare-partial">Role-gated UI, not retrieval</td><td className="fb-compare-yes">Enforced on every query</td></tr>
              <tr><td>Tamper-evident audit trail</td><td className="fb-compare-no">None</td><td className="fb-compare-partial">Transaction logs, not hash-chained</td><td className="fb-compare-yes">Append-only, hash-chained</td></tr>
              <tr><td>Human sign-off on agent actions</td><td className="fb-compare-no">No workflow at all</td><td className="fb-compare-partial">Sometimes, for invoices only</td><td className="fb-compare-yes">Approvals queue for every agent action</td></tr>
            </tbody>
          </table>
        </div>

        <div className="fb-kpi-row" style={{ paddingTop: "2.2rem" }}>
          <div className="fb-kpi-tile">
            <div className="fb-kpi-label">Invoice review time</div>
            <div className="fb-kpi-value">~15 min → ~2 min</div>
            <div className="fb-kpi-delta is-good">Manual entry vs. reviewing an OCR'd draft</div>
          </div>
          <div className="fb-kpi-tile">
            <div className="fb-kpi-label">Approval cycle</div>
            <div className="fb-kpi-value">Days → Same day</div>
            <div className="fb-kpi-delta is-good">Email chains vs. one Approvals queue</div>
          </div>
          <div className="fb-kpi-tile">
            <div className="fb-kpi-label">Missing-TIN catch rate</div>
            <div className="fb-kpi-value">Before submission</div>
            <div className="fb-kpi-delta is-good">Flagged automatically, not after LHDN rejects it</div>
          </div>
        </div>
        <p className="fb-pricing-fineprint">Illustrative estimates based on the workflow design above, not measured customer results — this is a prototype, not a case study.</p>
      </section>

      <section className="fb-section fb-section-alt fb-reveal is-visible" id="landing-pricing">
        <div className="fb-section-head">
          <h2>Simple pricing, built for finance teams</h2>
          <p>Every plan includes permission-aware retrieval, the tamper-evident audit trail, and PDPA-aligned e-invoicing.</p>
        </div>
        <div className="fb-pricing-grid">
          <div className="fb-pricing-card">
            <div className="fb-eyebrow">Starter</div>
            <div className="fb-pricing-amount">RM 299<span>/month</span></div>
            <p className="fb-pricing-note">For a single finance lead getting started.</p>
            <ul className="fb-pricing-features">
              <li>1 seat</li>
              <li>100 AI queries / month</li>
              <li>Up to 50 e-invoices / month</li>
              <li>English only</li>
              <li>Email support</li>
            </ul>
            <button className="fb-btn fb-btn-outline" style={{ width: "100%" }} type="button" onClick={() => show("signup")}>Start free trial</button>
          </div>
          <div className="fb-pricing-card is-highlighted">
            <div className="fb-eyebrow">Team · Most popular</div>
            <div className="fb-pricing-amount">RM 899<span>/month</span></div>
            <p className="fb-pricing-note">For a finance team running invoicing, collections and reporting together.</p>
            <ul className="fb-pricing-features">
              <li>5 seats</li>
              <li>Unlimited AI queries</li>
              <li>Up to 500 e-invoices / month</li>
              <li>English, Malay &amp; Chinese</li>
              <li>Telegram receipt bot</li>
              <li>Priority support</li>
            </ul>
            <button className="fb-btn fb-btn-solid" style={{ width: "100%" }} type="button" onClick={() => show("signup")}>Start free trial</button>
          </div>
          <div className="fb-pricing-card">
            <div className="fb-eyebrow">Enterprise</div>
            <div className="fb-pricing-amount">Custom</div>
            <p className="fb-pricing-note">For multi-entity finance functions with compliance requirements.</p>
            <ul className="fb-pricing-features">
              <li>Unlimited seats</li>
              <li>SSO &amp; role-based provisioning</li>
              <li>Extended audit retention</li>
              <li>Custom integrations</li>
              <li>Dedicated success manager</li>
            </ul>
            <a className="fb-btn fb-btn-outline" style={{ width: "100%" }} href="mailto:hello@finbrainos.example">Contact us</a>
          </div>
        </div>
        <p className="fb-pricing-fineprint">Prices shown in MYR — illustrative for this prototype, not a live billing system. <span tabIndex={0} role="button" style={{ cursor: "pointer", textDecoration: "underline" }} onClick={() => goToSecurity("landing")}>Read about our security &amp; compliance approach →</span></p>
      </section>

      <section className="fb-closing fb-reveal is-visible">
        <h2>Ready to give your team answers it can prove?</h2>
        <div className="fb-hero-ctas" style={{ justifyContent: "center" }}>
          <button className="fb-btn fb-btn-solid" onClick={() => show("signup")}>Start your free trial</button>
          <button className="fb-btn fb-btn-outline" type="button" onClick={() => show("login")}>Log in</button>
        </div>
      </section>

      <footer className="fb-footer">
        <div className="fb-footer-top">
          <div>
            <Wordmark />
            <p>Permission-aware AI for finance teams. This site is a prototype.</p>
          </div>
          <div className="fb-footer-links">
            <span tabIndex={0} role="button" onClick={() => goToSecurity("landing")}>Security</span>
            <span tabIndex={0} role="button" onClick={() => goToLegal("privacy", "landing")}>Privacy Policy</span>
            <span tabIndex={0} role="button" onClick={() => goToLegal("terms", "landing")}>Terms of Service</span>
            <a href="mailto:hello@finbrainos.example">Contact us</a>
          </div>
        </div>
        <div className="fb-footer-bottom">© 2026 FINBRAIN OS. Prototype for demonstration purposes — not a live product.</div>
      </footer>
    </div>
  );
}
