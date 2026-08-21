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
  const [endpointsLoaded, setEndpointsLoaded] = useState(false);
  const [endpointId, setEndpointId] = useState<number | null>(null);
  const [instruction, setInstruction] = useState(DEFAULT_INSTRUCTION);
  const [action, setAction] = useState<OutreachAction | null>(null);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open || endpointsLoaded) return;
    let active = true;
    void fetchCustomerEndpoints(customerId).then((rows) => {
      if (!active) return;
      const eligible = rows.filter((row) => row.delivery_eligible);
      setEndpoints(rows);
      setEndpointId(eligible[0]?.id ?? null);
      setEndpointsLoaded(true);
    }).catch((requestError) => {
      if (active) {
        setError(requestError instanceof Error
          ? requestError.message
          : "Could not load customer response methods.");
      }
    });
    return () => { active = false; };
  }, [customerId, endpointsLoaded, open]);

  useEffect(() => {
    if (!action || !["approved", "sending"].includes(action.status)) return;
    const timer = window.setInterval(() => {
      void fetchOutreachStatus(action.id).then((next) => {
        setAction((current) => current ? { ...current, ...next } : current);
      }).catch(() => undefined);
    }, 3_000);
    return () => window.clearInterval(timer);
  }, [action]);

  const eligibleEndpoints = endpoints.filter((row) => row.delivery_eligible);
  const emailNeedsVerification = endpoints.some(
    (row) => row.channel === "email" && row.verification_status === "observed",
  );

  const generate = async () => {
    if (endpointId === null) return;
    setBusy(true); setError("");
    try {
      const next = await generateOutreachAction(customerId, {
        customerEndpointId: endpointId,
        turnId,
        instruction,
      });
      if (next.body === null || (next.channel === "email" && next.subject === null)) {
        throw new Error("The authorized response preview is unavailable. Generate the response again.");
      }
      setAction(next);
      setSubject(next.subject ?? "");
      setBody(next.body);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Response generation failed.");
    } finally { setBusy(false); }
  };

  const save = async () => {
    if (!action) return;
    setBusy(true); setError("");
    try {
      const next = await updateOutreachAction(
        action.id,
        action.channel === "email" ? { subject, body } : { body },
      );
      if (next.body === null || (next.channel === "email" && next.subject === null)) {
        throw new Error("The authorized response preview is unavailable. Save the response again.");
      }
      setAction(next);
      setSubject(next.subject ?? "");
      setBody(next.body);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Response update failed.");
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
    return <button className="fb-btn fb-btn-solid" type="button" onClick={() => setOpen(true)}>Respond to customer</button>;
  }

  const draftComplete = action?.channel === "telegram"
    ? Boolean(body.trim())
    : Boolean(subject.trim() && body.trim());

  return <section className="fb-callout" aria-label="Governed customer response composer" style={{ marginTop: ".8rem" }}>
    <div style={{ display: "flex", justifyContent: "space-between", gap: ".75rem", alignItems: "center" }}>
      <strong>Governed customer response</strong>
      <button className="fb-link-toggle" type="button" onClick={() => setOpen(false)}>Close</button>
    </div>
    <p className="fb-fine">The receiver comes from this customer’s verified endpoint. The AI sees protected evidence only; approval is separate from drafting.</p>
    {error && <div className="fb-callout" role="alert">{error}</div>}
    {!action && <>
      <label className="fb-fine" htmlFor={`outreach-endpoint-${turnId}`}>Send via</label>
      <select id={`outreach-endpoint-${turnId}`} className="fb-input" value={endpointId ?? ""} onChange={(event) => setEndpointId(Number(event.target.value))} style={{ display: "block", width: "100%", margin: ".35rem 0" }}>
        {!eligibleEndpoints.length && <option value="">No verified delivery method</option>}
        {eligibleEndpoints.map((endpoint) => <option key={endpoint.id} value={endpoint.id}>{endpoint.display_label}</option>)}
      </select>
      {emailNeedsVerification && <div className="fb-fine" style={{ marginBottom: ".7rem" }}>Email on file — verification required before it can be used.</div>}
      {!emailNeedsVerification && <div style={{ marginBottom: ".7rem" }} />}
      <label className="fb-fine" htmlFor={`outreach-instruction-${turnId}`}>Response instruction</label>
      <textarea id={`outreach-instruction-${turnId}`} className="fb-input" rows={2} value={instruction} onChange={(event) => setInstruction(event.target.value)} style={{ display: "block", width: "100%", margin: ".35rem 0 .7rem" }} />
      <button className="fb-btn fb-btn-solid" type="button" disabled={busy || endpointId === null || !instruction.trim()} onClick={() => void generate()}>{busy ? "Generating protected response…" : "Generate response"}</button>
    </>}
    {action && <>
      <div className="fb-fine" style={{ marginBottom: ".5rem" }}>To: {action.recipient_label ?? action.recipient ?? "Protected endpoint"} · {action.status.replaceAll("_", " ")}{action.generation_mode ? ` · ${action.generation_mode}` : ""}</div>
      {action.channel === "email" && <input className="fb-input" aria-label="Email subject" value={subject} disabled={action.status !== "draft"} onChange={(event) => setSubject(event.target.value)} style={{ display: "block", width: "100%", marginBottom: ".6rem" }} />}
      <textarea className="fb-input" aria-label={action.channel === "telegram" ? "Telegram message" : "Email body"} rows={8} value={body} disabled={action.status !== "draft"} onChange={(event) => setBody(event.target.value)} style={{ display: "block", width: "100%", marginBottom: ".6rem" }} />
      <div style={{ display: "flex", gap: ".5rem", flexWrap: "wrap" }}>
        {action.status === "draft" && <><button className="fb-btn fb-btn-outline" type="button" disabled={busy || !draftComplete} onClick={() => void save()}>Save changes</button><button className="fb-btn fb-btn-solid" type="button" disabled={busy || !draftComplete} onClick={() => void transition("submit")}>Submit for approval</button><button className="fb-btn fb-btn-outline" type="button" disabled={busy} onClick={() => void transition("cancel")}>Cancel draft</button></>}
        {action.status === "pending_approval" && role === "owner_director" && <><button className="fb-btn fb-btn-solid" type="button" disabled={busy} onClick={() => void transition("approve")}>Approve and queue {action.channel === "telegram" ? "Telegram" : "email"}</button><button className="fb-btn fb-btn-outline" type="button" disabled={busy} onClick={() => void transition("reject")}>Reject</button></>}
      </div>
      {action.status === "pending_approval" && role !== "owner_director" && <div className="fb-fine">Waiting for owner approval. Nothing has been sent.</div>}
      {["approved", "sending"].includes(action.status) && <div className="fb-fine">Queued for the {action.channel === "telegram" ? "Telegram" : "email"} worker. This card will update automatically.</div>}
      {action.status === "sent" && <div className="fb-fine">{action.channel === "telegram" ? "Telegram message" : "Email"} sent successfully.</div>}
      {action.status === "replied" && <div className="fb-fine">A correlated customer reply has been ingested.</div>}
      {action.failure_code && <div className="fb-fine">Delivery issue: {action.failure_code}</div>}
    </>}
  </section>;
}
