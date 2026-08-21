import { useEffect, useState, type ReactNode } from "react";
import {
  createCustomerEndpoint,
  createOutreachAction,
  fetchCustomer,
  fetchCustomerEndpoints,
  fetchCustomerIdentityClaims,
  fetchCustomers,
  fetchOutreachActions,
  revokeCustomerEndpoint,
  resolveCustomerIdentityClaim,
  transitionOutreachAction,
  verifyCustomerEndpoint,
  type CustomerDetail,
  type CustomerEndpoint,
  type CustomerIdentityClaim,
  type CustomerSummary,
  type OutreachAction,
} from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { MaskedText } from "../components/MaskedText";
import { AppTopBar, Sidebar } from "../components/Nav";
import { useAppState } from "../lib/appState";
import { displayCase, formatRm, isPlaceholderName } from "../lib/customerAggregation";

type LoadState = "loading" | "loaded" | "error";

const TIER_LABEL: Record<string, string> = { urgent: "Urgent", high: "High", monitoring: "Monitoring", healthy: "Healthy" };

function priorityPillClass(priority: string): string {
  if (priority === "urgent") return "is-urgent";
  if (priority === "high") return "is-review";
  if (priority === "healthy") return "is-active";
  return "";
}

function outreachStatusPillClass(status: OutreachAction["status"]): string {
  if (status === "sent" || status === "replied") return "is-active";
  if (status === "pending_approval" || status === "failed" || status === "rejected") return "is-review";
  return "";
}

// Same masked-name treatment used on the Briefing page's Attention list, so a
// customer whose name never resolved reads as an intentional privacy state
// here too, instead of raw "[person — restricted]" placeholder text.
function CustomerNameLabel({ name }: { name: string }) {
  if (isPlaceholderName(name)) {
    return (
      <span className="fb-mask-badge">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="4" y="10" width="16" height="10" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></svg>
        Protected customer
      </span>
    );
  }
  return <>{displayCase(name)}</>;
}

const SOURCE_ICONS: Record<string, ReactNode> = {
  einvoice: <path d="M6 2h9l3 3v17H6z M9 8h6M9 12h6M9 16h4" />,
  email: <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="m3 7 9 6 9-6" /></>,
  telegram: <path d="M4 4h13a3 3 0 0 1 3 3v7a3 3 0 0 1-3 3H9l-5 3v-3a3 3 0 0 1-3-3V7a3 3 0 0 1 3-3z" />,
  outreach: <><path d="m22 2-7 20-4-9-9-4Z" /><path d="M22 2 11 13" /></>,
};
const DEFAULT_SOURCE_ICON = <circle cx="12" cy="12" r="4" />;

function CustomerWorkspace({ customer: initialCustomer, onBack }: { customer: CustomerDetail; onBack: () => void }) {
  const { show, askRole } = useAppState();
  const [customer, setCustomer] = useState(initialCustomer);
  const [endpoints, setEndpoints] = useState<CustomerEndpoint[]>([]);
  const [identityClaims, setIdentityClaims] = useState<CustomerIdentityClaim[]>([]);
  const [actions, setActions] = useState<OutreachAction[]>([]);
  const [email, setEmail] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const canManage = askRole === "finance_ops" || askRole === "owner_director";
  const canVerify = askRole === "owner_director";
  const refresh = async () => {
    const [currentCustomer, endpointRows, claimRows, actionRows] = await Promise.all([
      fetchCustomer(customer.id),
      fetchCustomerEndpoints(customer.id),
      fetchCustomerIdentityClaims(customer.id),
      fetchOutreachActions(),
    ]);
    setCustomer(currentCustomer);
    setEndpoints(endpointRows);
    setIdentityClaims(claimRows);
    setActions(actionRows.filter((row) => row.customer_id === customer.id));
  };
  useEffect(() => {
    if (!canManage) return;
    let active = true;
    void Promise.all([
      fetchCustomerEndpoints(customer.id),
      fetchCustomerIdentityClaims(customer.id),
      fetchOutreachActions(),
    ]).then(([endpointRows, claimRows, actionRows]) => {
      if (!active) return;
      setEndpoints(endpointRows);
      setIdentityClaims(claimRows);
      setActions(actionRows.filter((row) => row.customer_id === customer.id));
    }).catch(() => {
      if (active) setMessage("Outreach records could not be loaded for this role.");
    });
    return () => { active = false; };
  }, [customer.id, canManage]);
  const addEndpoint = async () => {
    setBusy(true); setMessage("");
    try {
      await createCustomerEndpoint(customer.id, email);
      setEmail(""); await refresh();
      setMessage("Email protected and recorded. An owner must verify it before submission.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Endpoint registration failed."); }
    finally { setBusy(false); }
  };
  const verify = async (id: number) => {
    setBusy(true); setMessage("");
    try { await verifyCustomerEndpoint(id); await refresh(); setMessage("Endpoint verified."); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Verification failed."); }
    finally { setBusy(false); }
  };
  const revoke = async (id: number) => {
    setBusy(true); setMessage("");
    try { await revokeCustomerEndpoint(id); await refresh(); setMessage("Endpoint revoked. It can no longer be used for outreach."); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Revocation failed."); }
    finally { setBusy(false); }
  };
  const resolveClaim = async (id: number, decision: "accept_primary" | "accept_alias" | "reject") => {
    setBusy(true); setMessage("");
    try {
      await resolveCustomerIdentityClaim(id, decision);
      await refresh();
      setMessage("Identity evidence reviewed and the customer safety gate was recalculated.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Identity review failed."); }
    finally { setBusy(false); }
  };
  const submitOutreach = async () => {
    const endpoint = endpoints.find((row) => row.verification_status === "verified");
    if (!endpoint) { setMessage("A verified email endpoint is required."); return; }
    setBusy(true); setMessage("");
    try {
      const draft = await createOutreachAction(customer.id, {
        customerEndpointId: endpoint.id,
        subject,
        body,
        evidenceContentIds: customer.timeline.flatMap((item) => item.tokenized_content_id ? [item.tokenized_content_id] : []),
      });
      await transitionOutreachAction(draft.id, "submit");
      setSubject(""); setBody(""); await refresh();
      setMessage("Protected draft submitted for owner approval. Nothing has been sent yet.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Outreach submission failed."); }
    finally { setBusy(false); }
  };
  return <div className="fb-page-body">
    <button className="fb-link-toggle" type="button" onClick={onBack}>← All customers</button>
    <div className="fb-customer-detail-head">
      <div><h2><CustomerNameLabel name={customer.name} /></h2><p className="fb-fine">{customer.profile_status} · {customer.profile_origin} profile · identity {customer.identity_review_status.replaceAll("_", " ")}</p></div>
      <span className={"fb-status-pill " + priorityPillClass(customer.priority)}><span className="fb-status-dot"></span>{TIER_LABEL[customer.priority] ?? customer.priority} · {customer.attention_score}/100</span>
    </div>
    <div className="fb-kpi-row" style={{ padding: "0 0 1.4rem" }}>
      <div className="fb-kpi-tile"><div className="fb-kpi-label">Outstanding</div><div className="fb-kpi-value">{formatRm(Number(customer.outstanding_total))}</div></div>
      <div className="fb-kpi-tile"><div className="fb-kpi-label">Overdue</div><div className="fb-kpi-value">{formatRm(Number(customer.overdue_total))}</div></div>
      <div className="fb-kpi-tile"><div className="fb-kpi-label">Invoices</div><div className="fb-kpi-value">{customer.invoice_count}</div></div>
      <div className="fb-kpi-tile"><div className="fb-kpi-label">Linked sources</div><div className="fb-kpi-value">{customer.linked_source_count}</div></div>
    </div>
    <button className="fb-btn fb-btn-solid" type="button" onClick={() => show("agents")}>Ask about this customer</button>
    <h3 style={{ marginTop: "1.5rem" }}>Why this customer needs attention</h3>
    {customer.attention_signals.length ? (
      <div className="fb-signal-list">
        {customer.attention_signals.map((signal, index) => (
          <div className="fb-signal-card" key={`${signal.signal_type}-${index}`}>
            <span className="fb-signal-points">+{signal.points}</span>
            <div>
              <div>{signal.label}</div>
              <div className="fb-fine">{signal.freshness} · {Math.round(signal.confidence * 100)}% confidence</div>
            </div>
          </div>
        ))}
      </div>
    ) : <div className="fb-callout">No active attention signals.</div>}
    <h3 style={{ marginTop: "1.5rem" }}>Cross-source timeline</h3>
    {customer.timeline.length ? (
      <div className="fb-timeline">
        {customer.timeline.map((item) => (
          <div className="fb-timeline-item" key={item.event_id}>
            <span className="fb-timeline-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{SOURCE_ICONS[item.source_system] ?? DEFAULT_SOURCE_ICON}</svg>
            </span>
            <div className="fb-timeline-content">
              <strong>{item.source_system.replaceAll("_", " ")}</strong>
              <span className="fb-fine"> · {item.occurred_at ? new Date(item.occurred_at).toLocaleString() : "Undated"} · {item.identity_status}</span>
              <p><MaskedText text={item.protected_summary} /></p>
            </div>
          </div>
        ))}
      </div>
    ) : <div className="fb-callout">No verified protected records are linked yet.</div>}
    {canManage && <section style={{ marginTop: "1.5rem" }}>
      <h3>Governed email outreach</h3>
      <p className="fb-fine">Email addresses and message content are protected at rest. Submission requires a verified endpoint; sending requires separate owner approval.</p>
      {message && <div className="fb-callout" role="status">{message}</div>}
      <div className="fb-panel">
        <strong>Protected endpoints</strong>
        {endpoints.map((endpoint) => <div key={endpoint.id} style={{ display: "flex", gap: ".6rem", alignItems: "center", marginTop: ".5rem", flexWrap: "wrap" }}>
          <span>
            {endpoint.authorized_value ?? <MaskedText text={endpoint.masked_value} />} · {endpoint.verification_status} · {endpoint.origin.replaceAll("_", " ")}
            {endpoint.authorized_value && <span className="fb-fine"> · authorized owner view</span>}
          </span>
          {endpoint.verification_status === "observed" && canVerify && <button className="fb-btn fb-btn-outline" type="button" disabled={busy} onClick={() => void verify(endpoint.id)}>Verify endpoint</button>}
          {endpoint.verification_status !== "revoked" && canVerify && <button className="fb-btn fb-btn-outline" type="button" disabled={busy} onClick={() => void revoke(endpoint.id)}>Revoke endpoint</button>}
          {endpoint.verification_status === "revoked" && <span className="fb-fine">Re-enter the same address to restore it as observed.</span>}
        </div>)}
        <div style={{ display: "flex", gap: ".6rem", marginTop: ".7rem", flexWrap: "wrap" }}>
          <input className="fb-input" type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="customer@example.com" aria-label="Customer email" style={{ flex: "1 1 220px" }} />
          <button className="fb-btn fb-btn-outline" type="button" disabled={busy || !email.trim()} onClick={() => void addEndpoint()}>Protect endpoint</button>
        </div>
      </div>
      {!!identityClaims.length && <div className="fb-panel">
        <strong>Protected identity evidence</strong>
        <p className="fb-fine">Names are claims, not automatic profile mutations. Conflicts block outreach until an owner resolves them.</p>
        {identityClaims.map((claim) => <div key={claim.id} style={{ marginTop: ".7rem", paddingTop: ".7rem", borderTop: "1px solid var(--line)" }}>
          <div>{claim.authorized_value ?? <MaskedText text={claim.masked_value} />} · {claim.claim_basis.replaceAll("_", " ")} · {claim.status}</div>
          <div className="fb-fine">Seen {claim.occurrence_count} time(s) · {Math.round(claim.confidence * 100)}% confidence</div>
          {canVerify && (claim.status === "observed" || claim.status === "conflicting") && <div style={{ display: "flex", gap: ".5rem", marginTop: ".5rem", flexWrap: "wrap" }}>
            <button className="fb-btn fb-btn-outline" type="button" disabled={busy} onClick={() => void resolveClaim(claim.id, "accept_primary")}>Use as primary</button>
            <button className="fb-btn fb-btn-outline" type="button" disabled={busy} onClick={() => void resolveClaim(claim.id, "accept_alias")}>Accept as alias</button>
            <button className="fb-btn fb-btn-outline" type="button" disabled={busy} onClick={() => void resolveClaim(claim.id, "reject")}>Reject claim</button>
          </div>}
        </div>)}
      </div>}
      <div className="fb-panel">
        <strong>Draft a response</strong>
        <input className="fb-input" value={subject} onChange={(event) => setSubject(event.target.value)} placeholder="Subject" aria-label="Outreach subject" style={{ display: "block", width: "100%", marginTop: ".6rem" }} />
        <textarea className="fb-input" value={body} onChange={(event) => setBody(event.target.value)} placeholder="Message" aria-label="Outreach message" rows={5} style={{ display: "block", width: "100%", marginTop: ".6rem" }} />
        {customer.profile_status !== "confirmed" || customer.identity_review_status !== "clear" ? <div className="fb-fine" style={{ marginTop: ".6rem" }}>Outreach is blocked until an owner confirms this profile and resolves identity conflicts.</div> : null}
        <button className="fb-btn fb-btn-solid" type="button" disabled={busy || !subject.trim() || !body.trim() || customer.profile_status !== "confirmed" || customer.identity_review_status !== "clear"} onClick={() => void submitOutreach()} style={{ marginTop: ".6rem" }}>Submit for approval</button>
      </div>
      <h3>Outreach history</h3>
      {actions.length ? actions.map((action) => <div className="fb-panel" key={action.id}>
        <span className={"fb-status-pill " + outreachStatusPillClass(action.status)}><span className="fb-status-dot"></span>{action.status.replaceAll("_", " ")}</span>
        <span className="fb-fine"> · {new Date(action.created_at).toLocaleString()}</span>
        <div className="fb-fine" style={{ marginTop: ".4rem" }}>{action.protected_subject}</div>
        {action.failure_code && <div className="fb-fine">Failure: {action.failure_code}</div>}
      </div>) : <div className="fb-callout">No governed outreach exists for this customer.</div>}
    </section>}
  </div>;
}

export default function Customers() {
  const { currentCustomerKey, showCustomerDetail } = useAppState();
  const initialId = currentCustomerKey?.startsWith("id:") ? Number(currentCustomerKey.slice(3)) : null;
  const [rows, setRows] = useState<CustomerSummary[]>([]);
  const [selected, setSelected] = useState<CustomerDetail | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const [search, setSearch] = useState("");
  useEffect(() => {
    let active = true;
    fetchCustomers().then(async (customers) => {
      if (!active) return;
      setRows(customers);
      if (initialId) setSelected(await fetchCustomer(initialId));
      setState("loaded");
    }).catch(() => { if (active) setState("error"); });
    return () => { active = false; };
  }, [initialId]);
  const open = async (id: number) => {
    showCustomerDetail(`id:${id}`);
    setSelected(await fetchCustomer(id));
  };
  const query = search.trim().toLowerCase();
  const filteredRows = query ? rows.filter((row) => displayCase(row.name).toLowerCase().includes(query)) : rows;
  return <div className="fb-root fb-shell">
    <Sidebar current="customers" /><AppTopBar current="customers" />
    <header className="fb-app-header"><h1>Customers</h1><p>Confirmed and provisional customer context ranked by deterministic attention signals.</p></header>
    {state === "loading" && <div className="fb-callout">Loading customer intelligence…</div>}
    {state === "error" && <div className="fb-callout">Customer intelligence is not enabled or could not be loaded.</div>}
    {state === "loaded" && selected && <CustomerWorkspace customer={selected} onBack={() => setSelected(null)} />}
    {state === "loaded" && !selected && <div className="fb-page-body">
      <div className="fb-table-toolbar">
        <div className="fb-table-search">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" /></svg>
          <input type="text" placeholder="Search customers…" value={search} onChange={(event) => setSearch(event.target.value)} />
        </div>
      </div>
      <div className="fb-table-wrap">
        <table className="fb-table">
          <thead><tr><th>Customer</th><th>Attention</th><th>Overdue</th><th>Identity</th><th>Outstanding</th><th>Sources</th><th aria-hidden="true"></th></tr></thead>
          <tbody>
            {filteredRows.length === 0 ? (
              <tr><td colSpan={7}>
                <EmptyState
                  icon="◎"
                  title={rows.length === 0 ? "No linked customers yet" : "No customers match your search"}
                  description={rows.length === 0
                    ? "Customers appear after structured buyer identities are linked to protected records."
                    : "Try a different name, or clear the search to see all customers."}
                  action={rows.length > 0 && query ? { label: "Clear search", onClick: () => setSearch("") } : undefined}
                />
              </td></tr>
            ) : filteredRows.map((row) => (
              <tr
                key={row.id}
                className="fb-table-row-clickable"
                tabIndex={0}
                role="button"
                onClick={() => void open(row.id)}
                onKeyDown={(event) => { if (event.key === "Enter") void open(row.id); }}
              >
                <td><CustomerNameLabel name={row.name} /></td>
                <td>
                  <span className={"fb-status-pill " + priorityPillClass(row.priority)}><span className="fb-status-dot"></span>{TIER_LABEL[row.priority] ?? row.priority}</span>
                  <span className="fb-fine"> {row.attention_score}/100</span>
                </td>
                <td className={"fb-num" + (Number(row.overdue_total) > 0 ? " is-attn" : "")}>{formatRm(Number(row.overdue_total))}</td>
                <td>{row.profile_status}{row.identity_review_status === "review_required" ? " · review required" : ""}</td>
                <td className="fb-num">{formatRm(Number(row.outstanding_total))}</td>
                <td className="fb-num">{row.linked_source_count}</td>
                <td className="fb-table-row-chevron" aria-hidden="true">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m9 18 6-6-6-6" /></svg>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>}
  </div>;
}
