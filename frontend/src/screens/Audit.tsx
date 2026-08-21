import { useEffect, useMemo, useState } from "react";
import { useI18n } from "../lib/i18n";
import { Sidebar, AppTopBar } from "../components/Nav";
import { PersonaSelector } from "../components/PersonaSelector";
import { useAppState } from "../lib/appState";
import { PERSONAS } from "../lib/personas";
import { EmptyState } from "../components/EmptyState";
import { MaskedText } from "../components/MaskedText";
import { disclosureTitle, humanize } from "../lib/auditFormatting";
import {
  fetchAuditLog,
  fetchWorkflowAudit,
  type AuditEntry,
  type WorkflowAuditEntry,
} from "../api/client";

type AuditFilter = "all" | "disclosure" | "workflow";

type DisplayEntry = {
  key: string;
  stream: Exclude<AuditFilter, "all">;
  time: string;
  title: string;
  actor: string;
  resource: string;
  status: string;
  needsReview: boolean;
  referenceLabel: string;
  reference: string;
  entryHash: string;
  previousHash: string;
  payload?: Record<string, unknown>;
};

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

function workflowReference(entry: WorkflowAuditEntry) {
  const queryReference = entry.event_payload.origin_query_hash ?? entry.event_payload.query_hash;
  return typeof queryReference === "string" && queryReference ? queryReference : entry.actor_ref;
}

function shortHash(value: string) {
  if (!value) return "Genesis entry";
  return value.length > 24 ? `${value.slice(0, 12)}…${value.slice(-8)}` : value;
}

function dayLabel(iso: string) {
  const date = new Date(iso);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  const sameDay = (a: Date, b: Date) => a.toDateString() === b.toDateString();
  if (sameDay(date, today)) return "Today";
  if (sameDay(date, yesterday)) return "Yesterday";
  return date.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });
}

function InspectChainData({ entry }: { entry: DisplayEntry }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="fb-audit-inspect">
      <button className="fb-link-toggle" type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        <span className={"fb-link-toggle-caret" + (open ? " is-open" : "")}>▸</span>
        Inspect full chain data
      </button>
      {open && (
        <dl>
          <div><dt>{entry.referenceLabel}</dt><dd><code>{entry.reference || "Not recorded"}</code></dd></div>
          <div><dt>Previous entry hash</dt><dd><code>{entry.previousHash || "Genesis entry — no previous hash"}</code></dd></div>
          <div><dt>Entry hash</dt><dd><code>{entry.entryHash}</code></dd></div>
          {entry.payload && Object.keys(entry.payload).length > 0 && (
            <div><dt>Workflow payload</dt><dd><code>{JSON.stringify(entry.payload, null, 2)}</code></dd></div>
          )}
        </dl>
      )}
    </div>
  );
}

export default function Audit() {
  const { t } = useI18n();
  const { askRole } = useAppState();
  const canViewAudit = PERSONAS[askRole].capabilities.viewAudit;
  const [verifying, setVerifying] = useState(false);
  const [liveEntries, setLiveEntries] = useState<AuditEntry[]>([]);
  const [workflowEntries, setWorkflowEntries] = useState<WorkflowAuditEntry[]>([]);
  const [disclosureChainValid, setDisclosureChainValid] = useState<boolean | null>(null);
  const [workflowChainValid, setWorkflowChainValid] = useState<boolean | null>(null);
  const [filter, setFilter] = useState<AuditFilter>("all");
  const [actorSearch, setActorSearch] = useState("");
  const [loadError, setLoadError] = useState("");

  const load = async () => {
    if (!canViewAudit) throw new Error("Compliance reviewer persona required");
    const [disclosures, workflow] = await Promise.all([
      fetchAuditLog(),
      fetchWorkflowAudit(),
    ]);
    setLiveEntries(disclosures.entries);
    setWorkflowEntries(workflow.entries);
    setDisclosureChainValid(disclosures.chain_valid);
    setWorkflowChainValid(workflow.chain_valid);
    setLoadError("");
  };

  useEffect(() => {
    let active = true;
    const initialLoad = async () => {
      if (!canViewAudit) {
        if (active) {
          setLiveEntries([]);
          setWorkflowEntries([]);
          setDisclosureChainValid(null);
          setWorkflowChainValid(null);
          setLoadError("");
        }
        return;
      }
      try {
        const [disclosures, workflow] = await Promise.all([
          fetchAuditLog(),
          fetchWorkflowAudit(),
        ]);
        if (!active) return;
        setLiveEntries(disclosures.entries);
        setWorkflowEntries(workflow.entries);
        setDisclosureChainValid(disclosures.chain_valid);
        setWorkflowChainValid(workflow.chain_valid);
        setLoadError("");
      } catch {
        if (active) {
          setDisclosureChainValid(null);
          setWorkflowChainValid(null);
          setLoadError("Audit data could not be loaded. Check that the backend is running, then retry verification.");
        }
      }
    };
    void initialLoad();
    return () => { active = false; };
  }, [askRole, canViewAudit]);

  const entries = useMemo<DisplayEntry[]>(() => {
    const disclosureRows: DisplayEntry[] = liveEntries.map((entry) => ({
      key: `disclosure-${entry.id}`,
      stream: "disclosure",
      time: entry.ts,
      title: disclosureTitle(entry.token, entry.authorized),
      actor: entry.role,
      resource: entry.token,
      status: entry.authorized ? "Allowed" : "Denied",
      needsReview: !entry.authorized,
      referenceLabel: "Query reference",
      reference: entry.query_hash,
      entryHash: entry.entry_hash,
      previousHash: entry.previous_hash,
    }));
    const workflowRows: DisplayEntry[] = workflowEntries.map((entry) => ({
      key: `workflow-${entry.id}`,
      stream: "workflow",
      time: entry.created_at,
      title: humanize(entry.event_type),
      actor: entry.actor_role,
      resource: `${entry.resource_type}:${entry.resource_id}`,
      status: "Recorded",
      needsReview: false,
      referenceLabel: entry.event_payload.origin_query_hash || entry.event_payload.query_hash
        ? "Origin query reference"
        : "Workflow reference",
      reference: workflowReference(entry),
      entryHash: entry.entry_hash,
      previousHash: entry.previous_hash,
      payload: entry.event_payload,
    }));
    return [...disclosureRows, ...workflowRows]
      .filter((entry) => filter === "all" || entry.stream === filter)
      .filter((entry) => !actorSearch.trim() || entry.actor.toLowerCase().includes(actorSearch.trim().toLowerCase()))
      .sort((a, b) => new Date(b.time).getTime() - new Date(a.time).getTime());
  }, [filter, actorSearch, liveEntries, workflowEntries]);

  const PAGE_SIZE = 10;
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  // Reset pagination when the filter changes, computed during render (React's
  // documented "adjusting state when a prop changes" pattern) rather than in an
  // effect, so it doesn't cost an extra commit-then-reset render pass.
  const pageResetKey = `${filter}:${actorSearch}`;
  const [prevPageResetKey, setPrevPageResetKey] = useState(pageResetKey);
  if (pageResetKey !== prevPageResetKey) {
    setPrevPageResetKey(pageResetKey);
    setVisibleCount(PAGE_SIZE);
  }

  const visibleEntries = useMemo(() => entries.slice(0, visibleCount), [entries, visibleCount]);
  const remaining = entries.length - visibleEntries.length;

  const groupedEntries = useMemo(() => {
    const groups: { label: string; rows: DisplayEntry[] }[] = [];
    for (const entry of visibleEntries) {
      const label = dayLabel(entry.time);
      const last = groups[groups.length - 1];
      if (last && last.label === label) last.rows.push(entry);
      else groups.push({ label, rows: [entry] });
    }
    return groups;
  }, [visibleEntries]);

  const verifyChain = async () => {
    setVerifying(true);
    try {
      await load();
    } catch {
      setLoadError("Verification could not reach the audit service. Check the backend and try again.");
    } finally {
      setVerifying(false);
    }
  };

  const exportCsv = () => {
    const rows: (string | number)[][] = [["Time", "Stream", "Actor", "Event", "Resource", "Status", "Reference", "Previous hash", "Entry hash"]];
    liveEntries.forEach((entry) => rows.push([
      entry.ts, "Disclosure decision", entry.role, "Token disclosure", entry.token,
      entry.authorized ? "Allowed" : "Denied", entry.query_hash, entry.previous_hash, entry.entry_hash,
    ]));
    workflowEntries.forEach((entry) => rows.push([
      entry.created_at, "Workflow event", entry.actor_role, entry.event_type,
      `${entry.resource_type}:${entry.resource_id}`, "Recorded", workflowReference(entry),
      entry.previous_hash, entry.entry_hash,
    ]));
    downloadCsv("finbrain-audit-trail.csv", rows);
  };

  const verificationLabel = (valid: boolean | null) => {
    if (verifying) return "Verifying chain…";
    if (valid === true) return "Valid hash chain";
    if (valid === false) return "Hash chain invalid";
    return "Verification unavailable";
  };

  return (
    <div className="fb-root fb-shell">
      <Sidebar current="audit" />
      <AppTopBar current="audit" />

      <header className="fb-app-header">
        <div className="fb-audit-title-row">
          <div>
            <h1>{t("audit.title")}</h1>
            <p>{t("audit.desc")}</p>
          </div>
          <button className="fb-btn fb-btn-outline" type="button" onClick={exportCsv} disabled={!canViewAudit}>Export audit CSV</button>
        </div>
      </header>

      <main className="fb-audit-main">
        <PersonaSelector />
        {!canViewAudit && (
          <div className="fb-callout">A verified Compliance reviewer account is required to view protected audit chains.</div>
        )}
        {loadError && <div className="fb-audit-error" role="alert">{loadError}</div>}

        <section className="fb-audit-verification" aria-label="Hash-chain verification" aria-live="polite">
          <div className="fb-audit-chain">
            <div>
              <strong>Disclosure decisions</strong>
              <span>{liveEntries.length} access decisions</span>
            </div>
            <span className={`fb-chain-result ${disclosureChainValid === true ? "is-valid" : disclosureChainValid === false ? "is-invalid" : ""}`}>
              {verificationLabel(disclosureChainValid)}
            </span>
          </div>
          <div className="fb-audit-chain">
            <div>
              <strong>Workflow events</strong>
              <span>{workflowEntries.length} process events</span>
            </div>
            <span className={`fb-chain-result ${workflowChainValid === true ? "is-valid" : workflowChainValid === false ? "is-invalid" : ""}`}>
              {verificationLabel(workflowChainValid)}
            </span>
          </div>
          <button className="fb-audit-verify" type="button" onClick={() => void verifyChain()} disabled={!canViewAudit || verifying}>
            {verifying ? "Verifying…" : "Re-verify both chains"}
          </button>
        </section>
        <p className="fb-fine" style={{ margin: "-1.4rem 0 2rem", maxWidth: "70ch" }}>
          Each entry is cryptographically linked to the one before it — if any past record were ever edited or
          deleted, the chain would break and this would turn red immediately.
        </p>

        <section className="fb-audit-events" aria-labelledby="audit-events-title">
          <div className="fb-audit-events-head">
            <div>
              <h2 id="audit-events-title">Audit events</h2>
              <p>Each event exposes its source reference and the real hashes used to verify chain integrity.</p>
            </div>
            <div className="fb-audit-filters" aria-label="Filter audit events">
              {([
                ["all", "All", liveEntries.length + workflowEntries.length],
                ["disclosure", "Disclosure decisions", liveEntries.length],
                ["workflow", "Workflow events", workflowEntries.length],
              ] as const).map(([value, label, count]) => (
                <button
                  key={value}
                  type="button"
                  className={filter === value ? "is-current" : ""}
                  aria-pressed={filter === value}
                  onClick={() => setFilter(value)}
                >
                  {label} <span>{count}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="fb-table-search" style={{ margin: "0 0 1.2rem" }}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" /></svg>
            <input type="text" placeholder="Search by role (e.g. owner_director)…" value={actorSearch} onChange={(event) => setActorSearch(event.target.value)} />
          </div>

          <div className="fb-audit-list">
            {entries.length === 0 && (
              <EmptyState
                icon={<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" /></svg>}
                title={actorSearch.trim() ? "No events match that actor" : "No audit events available"}
                description={actorSearch.trim() ? "Try a different actor name, or clear the search." : "Events for this stream will appear here once they occur."}
                action={actorSearch.trim() ? { label: "Clear search", onClick: () => setActorSearch("") } : undefined}
              />
            )}
            {groupedEntries.map((group) => (
              <div key={group.label}>
                <div className="fb-audit-day-header">{group.label}</div>
                {group.rows.map((entry) => (
                  <article className="fb-audit-entry" key={entry.key}>
                    <div className="fb-audit-entry-main">
                      <div className="fb-audit-entry-title">
                        <span className={`fb-audit-stream is-${entry.stream}`}>
                          {entry.stream === "disclosure" ? "Disclosure" : "Workflow"}
                        </span>
                        <div>
                          <h3>{entry.title}</h3>
                          <p>{humanize(entry.actor)} · <MaskedText text={entry.resource} /></p>
                        </div>
                      </div>
                      <div className="fb-audit-entry-state">
                        <span className={`fb-status-pill ${entry.needsReview ? "is-review" : "is-active"}`}>
                          <span className="fb-status-dot" />{entry.status}
                        </span>
                        <time dateTime={entry.time}>{new Date(entry.time).toLocaleString()}</time>
                      </div>
                    </div>

                    <div className="fb-audit-identifiers">
                      <div>
                        <span>Entry hash</span>
                        <code title={entry.entryHash}>{shortHash(entry.entryHash)}</code>
                      </div>
                    </div>

                    <InspectChainData entry={entry} />
                  </article>
                ))}
              </div>
            ))}
          </div>

          {remaining > 0 && (
            <button className="fb-audit-load-more" type="button" onClick={() => setVisibleCount((v) => v + PAGE_SIZE)}>
              Show {Math.min(remaining, PAGE_SIZE)} more <span>({remaining} remaining)</span>
            </button>
          )}
        </section>
      </main>
    </div>
  );
}
