import { useEffect, useMemo, useState } from "react";
import { useAppState } from "../lib/appState";
import { Sidebar, AppTopBar } from "../components/Nav";
import { EmptyState } from "../components/EmptyState";
import {
  fetchEinvoiceReadiness,
  fetchEinvoiceRecords,
  type EInvoiceApiRecord,
} from "../api/client";
import { buildCustomers, formatRm, toAmount, type CustomerAggregate } from "../lib/customerAggregation";

type LoadState = "loading" | "loaded" | "error";

function NotAvailableNote({ label, detail }: { label: string; detail: string }) {
  return (
    <div className="fb-customer-unavailable">
      <span className="fb-home-not-connected">
        <span className="fb-home-dot attn"></span>{label}
      </span>
      <p className="fb-fine">{detail}</p>
    </div>
  );
}

function CustomerDetail({ customer, onBack }: { customer: CustomerAggregate; onBack: () => void }) {
  const { showEinvoiceDetail } = useAppState();
  const sortedInvoices = [...customer.invoices].sort((a, b) => (b.issue_date ?? "").localeCompare(a.issue_date ?? ""));

  return (
    <div className="fb-page-body">
      <button className="fb-link-toggle" type="button" onClick={onBack} style={{ marginBottom: "1rem" }}>
        <span aria-hidden="true">←</span> All customers
      </button>

      <div className="fb-customer-detail-head">
        <h2>{customer.name}</h2>
        {customer.overdueTotal > 0 && (
          <span className="fb-status-pill is-review">
            <span className="fb-status-dot"></span>{customer.oldestOverdueDays} day{customer.oldestOverdueDays === 1 ? "" : "s"} overdue
          </span>
        )}
      </div>

      <div className="fb-kpi-row" style={{ padding: "0 0 1.4rem" }}>
        <div className="fb-kpi-tile">
          <div className="fb-kpi-label">Outstanding</div>
          <div className="fb-kpi-value">{formatRm(customer.outstandingTotal)}</div>
        </div>
        <div className="fb-kpi-tile">
          <div className="fb-kpi-label">Overdue</div>
          <div className="fb-kpi-value" style={{ color: customer.overdueTotal > 0 ? "var(--chart-attn)" : undefined }}>{formatRm(customer.overdueTotal)}</div>
        </div>
        <div className="fb-kpi-tile">
          <div className="fb-kpi-label">Invoices</div>
          <div className="fb-kpi-value">{customer.invoices.length}</div>
        </div>
        <div className="fb-kpi-tile">
          <div className="fb-kpi-label">e-Invoice blockers</div>
          <div className="fb-kpi-value" style={{ color: customer.blockerCount > 0 ? "var(--chart-attn)" : "var(--chart-good)" }}>{customer.blockerCount}</div>
        </div>
      </div>

      <h3 className="fb-eyebrow" style={{ margin: "0 0 .7rem" }}>Invoices</h3>
      <div className="fb-table-wrap" style={{ marginBottom: "1.6rem" }}>
        <table className="fb-table">
          <thead>
            <tr><th>Date</th><th>Invoice</th><th>Amount</th><th>Status</th></tr>
          </thead>
          <tbody>
            {sortedInvoices.map((inv) => (
              <tr key={inv.id} onClick={() => showEinvoiceDetail(String(inv.id))} style={{ cursor: "pointer" }}>
                <td>{inv.issue_date ?? "—"}</td>
                <td>{inv.invoice_no ?? `#${inv.id}`}</td>
                <td className="fb-num-left">{formatRm(toAmount(inv.total_amount))}</td>
                <td>
                  <span className="fb-status-pill">
                    <span className="fb-status-dot"></span>{inv.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3 className="fb-eyebrow" style={{ margin: "0 0 .7rem" }}>Beyond invoicing</h3>
      <div className="fb-customer-unavailable-grid">
        <NotAvailableNote
          label="Payment promises — not tracked yet"
          detail="No commitment-to-pay history is recorded for this customer today."
        />
        <NotAvailableNote
          label="Complaints — not tracked yet"
          detail="No support or dispute records are linked to this customer today."
        />
        <NotAvailableNote
          label="Email & Telegram activity — not linked yet"
          detail="Messages aren't connected to a specific customer today, so they can't appear in this timeline."
        />
      </div>
    </div>
  );
}

export default function Customers() {
  const { currentCustomerKey } = useAppState();
  const [records, setRecords] = useState<EInvoiceApiRecord[]>([]);
  const [blockerIds, setBlockerIds] = useState<Set<number>>(new Set());
  const [state, setState] = useState<LoadState>("loading");
  const [selectedKey, setSelectedKey] = useState<string | null>(currentCustomerKey);

  useEffect(() => {
    let active = true;
    Promise.all([fetchEinvoiceRecords(), fetchEinvoiceReadiness()])
      .then(([recs, readiness]) => {
        if (!active) return;
        setRecords(recs);
        setBlockerIds(new Set([...readiness.critical.records, ...readiness.warning.records].map((r) => r.id)));
        setState("loaded");
      })
      .catch(() => { if (active) setState("error"); });
    return () => { active = false; };
  }, []);

  const customers = useMemo(() => buildCustomers(records, blockerIds), [records, blockerIds]);
  const selected = customers.find((c) => c.key === selectedKey) ?? null;

  return (
    <div className="fb-root fb-shell">
      <Sidebar current="customers" />
      <AppTopBar current="customers" />

      <header className="fb-app-header">
        <h1>Customers</h1>
        <p>Ranked by invoicing data — email and Telegram activity aren't linked to a customer yet, so this view covers e-Invoicing only.</p>
      </header>

      {state === "loading" && <div className="fb-callout">Loading customers…</div>}
      {state === "error" && <div className="fb-callout" style={{ borderColor: "var(--chart-attn)", color: "var(--chart-attn)" }}>Couldn't load customer data.</div>}

      {state === "loaded" && selected && (
        <CustomerDetail customer={selected} onBack={() => setSelectedKey(null)} />
      )}

      {state === "loaded" && !selected && (
        <div className="fb-page-body">
          {customers.length === 0 ? (
            <EmptyState
              icon={<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="9" cy="7" r="3.2" /><path d="M2.5 20a6.5 6.5 0 0 1 13 0" /></svg>}
              title="No customers yet"
              description="Customers appear here once e-Invoicing records name a buyer."
            />
          ) : (
            <div className="fb-table-wrap">
              <table className="fb-table">
                <thead>
                  <tr><th>Customer</th><th>Outstanding</th><th>Overdue</th><th>Invoices</th><th>Blockers</th><th aria-hidden="true"></th></tr>
                </thead>
                <tbody>
                  {customers.map((c) => (
                    <tr key={c.key} onClick={() => setSelectedKey(c.key)} style={{ cursor: "pointer" }}>
                      <td>{c.name}</td>
                      <td className="fb-num-left">{formatRm(c.outstandingTotal)}</td>
                      <td className="fb-num-left" style={{ color: c.overdueTotal > 0 ? "var(--chart-attn)" : undefined }}>
                        {c.overdueTotal > 0 ? formatRm(c.overdueTotal) : "—"}
                      </td>
                      <td>{c.invoices.length}</td>
                      <td>{c.blockerCount > 0 ? c.blockerCount : "—"}</td>
                      <td className="fb-fine">View →</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
