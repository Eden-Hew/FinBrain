import { useEffect, useState } from "react";
import { useI18n } from "../lib/i18n";
import { AppNav } from "../components/Nav";
import { PersonaSelector } from "../components/PersonaSelector";
import { useAppState } from "../lib/appState";
import { PERSONAS } from "../lib/personas";
import {
  fetchAuditLog,
  fetchWorkflowAudit,
  type AuditEntry,
  type WorkflowAuditEntry,
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

export default function Audit() {
  const { t } = useI18n();
  const { askRole } = useAppState();
  const canViewAudit = PERSONAS[askRole].capabilities.viewAudit;
  const [verifying, setVerifying] = useState(false);
  const [liveEntries, setLiveEntries] = useState<AuditEntry[]>([]);
  const [workflowEntries, setWorkflowEntries] = useState<WorkflowAuditEntry[]>([]);
  const [chainsValid, setChainsValid] = useState<boolean | null>(null);

  const load = async () => {
    if (!canViewAudit) throw new Error("Compliance reviewer persona required");
    const [disclosures, workflow] = await Promise.all([
      fetchAuditLog(askRole),
      fetchWorkflowAudit(askRole),
    ]);
    setLiveEntries(disclosures.entries);
    setWorkflowEntries(workflow.entries);
    setChainsValid(disclosures.chain_valid && workflow.chain_valid);
  };

  useEffect(() => {
    let active = true;
    const initialLoad = async () => {
      try {
        if (!canViewAudit) {
          if (active) {
            setLiveEntries([]);
            setWorkflowEntries([]);
            setChainsValid(null);
          }
          return;
        }
        const [disclosures, workflow] = await Promise.all([
          fetchAuditLog(askRole),
          fetchWorkflowAudit(askRole),
        ]);
        if (!active) return;
        setLiveEntries(disclosures.entries);
        setWorkflowEntries(workflow.entries);
        setChainsValid(disclosures.chain_valid && workflow.chain_valid);
      } catch {
        if (active) setChainsValid(null);
      }
    };
    void initialLoad();
    return () => { active = false; };
  }, [askRole, canViewAudit]);

  const entryCount = liveEntries.length + workflowEntries.length;

  const verifyChain = async () => {
    setVerifying(true);
    try {
      await load();
    } finally {
      setVerifying(false);
    }
  };

  const exportCsv = () => {
    const rows: (string | number)[][] = [["Time", "Actor", "Type", "Resource", "Grant", "Status", "Hash"]];
    liveEntries.forEach((entry) => rows.push([
      entry.ts,
      entry.role,
      "Token disclosure",
      entry.token,
      entry.role,
      entry.authorized ? "Allowed" : "Denied",
      entry.query_hash,
    ]));
    workflowEntries.forEach((entry) => rows.push([
      entry.created_at,
      entry.actor_role,
      entry.event_type,
      `${entry.resource_type}:${entry.resource_id}`,
      entry.actor_role,
      "Recorded",
      entry.actor_ref,
    ]));
    downloadCsv("finbrain-audit-trail.csv", rows);
  };

  return (
    <div className="fb-root">
      <AppNav current="audit" />

      <header className="fb-app-header">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "1rem", flexWrap: "wrap" }}>
          <div>
            <h1>{t("audit.title")}</h1>
            <p>{t("audit.desc")}</p>
          </div>
          <button className="fb-btn fb-btn-outline" type="button" onClick={exportCsv} disabled={!canViewAudit}><span>{t("export.csv")}</span></button>
        </div>
      </header>

      <div className="fb-page-body" style={{ paddingBottom: 0 }}>
        <PersonaSelector />
        {!canViewAudit && (
          <div className="fb-callout">Select the Compliance reviewer demo persona to view protected audit chains.</div>
        )}
        <div className="fb-callout fb-chain-status" style={{ marginTop: 0 }}>
          {verifying
            ? "Verifying…"
            : chainsValid === true
              ? `Chains verified — ${entryCount} live entries, 0 gaps.`
              : chainsValid === false
                ? "Audit chain verification failed."
                : "Live audit data is unavailable."}{" "}
          <span className="fb-link" onClick={() => void verifyChain()}>Re-verify</span>
        </div>
      </div>

      <div className="fb-table-wrap">
        <table className="fb-table">
          <thead>
            <tr><th>Time</th><th>Actor</th><th>Type</th><th>Resource</th><th>Grant</th><th>Status</th><th>Hash</th></tr>
          </thead>
          <tbody>
            {liveEntries.map((e) => (
              <tr key={"live-" + e.id}>
                <td>{new Date(e.ts).toLocaleTimeString()}</td>
                <td>{e.role}</td>
                <td>Live Chat Query</td>
                <td>{e.query_hash.slice(0, 12)}…</td>
                <td>{e.role}</td>
                <td><span className={"fb-status-pill " + (!e.authorized ? "is-review" : "is-active")}><span className="fb-status-dot"></span>{e.authorized ? "Allowed" : "Denied"}</span></td>
                <td>{e.query_hash.slice(0, 8)}…</td>
              </tr>
            ))}
            {workflowEntries.map((entry) => (
              <tr key={`workflow-${entry.id}`}>
                <td>{new Date(entry.created_at).toLocaleTimeString()}</td>
                <td>{entry.actor_role}</td>
                <td>{entry.event_type.replaceAll("_", " ")}</td>
                <td>{entry.resource_type}:{entry.resource_id}</td>
                <td>{entry.actor_role}</td>
                <td><span className="fb-status-pill is-active"><span className="fb-status-dot"></span>Recorded</span></td>
                <td>{entry.actor_ref.slice(0, 8)}…</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
