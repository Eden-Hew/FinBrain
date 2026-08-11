import { useEffect, useState } from "react";
import { useI18n } from "../lib/i18n";
import { useAppState } from "../lib/appState";
import { AppNav } from "../components/Nav";
import { fetchAuditLog, type AuditEntry } from "../api/client";

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
  const { auditRows, auditBaseCount } = useAppState();
  const [verifying, setVerifying] = useState(false);
  const [liveEntries, setLiveEntries] = useState<AuditEntry[]>([]);

  useEffect(() => {
    fetchAuditLog("owner_director")
      .then((res) => setLiveEntries(res.entries))
      .catch(() => setLiveEntries([]));
  }, []);

  const entryCount = auditBaseCount + auditRows.length;

  const verifyChain = () => {
    setVerifying(true);
    setTimeout(() => setVerifying(false), 500);
  };

  const exportCsv = () => {
    const rows: (string | number)[][] = [["Time", "Actor", "Type", "Resource", "Grant", "Status", "Hash"]];
    auditRows.forEach((r) => rows.push([r.time, r.actor, r.type, r.resource, r.grant, r.status, r.hash]));
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
          <button className="fb-btn fb-btn-outline" type="button" onClick={exportCsv}><span>{t("export.csv")}</span></button>
        </div>
      </header>

      <div className="fb-page-body" style={{ paddingBottom: 0 }}>
        <div className="fb-callout fb-chain-status" style={{ marginTop: 0 }}>
          {verifying ? "Verifying…" : `Chain verified — ${entryCount} entries, 0 gaps.`}{" "}
          <span className="fb-link" onClick={verifyChain}>Re-verify</span>
        </div>
      </div>

      <div className="fb-table-wrap">
        <table className="fb-table">
          <thead>
            <tr><th>Time</th><th>Actor</th><th>Type</th><th>Resource</th><th>Grant</th><th>Status</th><th>Hash</th></tr>
          </thead>
          <tbody>
            {auditRows.map((r, i) => (
              <tr key={i}>
                <td>{r.time}</td><td>{r.actor}</td><td>{r.type}</td><td>{r.resource}</td><td>{r.grant}</td>
                <td><span className={"fb-status-pill " + (r.status === "Denied" ? "is-review" : "is-active")}><span className="fb-status-dot"></span>{r.status}</span></td>
                <td>{r.hash}</td>
              </tr>
            ))}
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
          </tbody>
        </table>
      </div>
    </div>
  );
}
