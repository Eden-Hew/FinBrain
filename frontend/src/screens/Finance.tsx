import { useEffect, useState, type MouseEvent } from "react";
import { useI18n } from "../lib/i18n";
import { useAppState } from "../lib/appState";
import { Sidebar, AppTopBar } from "../components/Nav";
import {
  fetchFinanceSummary,
  type ARAgingBucket,
  type FinancePeriod,
  type FinanceSummaryResponse,
  type TopCustomer,
} from "../api/client";

function downloadCsv(filename: string, rows: (string | number)[][]) {
  const csv = rows
    .map((row) => row.map((cell) => {
      const s = String(cell ?? "");
      return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
    }).join(","))
    .join("\r\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function formatCurrency(value: string | number): string {
  const num = typeof value === "number" ? value : parseFloat(value);
  if (Number.isNaN(num)) return "RM 0";
  const sign = num < 0 ? "-" : "";
  const abs = Math.abs(num);
  if (abs >= 1_000_000) return `${sign}RM ${(abs / 1_000_000).toFixed(2)}M`;
  if (abs >= 1_000) return `${sign}RM ${(abs / 1_000).toFixed(1)}K`;
  return `${sign}RM ${abs.toFixed(2)}`;
}

function periodLabel(data: FinanceSummaryResponse): string {
  const start = new Date(`${data.period_start}T00:00:00`);
  if (data.period === "month") {
    return start.toLocaleDateString("en-US", { month: "long", year: "numeric" });
  }
  if (data.period === "quarter") {
    return `Q${Math.floor(start.getMonth() / 3) + 1} ${start.getFullYear()}`;
  }
  return String(start.getFullYear());
}

const CHART_W = 640;
const CHART_H = 250;
const PAD_LEFT = 56;
const PAD_RIGHT = 20;
const PAD_TOP = 20;
const PAD_BOTTOM = 24;

function RevenueTrendChart({ data }: { data: FinanceSummaryResponse }) {
  const [hover, setHover] = useState<number | null>(null);
  const points = data.revenue_trend;
  const values = points.map((p) => parseFloat(p.total_amount));
  const maxValue = Math.max(1, ...values);

  const xPos = (i: number) =>
    PAD_LEFT + (points.length <= 1 ? 0 : (i / (points.length - 1)) * (CHART_W - PAD_LEFT - PAD_RIGHT));
  const yPos = (v: number) => PAD_TOP + (CHART_H - PAD_TOP - PAD_BOTTOM) * (1 - v / maxValue);

  const handleMove = (event: MouseEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const relX = ((event.clientX - rect.left) / rect.width) * CHART_W;
    let closest = 0;
    let closestDist = Infinity;
    points.forEach((_, i) => {
      const dist = Math.abs(xPos(i) - relX);
      if (dist < closestDist) { closestDist = dist; closest = i; }
    });
    setHover(closest);
  };

  if (points.length === 0) {
    return <div className="fb-callout">No validated revenue yet in this window.</div>;
  }

  const gridValues = [0, 0.25, 0.5, 0.75, 1].map((f) => maxValue * f);
  const labelStep = Math.max(1, Math.ceil(points.length / 12));

  return (
    <div className="fb-chart-hover-wrap">
      <svg
        viewBox={`0 0 ${CHART_W} ${CHART_H}`}
        role="img"
        aria-label={`Line chart of monthly validated revenue, ${points.length} months`}
        onMouseMove={handleMove}
        onMouseLeave={() => setHover(null)}
      >
        <line x1={PAD_LEFT} y1={PAD_TOP} x2={PAD_LEFT} y2={CHART_H - PAD_BOTTOM} stroke="var(--line)" strokeWidth="1" />
        <line x1={PAD_LEFT} y1={CHART_H - PAD_BOTTOM} x2={CHART_W - PAD_RIGHT} y2={CHART_H - PAD_BOTTOM} stroke="var(--line)" strokeWidth="1" />
        {gridValues.map((v) => (
          <g key={v}>
            <line x1={PAD_LEFT} y1={yPos(v)} x2={CHART_W - PAD_RIGHT} y2={yPos(v)} stroke="var(--line)" strokeWidth="1" />
            <text x={PAD_LEFT - 6} y={yPos(v) + 3} textAnchor="end" fontSize="9" fill="var(--ink-soft)">{formatCurrency(v)}</text>
          </g>
        ))}
        {points.map((p, i) => (
          i % labelStep === 0 ? (
            <text key={p.period_label} x={xPos(i)} y={CHART_H - 6} textAnchor="middle" fontSize="9" fill="var(--ink-soft)">{p.period_label}</text>
          ) : null
        ))}
        <polyline
          points={values.map((v, i) => `${xPos(i)},${yPos(v)}`).join(" ")}
          fill="none"
          stroke="var(--viz-1)"
          strokeWidth="2"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        {hover !== null && (
          <>
            <line x1={xPos(hover)} y1={PAD_TOP} x2={xPos(hover)} y2={CHART_H - PAD_BOTTOM} stroke="var(--ink-soft)" strokeWidth="1" strokeDasharray="3 3" />
            <circle cx={xPos(hover)} cy={yPos(values[hover])} r="5" fill="var(--viz-1)" stroke="var(--card)" strokeWidth="2" />
          </>
        )}
      </svg>
      {hover !== null && (
        <div className="fb-chart-tooltip" style={{ left: `${(xPos(hover) / CHART_W) * 100}%` }}>
          <strong>{points[hover].period_label}</strong>
          <div><span className="fb-legend-dot" style={{ background: "var(--viz-1)" }} />{formatCurrency(points[hover].total_amount)}</div>
        </div>
      )}
    </div>
  );
}

function TopCustomersChart({ customers }: { customers: TopCustomer[] }) {
  const [hover, setHover] = useState<number | null>(null);
  if (customers.length === 0) {
    return <div className="fb-callout">No validated invoices linked to a customer yet.</div>;
  }
  const values = customers.map((c) => parseFloat(c.total_amount));
  const maxValue = Math.max(1, ...values);
  const barW = 640;
  const barLeft = 160;
  const barRight = 526;
  const rowHeight = 40;
  const height = 10 + customers.length * rowHeight;
  const scale = (v: number) => barLeft + (v / maxValue) * (barRight - barLeft);

  return (
    <svg
      width="100%"
      viewBox={`0 0 ${barW} ${height}`}
      role="img"
      aria-label={`Horizontal bar chart of top ${customers.length} customers by revenue`}
    >
      {customers.map((customer, i) => {
        const top = 10 + i * rowHeight;
        const right = scale(values[i]);
        return (
          <g
            key={customer.customer_id}
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(null)}
            style={{ cursor: "default" }}
          >
            <text x={barLeft - 8} y={top + 14} textAnchor="end" fontSize="10.5" fill="var(--ink)">{customer.name}</text>
            <path
              d={`M${barLeft},${top} L${right - 4},${top} Q${right},${top} ${right},${top + 4} L${right},${top + 16} Q${right},${top + 20} ${right - 4},${top + 20} L${barLeft},${top + 20} Z`}
              fill="var(--viz-1)"
              opacity={hover === null || hover === i ? 1 : 0.45}
              style={{ transition: "opacity .15s ease" }}
            />
            <text x={right + 10} y={top + 14} fontSize="10" fontWeight="700" fill="var(--ink)" style={{ fontVariantNumeric: "tabular-nums" }}>{formatCurrency(customer.total_amount)}</text>
          </g>
        );
      })}
    </svg>
  );
}

const AGING_LABELS: Record<ARAgingBucket["label"], string> = {
  current: "Current",
  "1-30": "1–30 days overdue",
  "31-60": "31–60 days overdue",
  "61-90": "61–90 days overdue",
  "90+": "90+ days overdue",
};

// Illustrative fallback only -- shown with a visible "Demo data" banner whenever the
// real /finance/summary call fails (e.g. the backend serving this deployment hasn't
// picked up the endpoint yet), never silently presented as real. This is the opposite
// of how this screen used to work: every number here used to be a hardcoded literal
// with no indication it wasn't real. That was the whole problem; this fallback exists
// so demos don't dead-end on a bare error screen, not so numbers can be faked again.
// 24 months so "previous year" (and several "previous quarter" clicks) still land on
// a real computed figure instead of clamping to a single stray data point.
const MOCK_MONTHLY_REVENUE = [
  98000, 102500, 108900, 105200, 112800, 118500, 115200, 121900, 126400, 119800, 124600, 130200,
  128000, 134500, 141200, 139800, 152300, 158900, 149500, 163200, 171800, 168400, 176900, 184300,
];

// How far back the demo dataset stays coherent for each period granularity --
// beyond this, prior-period math clamps to a single stray month and produces
// nonsensical comparisons. Real backend data has no such limit.
const MOCK_MIN_OFFSET: Record<FinancePeriod, number> = { month: -11, quarter: -3, year: -1 };

const MOCK_TOP_CUSTOMERS: TopCustomer[] = [
  { customer_id: 1, name: "Tenaga Nasional Berhad", total_amount: "246000.00", invoice_count: 9 },
  { customer_id: 2, name: "Grab Malaysia Sdn Bhd", total_amount: "182400.00", invoice_count: 14 },
  { customer_id: 3, name: "AirAsia Group Berhad", total_amount: "156800.00", invoice_count: 6 },
  { customer_id: 4, name: "Petronas Dagangan Berhad", total_amount: "119500.00", invoice_count: 5 },
  { customer_id: 5, name: "Maybank Islamic Berhad", total_amount: "94200.00", invoice_count: 8 },
];

function mockMonthLabels(): string[] {
  const now = new Date();
  return Array.from({ length: 12 }, (_, i) => {
    const d = new Date(now.getFullYear(), now.getMonth() - (11 - i), 1);
    return d.toLocaleDateString("en-US", { month: "short", year: "numeric" });
  });
}

function buildMockFinanceSummary(period: FinancePeriod, offset: number): FinanceSummaryResponse {
  const monthsInPeriod = period === "month" ? 1 : period === "quarter" ? 3 : 12;
  const lastIndex = MOCK_MONTHLY_REVENUE.length - 1;
  const clamp = (i: number) => Math.max(0, Math.min(lastIndex, i));
  const sum = (from: number, to: number) =>
    MOCK_MONTHLY_REVENUE.slice(clamp(from), clamp(to) + 1).reduce((a, b) => a + b, 0);

  const endIndex = lastIndex + offset * monthsInPeriod;
  const startIndex = endIndex - monthsInPeriod + 1;
  const totalRevenue = sum(startIndex, endIndex);
  const priorRevenue = sum(startIndex - monthsInPeriod, endIndex - monthsInPeriod);

  const now = new Date();
  const periodStart = new Date(now.getFullYear(), now.getMonth() + offset * monthsInPeriod - (monthsInPeriod - 1), 1);
  const periodEnd = new Date(periodStart.getFullYear(), periodStart.getMonth() + monthsInPeriod, 1);
  const toIso = (d: Date) => d.toISOString().slice(0, 10);

  return {
    period,
    period_start: toIso(periodStart),
    period_end: toIso(periodEnd),
    total_revenue: totalRevenue.toFixed(2),
    prior_period_revenue: priorRevenue.toFixed(2),
    revenue_change_pct: priorRevenue > 0 ? ((totalRevenue - priorRevenue) / priorRevenue) * 100 : null,
    outstanding_ar: "94320.00",
    ar_aging: [
      { label: "current", count: 14, total_amount: "45200.00" },
      { label: "1-30", count: 8, total_amount: "28100.00" },
      { label: "31-60", count: 3, total_amount: "12400.00" },
      { label: "61-90", count: 2, total_amount: "5800.00" },
      { label: "90+", count: 1, total_amount: "2820.00" },
    ],
    revenue_trend: mockMonthLabels().map((label, i) => ({
      period_label: label,
      period_start: toIso(new Date(now.getFullYear(), now.getMonth() - (11 - i), 1)),
      // Trend is always the trailing 12 months from today, independent of the
      // selected period/offset -- matches revenue_summary()'s real backend behavior.
      total_amount: MOCK_MONTHLY_REVENUE[MOCK_MONTHLY_REVENUE.length - 12 + i].toFixed(2),
    })),
    top_customers: MOCK_TOP_CUSTOMERS,
    status_breakdown: [
      { label: "pending", count: 6, total_amount: "18400.00" },
      { label: "outstanding", count: 28, total_amount: "94320.00" },
      { label: "paid", count: 112, total_amount: "612400.00" },
    ],
    validated_invoice_count: 140,
    avg_days_to_pay: 22.4,
  };
}

export default function Finance() {
  const { t } = useI18n();
  const { show } = useAppState();
  const [period, setPeriod] = useState<FinancePeriod>("month");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<FinanceSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [isDemoData, setIsDemoData] = useState(false);

  useEffect(() => {
    let active = true;
    // Genuinely syncs to period/offset changing over time (re-fetching a new summary),
    // not state derivable once at mount, so it can't move out of the effect.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    setError("");
    fetchFinanceSummary(period, offset)
      .then((response) => {
        if (!active) return;
        setData(response);
        setIsDemoData(false);
        setLoading(false);
      })
      .catch((err) => {
        if (!active) return;
        const message = err instanceof Error ? err.message : "Failed to load finance summary.";
        if (message === "insufficient_role") {
          // A real permission denial must never be papered over with demo numbers --
          // that would misrepresent what this role can actually see.
          setError("Your role doesn't have access to financial figures. Ask an owner/director, finance, or compliance user.");
          setData(null);
          setIsDemoData(false);
        } else {
          setData(buildMockFinanceSummary(period, offset));
          setIsDemoData(true);
          setError("");
        }
        setLoading(false);
      });
    return () => { active = false; };
  }, [period, offset]);

  const changePeriod = (next: FinancePeriod) => {
    setPeriod(next);
    setOffset(0);
  };

  const exportCsv = () => {
    if (!data) return;
    const rows: (string | number)[][] = [
      ["Financial Dashboard export", periodLabel(data)],
      ...(isDemoData ? [["NOTE", "Demo data -- live backend unreachable, figures are illustrative"]] : []),
      [],
      ["Metric", "Value"],
      ["Total revenue", data.total_revenue],
      ["Prior period revenue", data.prior_period_revenue],
      ["Outstanding AR", data.outstanding_ar],
      ["Validated invoices", data.validated_invoice_count],
      ["Avg days to pay", data.avg_days_to_pay ?? ""],
      [],
      ["Revenue trend", "Amount"],
      ...data.revenue_trend.map((p) => [p.period_label, p.total_amount]),
      [],
      ["AR aging bucket", "Count", "Amount"],
      ...data.ar_aging.map((b) => [AGING_LABELS[b.label], b.count, b.total_amount]),
      [],
      ["Top customer", "Amount", "Invoices"],
      ...data.top_customers.map((c) => [c.name, c.total_amount, c.invoice_count]),
    ];
    downloadCsv("finbrain-finance-dashboard.csv", rows);
  };

  return (
    <div className="fb-root fb-shell">
      <Sidebar current="finance" />
      <AppTopBar current="finance" />

      <header className="fb-app-header">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "1rem", flexWrap: "wrap" }}>
          <div>
            <h1>{t("finance.title")}</h1>
            <p>{t("finance.desc")}</p>
          </div>
          <button className="fb-btn fb-btn-outline" type="button" onClick={exportCsv} disabled={!data}>
            <span>{t("export.csv")}</span>
          </button>
        </div>
        <div className="fb-audit-filters" aria-label="Select reporting period" style={{ marginTop: "1rem" }}>
          {(["month", "quarter", "year"] as FinancePeriod[]).map((value) => (
            <button
              key={value}
              type="button"
              className={period === value ? "is-current" : ""}
              aria-pressed={period === value}
              onClick={() => changePeriod(value)}
            >
              {value === "month" ? "Month" : value === "quarter" ? "Quarter" : "Year"}
            </button>
          ))}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: ".6rem", marginTop: ".6rem" }}>
          <button
            type="button"
            className="fb-btn fb-btn-outline"
            style={{ padding: ".3rem .6rem" }}
            onClick={() => setOffset((o) => o - 1)}
            disabled={isDemoData && offset <= MOCK_MIN_OFFSET[period]}
            aria-label="Previous period"
          >‹</button>
          <strong style={{ minWidth: "10ch", textAlign: "center" }}>{data ? periodLabel(data) : "—"}</strong>
          <button
            type="button"
            className="fb-btn fb-btn-outline"
            style={{ padding: ".3rem .6rem" }}
            onClick={() => setOffset((o) => Math.min(0, o + 1))}
            disabled={offset >= 0}
            aria-label="Next period"
          >›</button>
        </div>
      </header>

      {loading && <div className="fb-callout">Loading finance summary…</div>}
      {!loading && error && (
        <div className="fb-callout" style={{ borderColor: "var(--chart-attn)", color: "var(--chart-attn)" }}>{error}</div>
      )}
      {!loading && !error && isDemoData && (
        <div className="fb-callout" style={{ borderColor: "var(--chart-attn)", color: "var(--ink)" }}>
          <strong>Demo data.</strong> The live backend for this dashboard isn't reachable right now, so every figure below is illustrative, not real.
        </div>
      )}

      {!loading && !error && data && (
        <>
          <div className="fb-kpi-row">
            <div className="fb-kpi-tile">
              <div className="fb-kpi-label">Total revenue</div>
              <div className="fb-kpi-value">{formatCurrency(data.total_revenue)}</div>
              <div className={"fb-kpi-delta " + (data.revenue_change_pct === null ? "" : data.revenue_change_pct >= 0 ? "is-good" : "is-attn")}>
                {data.revenue_change_pct === null
                  ? "No prior-period data"
                  : `${data.revenue_change_pct >= 0 ? "▲" : "▼"} ${Math.abs(data.revenue_change_pct).toFixed(1)}% vs prior ${data.period}`}
              </div>
            </div>
            <button className="fb-kpi-tile fb-kpi-tile-link" type="button" onClick={() => show("einvoice")} title="See the invoices behind this number">
              <div className="fb-kpi-label">Outstanding AR</div>
              <div className="fb-kpi-value">{formatCurrency(data.outstanding_ar)}</div>
              <div className="fb-kpi-delta">Validated, unpaid invoices</div>
              <span className="fb-kpi-tile-cta">View invoices →</span>
            </button>
            <div className="fb-kpi-tile">
              <div className="fb-kpi-label">Invoices validated</div>
              <div className="fb-kpi-value">{data.validated_invoice_count}</div>
              <div className="fb-kpi-delta">All-time, this tenant</div>
            </div>
            <div className="fb-kpi-tile">
              <div className="fb-kpi-label">Avg days to pay</div>
              <div className="fb-kpi-value">{data.avg_days_to_pay === null ? "—" : data.avg_days_to_pay.toFixed(1)}</div>
              <div className="fb-kpi-delta">{data.avg_days_to_pay === null ? "No paid invoices yet" : "Issue date to payment date"}</div>
            </div>
          </div>

          <div className="fb-chart-section">
            <h2>Revenue trend</h2>
            <p className="fb-chart-caption">Trailing 12 months of validated invoice revenue. Hover for exact figures.</p>
            <div className="fb-chart-card">
              <div className="fb-chart-legend">
                <span><span className="fb-legend-dot" style={{ background: "var(--viz-1)" }}></span>Revenue</span>
              </div>
              <RevenueTrendChart data={data} />
            </div>
          </div>

          <div className="fb-chart-section">
            <h2>Top customers by revenue</h2>
            <p className="fb-chart-caption">Validated invoices, all time, ranked by total billed.</p>
            <div className="fb-chart-card">
              <TopCustomersChart customers={data.top_customers} />
            </div>
          </div>

          <div className="fb-chart-section">
            <h2>Accounts receivable aging</h2>
            <p className="fb-chart-caption">Validated, unpaid invoices grouped by days past due date.</p>
            <div className="fb-table-wrap">
              <table className="fb-table">
                <thead>
                  <tr><th>Bucket</th><th style={{ textAlign: "right" }}>Invoices</th><th style={{ textAlign: "right" }}>Amount</th></tr>
                </thead>
                <tbody>
                  {data.ar_aging.every((bucket) => bucket.count === 0) ? (
                    <tr><td colSpan={3} style={{ color: "var(--ink-soft)" }}>No outstanding invoices.</td></tr>
                  ) : (
                    data.ar_aging.map((bucket) => (
                      <tr key={bucket.label}>
                        <td>{AGING_LABELS[bucket.label]}</td>
                        <td className="fb-num">{bucket.count}</td>
                        <td className="fb-num">{formatCurrency(bucket.total_amount)}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="fb-chart-section">
            <h2>Invoice status</h2>
            <p className="fb-chart-caption">Every e-invoice record for this tenant, by document and payment status.</p>
            <div className="fb-table-wrap">
              <table className="fb-table">
                <thead>
                  <tr><th>Status</th><th style={{ textAlign: "right" }}>Invoices</th><th style={{ textAlign: "right" }}>Amount</th></tr>
                </thead>
                <tbody>
                  {data.status_breakdown.map((row) => (
                    <tr key={row.label}>
                      <td style={{ textTransform: "capitalize" }}>{row.label}</td>
                      <td className="fb-num">{row.count}</td>
                      <td className="fb-num">{formatCurrency(row.total_amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
