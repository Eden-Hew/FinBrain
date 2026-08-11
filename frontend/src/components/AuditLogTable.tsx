import { useEffect, useState } from "react";
import { fetchAuditLog, type AuditResponse, type Role } from "../api/client";

export function AuditLogTable({ role, refreshKey }: { role: Role; refreshKey: number }) {
  const [audit, setAudit] = useState<AuditResponse | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (role !== "compliance") return;
    fetchAuditLog(role)
      .then((response) => {
        setAudit(response);
        setError("");
      })
      .catch((reason: Error) => setError(reason.message));
  }, [role, refreshKey]);

  return (
    <section className="card audit-card">
      <div className="card-heading">
        <div><span className="eyebrow">Disclosure history</span><h2>Audit trail</h2></div>
        {audit && <span className={audit.chain_valid ? "chain-valid" : "chain-invalid"}>{audit.chain_valid ? "Chain verified" : "Chain invalid"}</span>}
      </div>
      {role !== "compliance" && <div className="locked"><span>⌁</span><p>Switch to the compliance role to inspect disclosure events.</p></div>}
      {error && <p className="error-text">{error}</p>}
      {role === "compliance" && audit && audit.entries.length === 0 && <p className="muted">No token disclosures have been recorded.</p>}
      {role === "compliance" && audit && audit.entries.length > 0 && (
        <div className="table-wrap"><table>
          <thead><tr><th>Role</th><th>Protected token</th><th>Decision</th><th>Time</th></tr></thead>
          <tbody>{audit.entries.map((entry) => (
            <tr key={entry.id}>
              <td>{entry.role.replaceAll("_", " ")}</td><td><code>{entry.token}</code></td>
              <td><span className={entry.authorized ? "allowed" : "denied"}>{entry.authorized ? "Allowed" : "Denied"}</span></td>
              <td>{new Date(entry.ts).toLocaleString()}</td>
            </tr>
          ))}</tbody>
        </table></div>
      )}
    </section>
  );
}
