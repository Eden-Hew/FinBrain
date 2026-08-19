import { useState, type MouseEvent } from "react";
import { useI18n } from "../lib/i18n";
import { useAppState } from "../lib/appState";
import { Sidebar, AppTopBar } from "../components/Nav";

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

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const REVENUE = [130, 134, 140, 147, 153, 159, 163, 168, 175, 178, 171, 172];
const PROFIT = [38, 39, 40, 41, 42, 44, 45, 46, 48, 49, 47, 57];

const CHART_W = 640;
const CHART_H = 250;
const PAD_LEFT = 40;
const PAD_RIGHT = 50;
const PAD_TOP = 20;
const PAD_BOTTOM = 20;
const MAX_VALUE = 200;

function xPos(i: number) {
  return PAD_LEFT + (i / (MONTHS.length - 1)) * (CHART_W - PAD_LEFT - PAD_RIGHT);
}
function yPos(value: number) {
  return PAD_TOP + (CHART_H - PAD_TOP - PAD_BOTTOM) * (1 - value / MAX_VALUE);
}

function RevenueProfitChart() {
  const [hover, setHover] = useState<number | null>(null);
  const revenuePoints = REVENUE.map((v, i) => `${xPos(i)},${yPos(v)}`).join(" ");
  const profitPoints = PROFIT.map((v, i) => `${xPos(i)},${yPos(v)}`).join(" ");
  const gridValues = [0, 50, 100, 150, 200];

  const handleMove = (event: MouseEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const relX = ((event.clientX - rect.left) / rect.width) * CHART_W;
    let closest = 0;
    let closestDist = Infinity;
    MONTHS.forEach((_, i) => {
      const dist = Math.abs(xPos(i) - relX);
      if (dist < closestDist) { closestDist = dist; closest = i; }
    });
    setHover(closest);
  };

  return (
    <div className="fb-chart-hover-wrap">
      <svg
        viewBox={`0 0 ${CHART_W} ${CHART_H}`}
        role="img"
        aria-label="Line chart comparing monthly revenue and profit over 12 months, both trending gently upward, revenue consistently above profit"
        onMouseMove={handleMove}
        onMouseLeave={() => setHover(null)}
      >
        <line x1={PAD_LEFT} y1={PAD_TOP} x2={PAD_LEFT} y2={CHART_H - PAD_BOTTOM} stroke="var(--line)" strokeWidth="1" />
        <line x1={PAD_LEFT} y1={CHART_H - PAD_BOTTOM} x2={CHART_W - PAD_RIGHT} y2={CHART_H - PAD_BOTTOM} stroke="var(--line)" strokeWidth="1" />
        {gridValues.map((v) => (
          <g key={v}>
            <line x1={PAD_LEFT} y1={yPos(v)} x2={CHART_W - PAD_RIGHT} y2={yPos(v)} stroke="var(--line)" strokeWidth="1" />
            <text x={PAD_LEFT - 6} y={yPos(v) + 3} textAnchor="end" fontSize="9" fill="var(--ink-soft)">{v}</text>
          </g>
        ))}
        {MONTHS.map((m, i) => (
          <text key={m} x={xPos(i)} y={CHART_H - 6} textAnchor="middle" fontSize="9" fill="var(--ink-soft)">{m}</text>
        ))}

        <polyline points={revenuePoints} fill="none" stroke="var(--viz-1)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        <circle cx={xPos(11)} cy={yPos(REVENUE[11])} r="4" fill="var(--viz-1)" stroke="var(--card)" strokeWidth="2" />
        <text x={xPos(11) + 8} y={yPos(REVENUE[11]) + 3} fontSize="10" fontWeight="700" fill="var(--ink)">RM{REVENUE[11]}K</text>

        <polyline points={profitPoints} fill="none" stroke="var(--viz-2)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        <circle cx={xPos(11)} cy={yPos(PROFIT[11])} r="4" fill="var(--viz-2)" stroke="var(--card)" strokeWidth="2" />
        <text x={xPos(11) + 8} y={yPos(PROFIT[11]) + 3} fontSize="10" fontWeight="700" fill="var(--ink)">RM{PROFIT[11]}K</text>

        {hover !== null && (
          <>
            <line x1={xPos(hover)} y1={PAD_TOP} x2={xPos(hover)} y2={CHART_H - PAD_BOTTOM} stroke="var(--ink-soft)" strokeWidth="1" strokeDasharray="3 3" />
            <circle cx={xPos(hover)} cy={yPos(REVENUE[hover])} r="5" fill="var(--viz-1)" stroke="var(--card)" strokeWidth="2" />
            <circle cx={xPos(hover)} cy={yPos(PROFIT[hover])} r="5" fill="var(--viz-2)" stroke="var(--card)" strokeWidth="2" />
          </>
        )}
      </svg>
      {hover !== null && (
        <div className="fb-chart-tooltip" style={{ left: `${(xPos(hover) / CHART_W) * 100}%` }}>
          <strong>{MONTHS[hover]}</strong>
          <div><span className="fb-legend-dot" style={{ background: "var(--viz-1)" }} />Revenue RM{REVENUE[hover]}K</div>
          <div><span className="fb-legend-dot" style={{ background: "var(--viz-2)" }} />Profit RM{PROFIT[hover]}K</div>
        </div>
      )}
    </div>
  );
}

const BUSINESS_UNITS = [
  { label: "SaaS Subscriptions", value: 620 },
  { label: "Transaction Fees", value: 480 },
  { label: "Advisory", value: 340 },
  { label: "Compliance Ops", value: 260 },
  { label: "Other", value: 140 },
];

function BusinessUnitChart() {
  const [hover, setHover] = useState<number | null>(null);
  const barW = 640, barMax = 620, barLeft = 144, barRight = 526.2;
  const scale = (v: number) => barLeft + (v / barMax) * (barRight - barLeft);

  return (
    <svg width="100%" viewBox={`0 0 ${barW} 210`} role="img" aria-label="Horizontal bar chart of revenue by business unit: SaaS Subscriptions RM620K, Transaction Fees RM480K, Advisory RM340K, Compliance Ops RM260K, Other RM140K">
      {BUSINESS_UNITS.map((unit, i) => {
        const top = 10 + i * 40;
        const right = scale(unit.value);
        return (
          <g
            key={unit.label}
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(null)}
            style={{ cursor: "default" }}
          >
            <text x={barLeft - 8} y={top + 14} textAnchor="end" fontSize="10.5" fill="var(--ink)">{unit.label}</text>
            <path
              d={`M${barLeft},${top} L${right - 4},${top} Q${right},${top} ${right},${top + 4} L${right},${top + 16} Q${right},${top + 20} ${right - 4},${top + 20} L${barLeft},${top + 20} Z`}
              fill="var(--viz-1)"
              opacity={hover === null || hover === i ? 1 : 0.45}
              style={{ transition: "opacity .15s ease" }}
            />
            <text x={right + 10} y={top + 14} fontSize="10" fontWeight="700" fill="var(--ink)" style={{ fontVariantNumeric: "tabular-nums" }}>RM{unit.value}K</text>
          </g>
        );
      })}
    </svg>
  );
}

export default function Finance() {
  const { t } = useI18n();
  const { show } = useAppState();

  const exportCsv = () => downloadCsv("finbrain-finance-dashboard.csv", [
    ["Metric", "Value", "Change vs last quarter"],
    ["Total revenue", "RM 1,840,000", "+12.4%"],
    ["Total profit", "RM 612,000", "+8.1%"],
    ["Profit margin", "33.3%", "+1.2 pts"],
    ["Outstanding AR", "RM 94,000", "+4.2% — needs review"],
  ]);

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
          <button className="fb-btn fb-btn-outline" type="button" onClick={exportCsv}><span>{t("export.csv")}</span></button>
        </div>
      </header>

      <div className="fb-kpi-row">
        <div className="fb-kpi-tile">
          <div className="fb-kpi-label">Total revenue</div>
          <div className="fb-kpi-value">RM 1.84M</div>
          <div className="fb-kpi-delta is-good">▲ 12.4% vs last quarter</div>
          <svg width="96" height="28" viewBox="0 0 96 28" role="img" aria-label="Revenue trending up over the last 8 periods">
            <polyline points="2,15 15.1,14 28.3,16 41.4,13 54.6,11 67.7,10 80.9,8 94,6" fill="none" stroke="var(--ink-soft)" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
            <circle cx="94" cy="6" r="3" fill="var(--chart-good)" />
          </svg>
        </div>
        <div className="fb-kpi-tile">
          <div className="fb-kpi-label">Total profit</div>
          <div className="fb-kpi-value">RM 612K</div>
          <div className="fb-kpi-delta is-good">▲ 8.1% vs last quarter</div>
          <svg width="96" height="28" viewBox="0 0 96 28" role="img" aria-label="Profit trending up over the last 8 periods">
            <polyline points="2,16 15.1,15.6 28.3,14 41.4,13.6 54.6,12 67.7,10.4 80.9,9.6 94,8.4" fill="none" stroke="var(--ink-soft)" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
            <circle cx="94" cy="8.4" r="3" fill="var(--chart-good)" />
          </svg>
        </div>
        <div className="fb-kpi-tile">
          <div className="fb-kpi-label">Profit margin</div>
          <div className="fb-kpi-value">33.3%</div>
          <div className="fb-kpi-delta is-good">▲ 1.2 pts vs last quarter</div>
          <svg width="96" height="28" viewBox="0 0 96 28" role="img" aria-label="Profit margin roughly flat with a slight improvement">
            <polyline points="2,14 15.1,14.4 28.3,13.6 41.4,14 54.6,13.2 67.7,12.8 80.9,12 94,11.2" fill="none" stroke="var(--ink-soft)" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
            <circle cx="94" cy="11.2" r="3" fill="var(--chart-good)" />
          </svg>
        </div>
        <button className="fb-kpi-tile fb-kpi-tile-link" type="button" onClick={() => show("einvoice")} title="See the invoices behind this number">
          <div className="fb-kpi-label">Outstanding AR</div>
          <div className="fb-kpi-value">RM 94K</div>
          <div className="fb-kpi-delta is-attn">⚠ 4.2% vs last quarter — review</div>
          <svg width="96" height="28" viewBox="0 0 96 28" role="img" aria-label="Outstanding receivables trending up, needs attention">
            <polyline points="2,17.6 15.1,15.6 28.3,14 41.4,12.4 54.6,11 67.7,9.6 80.9,8 94,7" fill="none" stroke="var(--ink-soft)" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
            <circle cx="94" cy="7" r="3" fill="var(--chart-attn)" />
          </svg>
          <span className="fb-kpi-tile-cta">View invoices →</span>
        </button>
      </div>

      <div className="fb-chart-section">
        <h2>Revenue vs. profit</h2>
        <p className="fb-chart-caption">Monthly, in RM thousands. Hover the chart for exact figures.</p>
        <div className="fb-chart-card">
          <div className="fb-chart-legend">
            <span><span className="fb-legend-dot" style={{ background: "var(--viz-1)" }}></span>Revenue</span>
            <span><span className="fb-legend-dot" style={{ background: "var(--viz-2)" }}></span>Profit</span>
          </div>
          <RevenueProfitChart />
        </div>
      </div>

      <div className="fb-chart-section">
        <h2>Revenue by business unit</h2>
        <p className="fb-chart-caption">Trailing 12 months, in RM thousands.</p>
        <div className="fb-chart-card">
          <BusinessUnitChart />
        </div>
      </div>
    </div>
  );
}
