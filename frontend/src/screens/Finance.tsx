import { useI18n } from "../lib/i18n";
import { AppNav } from "../components/Nav";

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

export default function Finance() {
  const { t } = useI18n();

  const exportCsv = () => downloadCsv("finbrain-finance-dashboard.csv", [
    ["Metric", "Value", "Change vs last quarter"],
    ["Total revenue", "RM 1,840,000", "+12.4%"],
    ["Total profit", "RM 612,000", "+8.1%"],
    ["Profit margin", "33.3%", "+1.2 pts"],
    ["Outstanding AR", "RM 94,000", "+4.2% — needs review"],
  ]);

  return (
    <div className="fb-root">
      <AppNav current="finance" />

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
        <div className="fb-kpi-tile">
          <div className="fb-kpi-label">Outstanding AR</div>
          <div className="fb-kpi-value">RM 94K</div>
          <div className="fb-kpi-delta is-attn">⚠ 4.2% vs last quarter — review</div>
          <svg width="96" height="28" viewBox="0 0 96 28" role="img" aria-label="Outstanding receivables trending up, needs attention">
            <polyline points="2,17.6 15.1,15.6 28.3,14 41.4,12.4 54.6,11 67.7,9.6 80.9,8 94,7" fill="none" stroke="var(--ink-soft)" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
            <circle cx="94" cy="7" r="3" fill="var(--chart-attn)" />
          </svg>
        </div>
      </div>

      <div className="fb-chart-section">
        <h2>Revenue vs. profit</h2>
        <p className="fb-chart-caption">Monthly, in RM thousands.</p>
        <div className="fb-chart-card">
          <div className="fb-chart-legend">
            <span><span className="fb-legend-dot" style={{ background: "var(--viz-1)" }}></span>Revenue</span>
            <span><span className="fb-legend-dot" style={{ background: "var(--viz-2)" }}></span>Profit</span>
          </div>
          <svg width="640" height="250" viewBox="0 0 640 250" role="img" aria-label="Line chart comparing monthly revenue and profit over 12 months, both trending gently upward, revenue consistently above profit">
            <line x1="40" y1="20" x2="40" y2="230" stroke="var(--line)" strokeWidth="1" />
            <line x1="40" y1="230" x2="590" y2="230" stroke="var(--line)" strokeWidth="1" />
            <line x1="40" y1="177.5" x2="590" y2="177.5" stroke="var(--line)" strokeWidth="1" />
            <line x1="40" y1="125" x2="590" y2="125" stroke="var(--line)" strokeWidth="1" />
            <line x1="40" y1="72.5" x2="590" y2="72.5" stroke="var(--line)" strokeWidth="1" />
            <line x1="40" y1="20" x2="590" y2="20" stroke="var(--line)" strokeWidth="1" />
            <text x="34" y="233" textAnchor="end" fontSize="9" fill="var(--ink-soft)">0</text>
            <text x="34" y="180.5" textAnchor="end" fontSize="9" fill="var(--ink-soft)">50</text>
            <text x="34" y="128" textAnchor="end" fontSize="9" fill="var(--ink-soft)">100</text>
            <text x="34" y="75.5" textAnchor="end" fontSize="9" fill="var(--ink-soft)">150</text>
            <text x="34" y="23" textAnchor="end" fontSize="9" fill="var(--ink-soft)">200</text>

            <text x="40" y="244" textAnchor="middle" fontSize="9" fill="var(--ink-soft)">Jan</text>
            <text x="89.5" y="244" textAnchor="middle" fontSize="9" fill="var(--ink-soft)">Feb</text>
            <text x="138.9" y="244" textAnchor="middle" fontSize="9" fill="var(--ink-soft)">Mar</text>
            <text x="188.4" y="244" textAnchor="middle" fontSize="9" fill="var(--ink-soft)">Apr</text>
            <text x="237.8" y="244" textAnchor="middle" fontSize="9" fill="var(--ink-soft)">May</text>
            <text x="287.3" y="244" textAnchor="middle" fontSize="9" fill="var(--ink-soft)">Jun</text>
            <text x="336.7" y="244" textAnchor="middle" fontSize="9" fill="var(--ink-soft)">Jul</text>
            <text x="386.2" y="244" textAnchor="middle" fontSize="9" fill="var(--ink-soft)">Aug</text>
            <text x="435.6" y="244" textAnchor="middle" fontSize="9" fill="var(--ink-soft)">Sep</text>
            <text x="485.1" y="244" textAnchor="middle" fontSize="9" fill="var(--ink-soft)">Oct</text>
            <text x="534.5" y="244" textAnchor="middle" fontSize="9" fill="var(--ink-soft)">Nov</text>
            <text x="584" y="244" textAnchor="middle" fontSize="9" fill="var(--ink-soft)">Dec</text>

            <polyline points="40,95.6 89.5,91.4 138.9,85.1 188.4,77.8 237.8,72.5 287.3,67.3 336.7,64.1 386.2,59.9 435.6,53.6 485.1,49.4 534.5,56.8 584,49.4" fill="none" stroke="var(--viz-1)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
            <circle cx="584" cy="49.4" r="4" fill="var(--viz-1)" stroke="var(--card)" strokeWidth="2" />
            <text x="592" y="52.4" fontSize="10" fontWeight="700" fill="var(--ink)">RM172K</text>

            <polyline points="40,185.9 89.5,183.8 138.9,181.7 188.4,179.6 237.8,177.5 287.3,176.5 336.7,175.4 386.2,173.3 435.6,172.3 485.1,170.2 534.5,173.3 584,170.2" fill="none" stroke="var(--viz-2)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
            <circle cx="584" cy="170.2" r="4" fill="var(--viz-2)" stroke="var(--card)" strokeWidth="2" />
            <text x="592" y="173.2" fontSize="10" fontWeight="700" fill="var(--ink)">RM57K</text>
          </svg>
        </div>
      </div>

      <div className="fb-chart-section">
        <h2>Revenue by business unit</h2>
        <p className="fb-chart-caption">Trailing 12 months, in RM thousands.</p>
        <div className="fb-chart-card">
          <svg width="640" height="210" viewBox="0 0 640 210" role="img" aria-label="Horizontal bar chart of revenue by business unit: SaaS Subscriptions RM620K, Transaction Fees RM480K, Advisory RM340K, Compliance Ops RM260K, Other RM140K">
            <text x="136" y="24" textAnchor="end" fontSize="10.5" fill="var(--ink)">SaaS Subscriptions</text>
            <path d="M144,10 L526.2,10 Q530.2,10 530.2,14 L530.2,26 Q530.2,30 526.2,30 L144,30 Z" fill="var(--viz-1)" />
            <text x="536.2" y="24" fontSize="10" fontWeight="700" fill="var(--ink)" style={{ fontVariantNumeric: "tabular-nums" }}>RM620K</text>

            <text x="136" y="64" textAnchor="end" fontSize="10.5" fill="var(--ink)">Transaction Fees</text>
            <path d="M144,50 L439.0,50 Q443.0,50 443.0,54 L443.0,66 Q443.0,70 439.0,70 L144,70 Z" fill="var(--viz-1)" />
            <text x="449.0" y="64" fontSize="10" fontWeight="700" fill="var(--ink)" style={{ fontVariantNumeric: "tabular-nums" }}>RM480K</text>

            <text x="136" y="104" textAnchor="end" fontSize="10.5" fill="var(--ink)">Advisory</text>
            <path d="M144,90 L351.8,90 Q355.8,90 355.8,94 L355.8,106 Q355.8,110 351.8,110 L144,110 Z" fill="var(--viz-1)" />
            <text x="361.8" y="104" fontSize="10" fontWeight="700" fill="var(--ink)" style={{ fontVariantNumeric: "tabular-nums" }}>RM340K</text>

            <text x="136" y="144" textAnchor="end" fontSize="10.5" fill="var(--ink)">Compliance Ops</text>
            <path d="M144,130 L302.0,130 Q306.0,130 306.0,134 L306.0,146 Q306.0,150 302.0,150 L144,150 Z" fill="var(--viz-1)" />
            <text x="312.0" y="144" fontSize="10" fontWeight="700" fill="var(--ink)" style={{ fontVariantNumeric: "tabular-nums" }}>RM260K</text>

            <text x="136" y="184" textAnchor="end" fontSize="10.5" fill="var(--ink)">Other</text>
            <path d="M144,170 L227.2,170 Q231.2,170 231.2,174 L231.2,186 Q231.2,190 227.2,190 L144,190 Z" fill="var(--viz-1)" />
            <text x="237.2" y="184" fontSize="10" fontWeight="700" fill="var(--ink)" style={{ fontVariantNumeric: "tabular-nums" }}>RM140K</text>
          </svg>
        </div>
      </div>
    </div>
  );
}
