import { useEffect, useState } from "react";
import {
  fetchCustomerEndpoints,
  fetchOutreachStatus,
  generateOutreachAction,
  transitionOutreachAction,
  updateOutreachAction,
  type CustomerEndpoint,
  type OutreachAction,
  type Role,
} from "../../api/client";

interface Props {
  customerId: number;
  turnId: number;
  role: Role;
}

const DEFAULT_INSTRUCTION = "Draft a concise, professional reply that addresses this customer's request.";

export function OutreachComposerCard({ customerId, turnId, role }: Props) {
  const [open, setOpen] = useState(false);
  const [endpoints, setEndpoints] = useState<CustomerEndpoint[]>([]);
  const [endpointId, setEndpointId] = useState<number | null>(null);
  const [instruction, setInstruction] = useState(DEFAULT_INSTRUCTION);
  const [action, setAction] = useState<OutreachAction | null>(null);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open || endpoints.length) return;
    let active = true;
    void fetchCustomerEndpoints(customerId).then((rows) => {
      if (!active) return;
      const verified = rows.filter((row) => row.verification_status === "verified");
      setEndpoints(verified);
      setEndpointId(verified[0]?.id ?? null);
    }).catch((requestError) => {
      if (active) setError(requestError instanceof Error ? requestError.message : "Could not load customer email endpoints.");
    });
    return () => { active = false; };
  }, [customerId, endpoints.length, open]);

  useEffect(() => {
    if (!action || !["approved", "sending"].includes(action.status)) return;
    const timer = window.setInterval(() => {
      void fetchOutreachStatus(action.id).then((next) => {
        setAction((current) => current ? { ...current, ...next } : current);
      }).catch(() => undefined);
    }, 3_000);
    return () => window.clearInterval(timer);
  }, [action]);

  const generate = async () => {
    if (endpointId === null) return;
    setBusy(true); setError("");
    try {
      const next = await generateOutreachAction(customerId, {
        customerEndpointId: endpointId,
        turnId,
        instruction,
      });
      setAction(next);
      setSubject(next.subject ?? next.protected_subject);
      setBody(next.body ?? next.protected_body);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Draft generation failed.");
    } finally { setBusy(false); }
  };

  const save = async () => {
    if (!action) return;
    setBusy(true); setError("");
    try {
      const next = await updateOutreachAction(action.id, { subject, body });
      setAction(next);
      setSubject(next.subject ?? next.protected_subject);
      setBody(next.body ?? next.protected_body);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Draft update failed.");
    } finally { setBusy(false); }
  };

  const transition = async (operation: "submit" | "approve" | "reject" | "cancel") => {
    if (!action) return;
    setBusy(true); setError("");
    try { setAction(await transitionOutreachAction(action.id, operation)); }
    catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Outreach transition failed."); }
    finally { setBusy(false); }
  };

  if (!open) {
    return <button className="fb-btn fb-btn-solid" type="button" onClick={() => setOpen(true)}>Draft email response</button>;
  }

  return <section className="fb-callout" aria-label="Governed email composer" style={{ marginTop: ".8rem" }}>
    <div style={{ display: "flex", justifyContent: "space-between", gap: ".75rem", alignItems: "center" }}>
      <strong>Governed email response</strong>
      <button className="fb-link-toggle" type="button" onClick={() => setOpen(false)}>Close</button>
    </div>
    <p className="fb-fine">The receiver comes from this customer’s verified endpoint. The AI sees protected evidence only; approval is separate from drafting.</p>
    {error && <div className="fb-callout" role="alert">{error}</div>}
    {!action && <>
      <label className="fb-fine" htmlFor={`outreach-endpoint-${turnId}`}>Receiver</label>
      <select id={`outreach-endpoint-${turnId}`} className="fb-input" value={endpointId ?? ""} onChange={(event) => setEndpointId(Number(event.target.value))} style={{ display: "block", width: "100%", margin: ".35rem 0 .7rem" }}>
        {!endpoints.length && <option value="">No verified email endpoint</option>}
        {endpoints.map((endpoint) => <option key={endpoint.id} value={endpoint.id}>{endpoint.authorized_value ?? endpoint.masked_value}</option>)}
      </select>
      <label className="fb-fine" htmlFor={`outreach-instruction-${turnId}`}>Draft instruction</label>
      <textarea id={`outreach-instruction-${turnId}`} className="fb-input" rows={2} value={instruction} onChange={(event) => setInstruction(event.target.value)} style={{ display: "block", width: "100%", margin: ".35rem 0 .7rem" }} />
      <button className="fb-btn fb-btn-solid" type="button" disabled={busy || endpointId === null || !instruction.trim()} onClick={() => void generate()}>{busy ? "Generating protected draft…" : "Generate email draft"}</button>
    </>}
    {action && <>
      <div className="fb-fine" style={{ marginBottom: ".5rem" }}>To: {action.recipient ?? "Protected endpoint"} · {action.status.replaceAll("_", " ")}{action.generation_mode ? ` · ${action.generation_mode}` : ""}</div>
      <input className="fb-input" aria-label="Email subject" value={subject} disabled={action.status !== "draft"} onChange={(event) => setSubject(event.target.value)} style={{ display: "block", width: "100%", marginBottom: ".6rem" }} />
      <textarea className="fb-input" aria-label="Email body" rows={8} value={body} disabled={action.status !== "draft"} onChange={(event) => setBody(event.target.value)} style={{ display: "block", width: "100%", marginBottom: ".6rem" }} />
      <div style={{ display: "flex", gap: ".5rem", flexWrap: "wrap" }}>
        {action.status === "draft" && <><button className="fb-btn fb-btn-outline" type="button" disabled={busy || !subject.trim() || !body.trim()} onClick={() => void save()}>Save changes</button><button className="fb-btn fb-btn-solid" type="button" disabled={busy || !subject.trim() || !body.trim()} onClick={() => void transition("submit")}>Submit for approval</button><button className="fb-btn fb-btn-outline" type="button" disabled={busy} onClick={() => void transition("cancel")}>Cancel draft</button></>}
        {action.status === "pending_approval" && role === "owner_director" && <><button className="fb-btn fb-btn-solid" type="button" disabled={busy} onClick={() => void transition("approve")}>Approve and queue email</button><button className="fb-btn fb-btn-outline" type="button" disabled={busy} onClick={() => void transition("reject")}>Reject</button></>}
      </div>
      {action.status === "pending_approval" && role !== "owner_director" && <div className="fb-fine">Waiting for owner approval. Nothing has been sent.</div>}
      {["approved", "sending"].includes(action.status) && <div className="fb-fine">Queued for the email worker. This card will update automatically.</div>}
      {action.status === "sent" && <div className="fb-fine">Email sent successfully.</div>}
      {action.status === "replied" && <div className="fb-fine">A correlated customer reply has been ingested.</div>}
      {action.failure_code && <div className="fb-fine">Delivery issue: {action.failure_code}</div>}
    </>}
  </section>;
}
