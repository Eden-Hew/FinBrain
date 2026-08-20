import { useEffect, useMemo, useState } from "react";
import { useI18n } from "../lib/i18n";
import { useAppState } from "../lib/appState";
import { Sidebar, AppTopBar } from "../components/Nav";
import { EmptyState } from "../components/EmptyState";
import { PERSONAS } from "../lib/personas";
import { buildCustomers, formatRm } from "../lib/customerAggregation";
import {
  fetchAuditLog,
  fetchEinvoiceOutreachDrafts,
  fetchEinvoiceReadiness,
  fetchEinvoiceRecords,
  fetchEmailRecords,
  fetchEmailStatus,
  fetchFinanceSummary,
  fetchRecommendations,
  fetchTelegramRecords,
  fetchTelegramStatus,
  fetchWorkflowAudit,
  type EinvoiceReadinessResponse,
  type EInvoiceApiRecord,
  type FinanceSummaryResponse,
} from "../api/client";

type LoadState = "loading" | "loaded" | "error";

const TIER_LABEL: Record<string, string> = { urgent: "Urgent", high: "High", monitoring: "Monitoring", healthy: "Healthy" };

function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} hr ago`;
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

function isToday(iso: string): boolean {
  const d = new Date(iso);
  const now = new Date();
  return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate();
}

function RestrictedNote({ label }: { label: string }) {
  return (
    <span className="fb-disabled-hint">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="4" y="10" width="16" height="10" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></svg>
      {label}
    </span>
  );
}

function CardShell({
  tone, icon, label, onClick, children,
}: {
  tone: string;
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      className={"fb-home-card is-" + tone}
      type="button"
      onClick={onClick}
    >
      <div className="fb-home-card-top">
        <span className="fb-home-card-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{icon}</svg>
        </span>
        <span className="fb-home-card-arrow" aria-hidden="true">→</span>
      </div>
      <div className="fb-home-card-label">{label}</div>
      {children}
    </button>
  );
}

const RING_RADIUS = 25;
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;

function EinvoiceCard() {
  const { show } = useAppState();
  const [data, setData] = useState<EinvoiceReadinessResponse | null>(null);
  const [state, setState] = useState<LoadState>("loading");

  useEffect(() => {
    let active = true;
    fetchEinvoiceReadiness()
      .then((res) => { if (active) { setData(res); setState("loaded"); } })
      .catch(() => { if (active) setState("error"); });
    return () => { active = false; };
  }, []);

  const pct = data ? Math.round(data.score * 100) : 0;

  return (
    <CardShell
      tone="einvoice"
      label="e-Invoicing"
      onClick={() => show("einvoice")}
      icon={<path d="M6 2h9l3 3v17H6z M9 8h6M9 12h6M9 16h4" />}
    >
      {state === "loading" && <div className="fb-fine">Loading…</div>}
      {state === "error" && <div className="fb-fine">Couldn't load e-Invoicing data.</div>}
      {state === "loaded" && data && (
        <div className="fb-home-ring-row">
          <div className="fb-home-ring-wrap">
            <svg width="60" height="60" viewBox="0 0 60 60" aria-hidden="true">
              <circle cx="30" cy="30" r={RING_RADIUS} fill="none" stroke="var(--bg-alt)" strokeWidth="6" />
              <circle
                cx="30" cy="30" r={RING_RADIUS} fill="none" stroke="var(--accent)" strokeWidth="6" strokeLinecap="round"
                strokeDasharray={RING_CIRCUMFERENCE}
                strokeDashoffset={RING_CIRCUMFERENCE * (1 - pct / 100)}
                transform="rotate(-90 30 30)"
              />
            </svg>
            <span className="fb-home-ring-value">{pct}<small>%</small></span>
          </div>
          <div className="fb-home-ring-legend">
            <span style={{ color: "var(--chart-attn)" }}>{data.critical.count} critical</span>
            <span>{data.warning.count} warning</span>
            <span style={{ color: "var(--chart-good)" }}>{data.passing_count} passing</span>
          </div>
        </div>
      )}
    </CardShell>
  );
}

function AuditCard() {
  const { show, askRole } = useAppState();
  const canView = PERSONAS[askRole].capabilities.viewAudit;
  const [state, setState] = useState<LoadState>("loading");
  const [summary, setSummary] = useState<{ total: number; chainValid: boolean; latest: string | null } | null>(null);

  useEffect(() => {
    if (!canView) return;
    let active = true;
    const load = async () => {
      setState("loading");
      try {
        const [disclosures, workflow] = await Promise.all([fetchAuditLog(), fetchWorkflowAudit()]);
        if (!active) return;
        const times = [...disclosures.entries.map((e) => e.ts), ...workflow.entries.map((e) => e.created_at)].sort();
        setSummary({
          total: disclosures.entries.length + workflow.entries.length,
          chainValid: disclosures.chain_valid && workflow.chain_valid,
          latest: times.length ? times[times.length - 1] : null,
        });
        setState("loaded");
      } catch {
        if (active) setState("error");
      }
    };
    void load();
    return () => { active = false; };
  }, [canView]);

  return (
    <CardShell
      tone="audit"
      label="Audit"
      onClick={() => show("audit")}
      icon={<path d="M12 3 20 6.5v5.3c0 4.7-3.2 8.9-8 10.2-4.8-1.3-8-5.5-8-10.2V6.5z" />}
    >
      {!canView && <RestrictedNote label="Compliance role required" />}
      {canView && state === "loading" && <div className="fb-fine">Loading…</div>}
      {canView && state === "error" && <div className="fb-fine">Couldn't load audit data.</div>}
      {canView && state === "loaded" && summary && (
        <>
          <div className="fb-home-card-headline"><span className="num">{summary.total}</span><span className="unit">events logged</span></div>
          <div className="fb-home-card-foot">
            <span className={"fb-home-dot " + (summary.chainValid ? "good" : "attn")}></span>
            {summary.chainValid ? "Hash chain healthy" : "Chain verification issue"}
            {summary.latest && <> · {relativeTime(summary.latest)}</>}
          </div>
        </>
      )}
    </CardShell>
  );
}

function ApprovalsCard() {
  const { show, askRole } = useAppState();
  const capabilities = PERSONAS[askRole].capabilities;
  const [state, setState] = useState<LoadState>("loading");
  const [recCount, setRecCount] = useState<number | null>(null);
  const [outreachCount, setOutreachCount] = useState<number | null>(null);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setState("loading");
      try {
        if (capabilities.viewRecommendations) {
          const rows = await fetchRecommendations();
          if (active) setRecCount(rows.filter((r) => r.status === "proposed" || r.status === "approved").length);
        } else if (active) setRecCount(null);

        if (capabilities.manageEinvoiceReadiness) {
          const drafts = await fetchEinvoiceOutreachDrafts();
          if (active) setOutreachCount(drafts.length);
        } else if (active) setOutreachCount(null);

        if (active) setState("loaded");
      } catch {
        if (active) setState("error");
      }
    };
    void load();
    return () => { active = false; };
  }, [askRole, capabilities.viewRecommendations, capabilities.manageEinvoiceReadiness]);

  const visible = capabilities.viewRecommendations || capabilities.manageEinvoiceReadiness;
  const total = (recCount ?? 0) + (outreachCount ?? 0);
  const parts = [
    recCount !== null && recCount > 0 && `${recCount} AI recommendation${recCount === 1 ? "" : "s"}`,
    outreachCount !== null && outreachCount > 0 && `${outreachCount} outreach draft${outreachCount === 1 ? "" : "s"}`,
  ].filter(Boolean) as string[];

  return (
    <CardShell
      tone="approvals"
      label="Approvals"
      onClick={() => show("approvals")}
      icon={<path d="M9 12l2 2 4-4M12 3l8 4v5c0 4.5-3.2 8.5-8 10-4.8-1.5-8-5.5-8-10V7z" />}
    >
      {!visible && <RestrictedNote label="Owner / finance role required" />}
      {visible && state === "loading" && <div className="fb-fine">Loading…</div>}
      {visible && state === "error" && <div className="fb-fine">Couldn't load approvals data.</div>}
      {visible && state === "loaded" && (
        <>
          <div className="fb-home-card-headline"><span className="num">{total}</span><span className="unit">awaiting your review</span></div>
          <div className="fb-home-card-sub">{total === 0 ? "You're all caught up" : parts.join(" · ")}</div>
        </>
      )}
    </CardShell>
  );
}

function CaptureCard() {
  const { show } = useAppState();
  const [state, setState] = useState<LoadState>("loading");
  const [emailConfigured, setEmailConfigured] = useState(false);
  const [telegramConfigured, setTelegramConfigured] = useState(false);
  const [todayCount, setTodayCount] = useState(0);
  const [totalCount, setTotalCount] = useState(0);

  useEffect(() => {
    let active = true;
    Promise.all([fetchEmailStatus(), fetchEmailRecords(), fetchTelegramStatus(), fetchTelegramRecords()])
      .then(([emailStatus, emailRecords, telegramStatus, telegramRecords]) => {
        if (!active) return;
        setEmailConfigured(emailStatus.configured);
        setTelegramConfigured(telegramStatus.configured);
        const all = [...emailRecords, ...telegramRecords];
        setTotalCount(all.length);
        setTodayCount(all.filter((r) => isToday(r.created_at)).length);
        setState("loaded");
      })
      .catch(() => { if (active) setState("error"); });
    return () => { active = false; };
  }, []);

  const connected = [emailConfigured && "Email", telegramConfigured && "Telegram"].filter(Boolean) as string[];

  return (
    <CardShell
      tone="capture"
      label="Message Capture"
      onClick={() => show("ingestion")}
      icon={<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 9l5-5 5 5M12 4v13" />}
    >
      {state === "loading" && <div className="fb-fine">Loading…</div>}
      {state === "error" && <div className="fb-fine">Couldn't load capture status.</div>}
      {state === "loaded" && (
        <>
          <div className="fb-home-card-headline">
            <span className="num">{totalCount}</span>
            <span className="unit">protected record{totalCount === 1 ? "" : "s"}</span>
          </div>
          <div className="fb-home-card-foot">
            <span className={"fb-home-delta-badge" + (todayCount > 0 ? " is-active" : "")}>
              {todayCount > 0 ? `+${todayCount} today` : "No new captures today"}
            </span>
          </div>
          <div className="fb-home-card-sub">
            {connected.length ? connected.join(" + ") + " connected" : "Nothing connected yet"}
          </div>
        </>
      )}
    </CardShell>
  );
}

function FinanceCard() {
  const { show } = useAppState();
  const [data, setData] = useState<FinanceSummaryResponse | null>(null);
  const [state, setState] = useState<LoadState>("loading");

  useEffect(() => {
    let active = true;
    fetchFinanceSummary("month", 0)
      .then((res) => { if (active) { setData(res); setState("loaded"); } })
      .catch(() => { if (active) setState("error"); });
    return () => { active = false; };
  }, []);

  return (
    <CardShell
      tone="finance"
      label="Financial Intelligence"
      onClick={() => show("finance")}
      icon={<path d="M4 19V9M10 19V5M16 19v-7M22 19H2" />}
    >
      {state === "loading" && <div className="fb-fine">Loading…</div>}
      {state === "error" && <div className="fb-fine">Couldn't load financial data.</div>}
      {state === "loaded" && data && (
        <>
          <div className="fb-home-card-headline"><span className="num">{formatRm(Number(data.outstanding_ar) || 0)}</span></div>
          <div className="fb-home-card-sub">Outstanding receivables</div>
          <div className="fb-home-card-foot">
            {data.revenue_change_pct != null && (
              <span className={"fb-home-delta-badge" + (data.revenue_change_pct >= 0 ? " is-active" : "")}>
                {data.revenue_change_pct >= 0 ? "+" : ""}{data.revenue_change_pct.toFixed(1)}% revenue vs. last period
              </span>
            )}
          </div>
        </>
      )}
    </CardShell>
  );
}

function AttentionSection() {
  const { showCustomerDetail } = useAppState();
  const [records, setRecords] = useState<EInvoiceApiRecord[]>([]);
  const [state, setState] = useState<LoadState>("loading");

  useEffect(() => {
    let active = true;
    fetchEinvoiceRecords()
      .then((res) => { if (active) { setRecords(res); setState("loaded"); } })
      .catch(() => { if (active) setState("error"); });
    return () => { active = false; };
  }, []);

  const customers = useMemo(() => buildCustomers(records, new Set()), [records]);
  const needsAttention = customers.filter((c) => c.overdueTotal > 0).slice(0, 5);

  return (
    <section style={{ marginBottom: "1.6rem" }}>
      <div className="fb-eyebrow" style={{ marginBottom: ".6rem" }}>Attention — from invoicing data</div>
      {state === "loading" && <div className="fb-callout">Loading customer attention…</div>}
      {state === "error" && <div className="fb-callout" style={{ borderColor: "var(--chart-attn)", color: "var(--chart-attn)" }}>Couldn't load customer data.</div>}
      {state === "loaded" && needsAttention.length === 0 && (
        <EmptyState
          icon={<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5" /></svg>}
          title="No customers need attention right now"
          description="Nobody has an overdue invoice today."
        />
      )}
      {state === "loaded" && needsAttention.length > 0 && (
        <div className="fb-briefing-list">
          {needsAttention.map((c) => (
            <button key={c.key} className="fb-briefing-row" type="button" onClick={() => showCustomerDetail(c.key)}>
              <span className={"fb-briefing-tier is-" + c.tier}>{TIER_LABEL[c.tier]}</span>
              <span className="fb-briefing-name">{c.name}</span>
              <span className="fb-briefing-detail">{formatRm(c.overdueTotal)} overdue · {c.oldestOverdueDays} day{c.oldestOverdueDays === 1 ? "" : "s"}</span>
              <span className="fb-home-card-arrow" aria-hidden="true">→</span>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

export default function Home() {
  const { t } = useI18n();
  const { show } = useAppState();

  return (
    <div className="fb-root fb-shell">
      <Sidebar current="home" />
      <AppTopBar current="home" />

      <header className="fb-app-header">
        <h1>{t("home.title")}</h1>
        <p>{t("home.desc")}</p>
      </header>

      <div className="fb-page-body">
        <AttentionSection />

        <div className="fb-eyebrow" style={{ marginBottom: ".6rem" }}>Workspace signals</div>
        <div className="fb-home-grid">
          <EinvoiceCard />
          <AuditCard />
          <ApprovalsCard />
          <CaptureCard />
          <FinanceCard />
        </div>

        <div className="fb-home-ask-cta">
          <div className="fb-home-ask-cta-copy">
            <h2>Have a question about any of this?</h2>
            <p>Ask FinBrain in plain language — it cites every source and never shows a persona more than their role allows.</p>
          </div>
          <button className="fb-btn fb-btn-solid" type="button" onClick={() => show("agents")}>
            Start a conversation
          </button>
        </div>
      </div>
    </div>
  );
}
