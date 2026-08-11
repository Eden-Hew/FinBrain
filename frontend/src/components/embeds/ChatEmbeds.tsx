import { useState } from "react";
import { useAppState } from "../../lib/appState";
import {
  FB_AGENTS, FB_ASK_ROLES, FB_EINVOICE_STATUS_LABEL, FB_TG_SAMPLES,
  type AgentDef,
} from "../../data/sampleData";

export function EmbedRevenue() {
  const { askRole } = useAppState();
  const data = FB_ASK_ROLES[askRole];
  return (
    <div className="fb-answer-card is-financial">
      <div className="fb-financial-badge">Financial figure — confirm before filing</div>
      <div className="fb-answer-text" dangerouslySetInnerHTML={{ __html: data.answer }} />
      <div className="fb-citation-list">
        {data.citations.map((c, i) =>
          c.withheld ? (
            <div className="fb-citation-row is-withheld" key={i}><span>Withheld — {c.access} source</span><span>Not visible to your role</span></div>
          ) : (
            <div className="fb-citation-row" key={i}><span>{c.label}</span><span>{c.access}</span></div>
          ),
        )}
      </div>
      {data.note && <div className="fb-answer-note">{data.note}</div>}
    </div>
  );
}

export function EmbedRecommendations() {
  const { recommendations, draftSop, show } = useAppState();
  return (
    <div className="fb-card-list">
      {recommendations.map((rec) => {
        const impactLabel = rec.impact === 3 ? "High impact" : rec.impact === 2 ? "Medium impact" : "Low impact";
        return (
          <div className="fb-rec-card" key={rec.id}>
            <div className="fb-rec-card-top">
              <h3>{rec.title}</h3>
              <div className="fb-impact">
                {[1, 2, 3].map((n) => <span key={n} className={"fb-impact-dot" + (n <= rec.impact ? " is-filled" : "")} />)}
                <span className="fb-impact-label">{impactLabel}</span>
              </div>
            </div>
            <div className="fb-rec-evidence">{rec.evidence}</div>
            {rec.status === "sop_drafted" ? (
              <span className="fb-rec-status">SOP drafted — <span className="fb-chain-status"><span className="fb-link" onClick={() => show("agents")}>view in SOP Library →</span></span></span>
            ) : (
              <button className="fb-btn fb-btn-outline" type="button" onClick={() => draftSop(rec.id)}>Draft as SOP</button>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function EmbedSops() {
  const { sops, approveSop, rejectSop } = useAppState();
  return (
    <div className="fb-card-list">
      {sops.map((sop) => (
        <div className="fb-sop-card" key={sop.id}>
          <div className="fb-sop-card-top">
            <div><h3>{sop.title}</h3><div className="fb-sop-meta">v{sop.version} · Owner: {sop.owner}</div></div>
            <div style={{ display: "flex", alignItems: "center", gap: ".8rem" }}>
              <span className={"fb-status-pill" + (sop.status === "approved" ? " is-active" : "")}><span className="fb-status-dot" />{sop.status === "approved" ? "Approved" : "Draft"}</span>
              {sop.status === "draft" && (
                <div style={{ display: "flex", gap: ".4rem" }}>
                  <button className="fb-btn fb-btn-solid" type="button" onClick={() => approveSop(sop.id)}>Approve</button>
                  <button className="fb-btn fb-btn-outline" type="button" onClick={() => rejectSop(sop.id)}>Discard</button>
                </div>
              )}
            </div>
          </div>
          <div className="fb-sop-steps">
            {sop.steps.map((step) => (
              <div className="fb-log-row" key={step.n}><div className="fb-log-row-time">Step {step.n} · {step.t}</div><div className="fb-log-row-text">{step.d}</div></div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export function EmbedEinvoicePending() {
  const { einvoices, show } = useAppState();
  const ids = Object.keys(einvoices).filter((id) => einvoices[id].status === "pending" || einvoices[id].status === "review");
  if (ids.length === 0) {
    return <p className="fb-sans" style={{ color: "var(--ink-soft)", fontSize: ".8rem", margin: 0 }}>Nothing needs your approval right now — every e-invoice is either validated or submitted.</p>;
  }
  return (
    <div className="fb-log-list">
      {ids.map((id) => {
        const inv = einvoices[id];
        return (
          <div className="fb-log-row" key={id}>
            <div className="fb-log-row-time">{inv.supplier} · {inv.amount}</div>
            <div className="fb-log-row-text">{FB_EINVOICE_STATUS_LABEL[inv.status]} — <span className="fb-link" onClick={() => show("einvoice")}>review in e-Invoicing →</span></div>
          </div>
        );
      })}
    </div>
  );
}

export function EmbedAgentStatus({ agentKey }: { agentKey: AgentDef["key"] }) {
  const agent = FB_AGENTS[agentKey];
  return (
    <div className="fb-detail-body" style={{ padding: 0 }}>
      <div className="fb-detail-col">
        <h2>{agent.name} — Settings</h2>
        <div className="fb-settings-list">
          {agent.settings.map((row) => <div className="fb-settings-row" key={row[0]}><span>{row[0]}</span><span>{row[1]}</span></div>)}
        </div>
      </div>
      <div className="fb-detail-col">
        <h2>Activity log</h2>
        <div className="fb-log-list">
          {agent.log.map((row, i) => <div className="fb-log-row" key={i}><div className="fb-log-row-time">{row[0]}</div><div className="fb-log-row-text">{row[1]}</div></div>)}
        </div>
      </div>
    </div>
  );
}

export function EmbedTelegram() {
  const [messages, setMessages] = useState<typeof FB_TG_SAMPLES>([]);
  const [index, setIndex] = useState(0);

  const simulate = () => {
    setMessages((m) => [...m, FB_TG_SAMPLES[index % FB_TG_SAMPLES.length]]);
    setIndex((i) => i + 1);
  };

  return (
    <>
      <div className="fb-callout" style={{ margin: "0 0 1rem" }}>Auto-processed for known contacts on receipts under <strong>RM 1,000</strong> — anything larger, or from an unrecognized sender, routes to the e-Invoicing queue for human approval instead.</div>
      <div className="fb-tg-panel">
        <div className="fb-tg-header">
          <div className="fb-tg-avatar">SF</div>
          <div><div className="fb-tg-header-name">Segar Fresh Produce</div><div className="fb-tg-header-sub">Supplier · via Telegram</div></div>
        </div>
        <div className="fb-tg-thread">
          <div className="fb-tg-row in">
            <div className="fb-tg-bubble">
              <div className="fb-tg-receipt" aria-hidden="true" />
              Here's the receipt for today's delivery 🧾
            </div>
          </div>
          <div className="fb-tg-row in"><div className="fb-tg-processing">Reading receipt… extracting fields… mapping to MyInvois…</div></div>
          <div className="fb-tg-row out">
            <div className="fb-tg-bubble is-card">
              <div style={{ fontSize: ".68rem", fontWeight: 700, marginBottom: ".4rem" }}>✓ e-Invoice ready</div>
              <div className="fb-tg-ic-row"><span>Supplier</span><span>Segar Fresh Produce</span></div>
              <div className="fb-tg-ic-row"><span>Amount</span><span>RM 268.00</span></div>
              <div className="fb-tg-ic-row"><span>UIN</span><span>MY29A7T2LX</span></div>
              <div style={{ fontSize: ".66rem", color: "var(--ink-soft)", marginTop: ".5rem" }}>Submitted &amp; validated by LHDN. No approval needed — auto-processed under your Telegram intake threshold.</div>
            </div>
          </div>
          {messages.map((sample, i) => (
            <div key={i}>
              <div className="fb-tg-row in"><div className="fb-tg-bubble"><div className="fb-tg-receipt" aria-hidden="true" />{sample.note}</div></div>
              <div className="fb-tg-row in"><div className="fb-tg-processing">Reading receipt… extracting fields… mapping to MyInvois…</div></div>
              <div className="fb-tg-row out">
                <div className="fb-tg-bubble is-card">
                  <div style={{ fontSize: ".68rem", fontWeight: 700, marginBottom: ".4rem" }}>✓ e-Invoice ready</div>
                  <div className="fb-tg-ic-row"><span>{sample.kind}</span><span>{sample.name}</span></div>
                  <div className="fb-tg-ic-row"><span>Amount</span><span>{sample.amount}</span></div>
                  <div className="fb-tg-ic-row"><span>UIN</span><span>{sample.uin}</span></div>
                  <div style={{ fontSize: ".66rem", color: "var(--ink-soft)", marginTop: ".5rem" }}>Submitted &amp; validated by LHDN. No approval needed — auto-processed under your Telegram intake threshold.</div>
                </div>
              </div>
            </div>
          ))}
        </div>
        <div className="fb-tg-footer">
          <button className="fb-btn fb-btn-outline" type="button" onClick={simulate}>Simulate another receipt coming in</button>
        </div>
      </div>
    </>
  );
}

export function EmbedTin() {
  const [resolved, setResolved] = useState(false);
  return (
    <div className="fb-rec-card">
      <div className="fb-rec-card-top">
        <h3>Buyer TIN validation</h3>
        <span className={"fb-status-pill" + (resolved ? " is-active" : " is-review")}><span className="fb-status-dot" />{resolved ? "Requests sent" : "2 flagged"}</span>
      </div>
      <div className="fb-log-list" style={{ marginBottom: ".8rem" }}>
        <div className="fb-log-row"><div className="fb-log-row-time">Grab Malaysia</div><div className="fb-log-row-text">Using generic individual TIN (EI00000000010) — needs confirmation before submission.</div></div>
        <div className="fb-log-row"><div className="fb-log-row-time">Warung Kak Yah</div><div className="fb-log-row-text">No TIN on file — LHDN will reject this e-invoice as-is.</div></div>
      </div>
      <div className="fb-rec-evidence">{resolved ? "Reminder sent via Telegram and email to Grab Malaysia and Warung Kak Yah — awaiting their reply." : "Missing or malformed buyer TINs are the #1 cause of rejected e-invoices this month."}</div>
      <button className="fb-btn fb-btn-outline" type="button" disabled={resolved} onClick={() => setResolved(true)}>Send TIN request</button>
    </div>
  );
}

export function EmbedTax() {
  const [resolved, setResolved] = useState(false);
  return (
    <div className="fb-rec-card">
      <div className="fb-rec-card-top">
        <h3>Tax classification risk</h3>
        <span className={"fb-status-pill" + (resolved ? " is-active" : " is-review")}><span className="fb-status-dot" />{resolved ? "Resolved" : "1 flagged"}</span>
      </div>
      <div className="fb-rec-evidence">{resolved ? "Reclassified the Petronas Dagangan receipt (RM 320.00) to ST-05 — Sales Tax (Petroleum). Ready to resubmit." : "Petronas Dagangan fuel receipt (RM 320.00) is classified as SST 6% General — pattern suggests it should be ST-05 Sales Tax (Petroleum) instead. Wrong codes validate fine today and surface as audit findings later."}</div>
      {!resolved && <button className="fb-btn fb-btn-outline" type="button" onClick={() => setResolved(true)}>Apply suggested code (ST-05)</button>}
    </div>
  );
}

export function EmbedWindow() {
  const [resubmitted, setResubmitted] = useState(false);
  return (
    <div className="fb-rec-card">
      <div className="fb-rec-card-top">
        <h3>72-hour rejection window</h3>
        <span className="fb-status-pill is-review"><span className="fb-status-dot" />3 closing soon</span>
      </div>
      <div className="fb-log-list">
        <div className="fb-log-row"><div className="fb-log-row-time">TNB-2026-88213</div><div className="fb-log-row-text">9h 12m left to cancel or amend before it locks in.</div></div>
        <div className="fb-log-row"><div className="fb-log-row-time">GRB-4471209</div><div className="fb-log-row-text">34h left in the window.</div></div>
        <div className="fb-log-row"><div className="fb-log-row-time">AST-118820</div><div className="fb-log-row-text">61h left in the window.</div></div>
        <div className="fb-log-row">
          {resubmitted ? (
            <><div className="fb-log-row-time">OS-4471 · Office Supplies Sdn Bhd</div><div className="fb-log-row-text">Resubmitted with corrected TIN — pending LHDN validation.</div></>
          ) : (
            <><div className="fb-log-row-time">OS-4471 · Office Supplies Sdn Bhd</div><div className="fb-log-row-text">Rejected by LHDN (missing supplier TIN) — needs resubmission.</div></>
          )}
        </div>
      </div>
      {!resubmitted && <button className="fb-btn fb-btn-outline" type="button" style={{ marginTop: ".8rem" }} onClick={() => setResubmitted(true)}>Resubmit OS-4471</button>}
    </div>
  );
}

export function EmbedConsol() {
  const [previewOpen, setPreviewOpen] = useState(false);
  const [generated, setGenerated] = useState(false);
  return (
    <div className="fb-rec-card">
      <div className="fb-rec-card-top">
        <h3>Consolidated B2C e-invoices</h3>
        <span className={"fb-status-pill" + (generated ? " is-active" : "")}><span className="fb-status-dot" />{generated ? "Generated" : "18 pending"}</span>
      </div>
      <div className="fb-rec-evidence">18 individual B2C sales this month (RM 1,240.00 total) are eligible for the monthly consolidated e-invoice under the relaxation period. Next consolidation run: 31 Aug 2026, 11:59pm.</div>
      <div style={{ display: "flex", gap: ".6rem", flexWrap: "wrap" }}>
        <button className="fb-btn fb-btn-outline" type="button" onClick={() => setPreviewOpen((v) => !v)}>Preview consolidated invoice</button>
        {!generated && <button className="fb-btn fb-btn-solid" type="button" onClick={() => setGenerated(true)}>Generate &amp; submit now</button>}
      </div>
      {previewOpen && (
        <div className="fb-settings-list" style={{ marginTop: "1rem" }}>
          <div className="fb-settings-row"><span>Period</span><span>1–31 Aug 2026</span></div>
          <div className="fb-settings-row"><span>Transactions</span><span>18</span></div>
          <div className="fb-settings-row"><span>Total amount</span><span>RM 1,240.00</span></div>
          <div className="fb-settings-row"><span>Buyer</span><span>General Public (Consolidated)</span></div>
          <div className="fb-settings-row"><span>Classification</span><span>Retail — Consolidated B2C</span></div>
        </div>
      )}
      {generated && <div className="fb-rec-evidence" style={{ marginTop: ".9rem" }}>Consolidated e-invoice generated — UIN MY29E4K7BQXR, submitted to MyInvois sandbox.</div>}
    </div>
  );
}

export function EmbedGl() {
  const [open, setOpen] = useState(false);
  return (
    <div className="fb-rec-card">
      <div className="fb-rec-card-top">
        <h3>GL reconciliation</h3>
        <span className="fb-status-pill is-active"><span className="fb-status-dot" />96% matched</span>
      </div>
      <div className="fb-rec-evidence">142 of 148 general ledger revenue lines this month are matched to a validated e-invoice. 6 unmatched lines (RM 8,420.00 total) need review before close.</div>
      <button className="fb-btn fb-btn-outline" type="button" onClick={() => setOpen((v) => !v)}>View unmatched lines</button>
      {open && (
        <div style={{ marginTop: "1rem", overflowX: "auto" }}>
          <table className="fb-table">
            <thead><tr><th>GL Ref</th><th style={{ textAlign: "right" }}>Amount</th><th>Issue</th></tr></thead>
            <tbody>
              <tr><td>GL-4471</td><td className="fb-num">RM 1,850.00</td><td>Consulting revenue, no e-invoice found</td></tr>
              <tr><td>GL-4482</td><td className="fb-num">RM 2,120.00</td><td>Deposit received, awaiting invoice generation</td></tr>
              <tr><td>GL-4499</td><td className="fb-num">RM 940.00</td><td>Refund reversal, e-invoice cancelled but GL not adjusted</td></tr>
              <tr><td>GL-4503</td><td className="fb-num">RM 1,600.00</td><td>Duplicate entry suspected</td></tr>
              <tr><td>GL-4511</td><td className="fb-num">RM 1,210.00</td><td>Manual journal entry, no source invoice</td></tr>
              <tr><td>GL-4520</td><td className="fb-num">RM 700.00</td><td>e-Invoice pending approval (Petronas Dagangan)</td></tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function EmbedCash() {
  const [note, setNote] = useState("Pulled live from bank feeds, AP due dates, and AR due dates — no manual reconciliation.");
  return (
    <div className="fb-rec-card is-financial">
      <div className="fb-rec-card-top">
        <h3>Cash flow visibility</h3>
        <span className="fb-status-pill is-active"><span className="fb-status-dot" />On track</span>
      </div>
      <div className="fb-financial-badge">Financial figure — confirm before filing</div>
      <div className="fb-settings-list" style={{ marginBottom: ".8rem" }}>
        <div className="fb-settings-row"><span>Cash on hand (3 accounts)</span><span>RM 284,600</span></div>
        <div className="fb-settings-row"><span>Committed outflows (7 days)</span><span>RM 96,200</span></div>
        <div className="fb-settings-row"><span>Expected inflows (7 days)</span><span>RM 142,000</span></div>
        <div className="fb-settings-row"><span>Net projected position</span><span>RM 330,400</span></div>
      </div>
      <div className="fb-rec-evidence">{note}</div>
      <button className="fb-btn fb-btn-outline" type="button" onClick={() => setNote("Refreshed just now — pulled live from bank feeds, AP due dates, and AR due dates.")}>Refresh forecast</button>
    </div>
  );
}

export function EmbedAr() {
  const [rows, setRows] = useState([
    { name: "Bina Jaya Hardware · RM 4,200 · 65 days overdue", text: "Stage: Reminder sent (2×). Next: Firm notice.", escalated: false, nextText: "Firm notice sent. Next: Hand to collections.", nextName: "Bina Jaya Hardware" },
    { name: "Timur Logistics · RM 2,850 · 78 days overdue", text: "Stage: Firm notice sent. Next: Hand to collections.", escalated: false, nextText: "Escalated to collections.", nextName: "Timur Logistics" },
    { name: "Warung Kak Yah · RM 610 · 92 days overdue", text: "Stage: Escalated to collections.", escalated: true, nextText: "", nextName: "" },
  ]);
  const escalate = (i: number) => {
    setRows((r) => r.map((row, idx) => (idx === i ? { ...row, name: row.nextName, text: row.nextText, escalated: true } : row)));
  };
  return (
    <div className="fb-rec-card is-financial">
      <div className="fb-rec-card-top">
        <h3>AR aging &amp; escalation</h3>
        <span className="fb-status-pill is-review"><span className="fb-status-dot" />3 accounts overdue</span>
      </div>
      <div className="fb-financial-badge">Financial figure — confirm before filing</div>
      <div className="fb-settings-list" style={{ marginBottom: ".8rem" }}>
        <div className="fb-settings-row"><span>Current</span><span>RM 118,400</span></div>
        <div className="fb-settings-row"><span>1–30 days overdue</span><span>RM 22,600</span></div>
        <div className="fb-settings-row"><span>31–60 days overdue</span><span>RM 4,200</span></div>
        <div className="fb-settings-row"><span>61–90+ days overdue</span><span>RM 3,460</span></div>
      </div>
      <div className="fb-log-list">
        {rows.map((row, i) => (
          <div className="fb-log-row" key={i}><div className="fb-log-row-time">{row.name}</div><div className="fb-log-row-text">{row.text}</div></div>
        ))}
      </div>
      <div style={{ display: "flex", gap: ".6rem", flexWrap: "wrap", marginTop: ".8rem" }}>
        {!rows[0].escalated && <button className="fb-btn fb-btn-outline" type="button" onClick={() => escalate(0)}>Escalate Bina Jaya Hardware</button>}
        {!rows[1].escalated && <button className="fb-btn fb-btn-outline" type="button" onClick={() => escalate(1)}>Escalate Timur Logistics</button>}
      </div>
    </div>
  );
}

export function EmbedLead() {
  const [drafted, setDrafted] = useState(false);
  return (
    <div className="fb-rec-card">
      <div className="fb-rec-card-top">
        <h3>Lead response watch</h3>
        <span className={"fb-status-pill" + (drafted ? " is-active" : " is-review")}><span className="fb-status-dot" />{drafted ? "Reply drafted" : "1 lead waiting"}</span>
      </div>
      <div className="fb-log-list" style={{ marginBottom: ".8rem" }}>
        <div className="fb-log-row">
          {drafted ? (
            <><div className="fb-log-row-time">Instagram DM · Amirah K.</div><div className="fb-log-row-text">Reply drafted: "Hi Amirah, thanks for asking! Business tier is RM320/seat/month and includes all 5 connectors plus the Process Optimization Engine — happy to set up a quick call." Queued for approval.</div></>
          ) : (
            <><div className="fb-log-row-time">Instagram DM · Amirah K.</div><div className="fb-log-row-text">Asking about Business tier pricing — waiting 47 min.</div></>
          )}
        </div>
        <div className="fb-log-row"><div className="fb-log-row-time">WhatsApp · Zulkifli Trading</div><div className="fb-log-row-text">Asked about a demo — responded in 8 min.</div></div>
        <div className="fb-log-row"><div className="fb-log-row-time">Website form · Nadia binti Rahman</div><div className="fb-log-row-text">Asking about MyInvois integration — waiting 12 min.</div></div>
      </div>
      {!drafted && <button className="fb-btn fb-btn-outline" type="button" onClick={() => setDrafted(true)}>Draft reply to Amirah K.</button>}
    </div>
  );
}

export function EmbedCrm() {
  return (
    <div className="fb-rec-card">
      <div className="fb-rec-card-top">
        <h3>CRM auto-logging</h3>
        <span className="fb-status-pill is-active"><span className="fb-status-dot" />12 logged today</span>
      </div>
      <div className="fb-rec-evidence">Every call, WhatsApp thread, and meeting note is transcribed and logged to the CRM automatically — no end-of-day data entry.</div>
      <div className="fb-log-list">
        <div className="fb-log-row"><div className="fb-log-row-time">10:42 · Call — Bina Jaya Hardware</div><div className="fb-log-row-text">Logged. Deal stage updated to Negotiation.</div></div>
        <div className="fb-log-row"><div className="fb-log-row-time">09:15 · WhatsApp — Zulkifli Trading</div><div className="fb-log-row-text">Logged. Deal stage updated to Demo Scheduled.</div></div>
        <div className="fb-log-row"><div className="fb-log-row-time">Yesterday · Meeting notes — Segar Fresh Produce</div><div className="fb-log-row-text">Logged. Deal stage updated to Closed Won.</div></div>
      </div>
    </div>
  );
}

export function EmbedRenewal() {
  const [sent, setSent] = useState(false);
  return (
    <div className="fb-rec-card">
      <div className="fb-rec-card-top">
        <h3>Renewal tracking</h3>
        <span className="fb-status-pill is-review"><span className="fb-status-dot" />2 due within 14 days</span>
      </div>
      <div className="fb-log-list">
        <div className="fb-log-row">
          {sent ? (
            <><div className="fb-log-row-time">Warung Kak Yah · Team plan, 20 seats</div><div className="fb-log-row-text">Renews in 6 days — reminder sent just now via email and WhatsApp.</div></>
          ) : (
            <><div className="fb-log-row-time">Warung Kak Yah · Team plan, 20 seats</div><div className="fb-log-row-text">Renews in 6 days — no response to renewal notice yet.</div></>
          )}
        </div>
        <div className="fb-log-row"><div className="fb-log-row-time">Bina Jaya Hardware · Business plan, 45 seats</div><div className="fb-log-row-text">Renews in 13 days — renewal confirmed.</div></div>
      </div>
      {!sent && <button className="fb-btn fb-btn-outline" type="button" style={{ marginTop: ".8rem" }} onClick={() => setSent(true)}>Send renewal reminder</button>}
    </div>
  );
}

const AGENT_ORDER: AgentDef["key"][] = ["invoicing", "sheets", "drive", "sales"];

function pickAgentReply(agentKey: AgentDef["key"], lang: "en" | "ms" | "zh", lower: string, raw: string): string | null {
  const data = FB_AGENTS[agentKey].i18n[lang];
  for (const rule of data.replies) {
    for (const kw of rule.keywords) {
      if (lower.indexOf(kw.toLowerCase()) !== -1 || raw.indexOf(kw) !== -1) return rule.reply;
    }
  }
  return null;
}

export interface ChatReply {
  text: string;
  embed?: React.ReactNode;
}

const RULES: { test: string[]; text: string; embed: () => React.ReactNode }[] = [
  { test: ["telegram", "receipt bot", "receipt queue"], text: "Here's today's Telegram receipt activity:", embed: () => <EmbedTelegram /> },
  { test: ["sop", "procedure", "standard operating"], text: "Here's the current SOP library:", embed: () => <EmbedSops /> },
  { test: ["recommendation", "optimi", "pattern", "process improvement"], text: "Here's what the Process Optimization Engine has flagged:", embed: () => <EmbedRecommendations /> },
  { test: ["cash flow", "cash position", "runway", "cash on hand"], text: "Here's the current cash position:", embed: () => <EmbedCash /> },
  { test: ["tax class", "classification", "sst", "tax code", "tax risk"], text: "Here's the tax classification I'd flag for review:", embed: () => <EmbedTax /> },
  { test: ["buyer tin", "tin request", "tin validation"], text: "Here's where buyer TIN validation stands:", embed: () => <EmbedTin /> },
  { test: ["72-hour", "72 hour", "rejection window", "expiring invoice"], text: "Here's what's inside the 72-hour rejection window:", embed: () => <EmbedWindow /> },
  { test: ["consolidat", "b2c"], text: "Here's the consolidated B2C e-invoice status:", embed: () => <EmbedConsol /> },
  { test: ["general ledger", "gl reconcil", "reconcile the ledger"], text: "Here's the GL reconciliation status:", embed: () => <EmbedGl /> },
  { test: ["e-invoice", "einvoice", "need my approval", "pending invoice", "invoice review"], text: "Here's what needs your approval or review:", embed: () => <EmbedEinvoicePending /> },
  { test: ["overdue", "aging", "ar aging", "escalat", "collections"], text: "Here's AR aging, and where each overdue account stands:", embed: () => <EmbedAr /> },
  { test: ["lead", "instagram", "inquiry"], text: "Here's lead response status:", embed: () => <EmbedLead /> },
  { test: ["crm", "call log", "logged today"], text: "Here's what got auto-logged to the CRM:", embed: () => <EmbedCrm /> },
  { test: ["renewal", "renew"], text: "Here's renewal tracking:", embed: () => <EmbedRenewal /> },
  { test: ["revenue", "q3", "earnings", "profit", "acme"], text: "Here's what I can tell you, filtered to your current role:", embed: () => <EmbedRevenue /> },
];

export function resolveChatReply(rawMessage: string, lang: "en" | "ms" | "zh", fallback: string): ChatReply {
  const lower = rawMessage.toLowerCase();
  const has = (list: string[]) => list.some((kw) => lower.indexOf(kw) !== -1 || rawMessage.indexOf(kw) !== -1);

  for (const rule of RULES) {
    if (has(rule.test)) return { text: rule.text, embed: rule.embed() };
  }

  for (const key of AGENT_ORDER) {
    const reply = pickAgentReply(key, lang, lower, rawMessage);
    if (reply) return { text: reply, embed: <EmbedAgentStatus agentKey={key} /> };
  }

  return { text: fallback };
}
