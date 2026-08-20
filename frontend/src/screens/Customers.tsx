import { useEffect, useState } from "react";
import {
  createCustomerEndpoint,
  createOutreachAction,
  fetchCustomer,
  fetchCustomerEndpoints,
  fetchCustomers,
  fetchOutreachActions,
  transitionOutreachAction,
  verifyCustomerEndpoint,
  type CustomerDetail,
  type CustomerEndpoint,
  type CustomerSummary,
  type OutreachAction,
} from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { AppTopBar, Sidebar } from "../components/Nav";
import { useAppState } from "../lib/appState";
import { formatRm } from "../lib/customerAggregation";

type LoadState = "loading" | "loaded" | "error";

function CustomerWorkspace({ customer, onBack }: { customer: CustomerDetail; onBack: () => void }) {
  const { askAbout, askRole } = useAppState();
  const [endpoints, setEndpoints] = useState<CustomerEndpoint[]>([]);
  const [actions, setActions] = useState<OutreachAction[]>([]);
  const [email, setEmail] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const canManage = askRole === "finance_ops" || askRole === "owner_director";
  const canVerify = askRole === "owner_director";
  const refresh = async () => {
    const [endpointRows, actionRows] = await Promise.all([
      fetchCustomerEndpoints(customer.id),
      fetchOutreachActions(),
    ]);
    setEndpoints(endpointRows);
    setActions(actionRows.filter((row) => row.customer_id === customer.id));
  };
  useEffect(() => {
    if (!canManage) return;
    let active = true;
    void Promise.all([
      fetchCustomerEndpoints(customer.id),
      fetchOutreachActions(),
    ]).then(([endpointRows, actionRows]) => {
      if (!active) return;
      setEndpoints(endpointRows);
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
      <div><h2>{customer.name}</h2><p className="fb-fine">Verified cross-source customer workspace</p></div>
      <span className="fb-status-pill is-review"><span className="fb-status-dot"></span>{customer.priority} · {customer.attention_score}/100</span>
    </div>
    <div className="fb-kpi-row" style={{ padding: "0 0 1.4rem" }}>
      <div className="fb-kpi-tile"><div className="fb-kpi-label">Outstanding</div><div className="fb-kpi-value">{formatRm(Number(customer.outstanding_total))}</div></div>
      <div className="fb-kpi-tile"><div className="fb-kpi-label">Overdue</div><div className="fb-kpi-value">{formatRm(Number(customer.overdue_total))}</div></div>
      <div className="fb-kpi-tile"><div className="fb-kpi-label">Invoices</div><div className="fb-kpi-value">{customer.invoice_count}</div></div>
      <div className="fb-kpi-tile"><div className="fb-kpi-label">Linked sources</div><div className="fb-kpi-value">{customer.linked_source_count}</div></div>
    </div>
    <button className="fb-btn fb-btn-solid" type="button" onClick={() => askAbout("What needs attention for this customer, and why?")}>Ask about this customer</button>
    <h3 style={{ marginTop: "1.5rem" }}>Why this customer needs attention</h3>
    {customer.attention_signals.length ? customer.attention_signals.map((signal, index) =>
      <div className="fb-callout" key={`${signal.signal_type}-${index}`}><strong>+{signal.points}</strong> · {signal.label}<div className="fb-fine">{signal.freshness} · {Math.round(signal.confidence * 100)}% confidence</div></div>
    ) : <div className="fb-callout">No active attention signals.</div>}
    <h3 style={{ marginTop: "1.5rem" }}>Cross-source timeline</h3>
    {customer.timeline.length ? customer.timeline.map((item) =>
      <article className="fb-callout" key={item.event_id}><strong>{item.source_system.replaceAll("_", " ")}</strong><span className="fb-fine"> · {item.occurred_at ? new Date(item.occurred_at).toLocaleString() : "Undated"} · {item.identity_status}</span><p>{item.protected_summary}</p></article>
    ) : <div className="fb-callout">No verified protected records are linked yet.</div>}
    {canManage && <section style={{ marginTop: "1.5rem" }}>
      <h3>Governed email outreach</h3>
      <p className="fb-fine">Email addresses and message content are protected at rest. Submission requires a verified endpoint; sending requires separate owner approval.</p>
      {message && <div className="fb-callout" role="status">{message}</div>}
      <div className="fb-callout">
        <strong>Protected endpoints</strong>
        {endpoints.map((endpoint) => <div key={endpoint.id} style={{ display: "flex", gap: ".6rem", alignItems: "center", marginTop: ".5rem", flexWrap: "wrap" }}>
          <span>{endpoint.masked_value} · {endpoint.verification_status}</span>
          {endpoint.verification_status === "observed" && canVerify && <button className="fb-btn fb-btn-outline" type="button" disabled={busy} onClick={() => void verify(endpoint.id)}>Verify endpoint</button>}
        </div>)}
        <div style={{ display: "flex", gap: ".6rem", marginTop: ".7rem", flexWrap: "wrap" }}>
          <input className="fb-input" type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="customer@example.com" aria-label="Customer email" />
          <button className="fb-btn fb-btn-outline" type="button" disabled={busy || !email.trim()} onClick={() => void addEndpoint()}>Protect endpoint</button>
        </div>
      </div>
      <div className="fb-callout">
        <strong>Draft a response</strong>
        <input className="fb-input" value={subject} onChange={(event) => setSubject(event.target.value)} placeholder="Subject" aria-label="Outreach subject" style={{ display: "block", width: "100%", marginTop: ".6rem" }} />
        <textarea className="fb-input" value={body} onChange={(event) => setBody(event.target.value)} placeholder="Message" aria-label="Outreach message" rows={5} style={{ display: "block", width: "100%", marginTop: ".6rem" }} />
        <button className="fb-btn fb-btn-solid" type="button" disabled={busy || !subject.trim() || !body.trim()} onClick={() => void submitOutreach()} style={{ marginTop: ".6rem" }}>Submit for approval</button>
      </div>
      <h3>Outreach history</h3>
      {actions.length ? actions.map((action) => <div className="fb-callout" key={action.id}>
        <strong>{action.status.replaceAll("_", " ")}</strong> · {new Date(action.created_at).toLocaleString()}
        <div className="fb-fine">{action.protected_subject}</div>
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
  return <div className="fb-root fb-shell">
    <Sidebar current="customers" /><AppTopBar current="customers" />
    <header className="fb-app-header"><h1>Customers</h1><p>Verified cross-source evidence ranked by deterministic attention signals.</p></header>
    {state === "loading" && <div className="fb-callout">Loading customer intelligence…</div>}
    {state === "error" && <div className="fb-callout">Customer intelligence is not enabled or could not be loaded.</div>}
    {state === "loaded" && selected && <CustomerWorkspace customer={selected} onBack={() => setSelected(null)} />}
    {state === "loaded" && !selected && <div className="fb-page-body">
      {!rows.length ? <EmptyState icon="◎" title="No linked customers yet" description="Customers appear after structured buyer identities are linked to protected records." /> :
        <div className="fb-table-wrap"><table className="fb-table"><thead><tr><th>Customer</th><th>Attention</th><th>Outstanding</th><th>Overdue</th><th>Sources</th></tr></thead><tbody>{rows.map((row) => <tr key={row.id} onClick={() => void open(row.id)} style={{ cursor: "pointer" }}><td>{row.name}</td><td>{row.attention_score} · {row.priority}</td><td>{formatRm(Number(row.outstanding_total))}</td><td>{formatRm(Number(row.overdue_total))}</td><td>{row.linked_source_count}</td></tr>)}</tbody></table></div>}
    </div>}
  </div>;
}
