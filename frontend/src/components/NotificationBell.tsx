import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useAppState } from "../lib/appState";
import { PERSONAS } from "../lib/personas";
import { disclosureTitle, humanize } from "../lib/auditFormatting";
import { getReadIds, markManyRead, markRead } from "../lib/notificationReads";
import {
  fetchAuditLog,
  fetchEinvoiceReadiness,
  fetchWorkflowAudit,
  type AuditEntry,
  type WorkflowAuditEntry,
} from "../api/client";

type NotificationCategory = "invoicing" | "audit" | "approvals";

interface NotificationItem {
  id: string;
  category: NotificationCategory;
  title: string;
  detail: string;
  time: string | null;
  onOpen: () => void;
}

const CATEGORY_ICON: Record<NotificationCategory, ReactNode> = {
  invoicing: <path d="M6 2h9l3 3v17H6z M9 8h6M9 12h6M9 16h4" />,
  audit: <path d="M12 3 20 6.5v5.3c0 4.7-3.2 8.9-8 10.2-4.8-1.3-8-5.5-8-10.2V6.5z" />,
  approvals: <path d="M9 12l2 2 4-4M12 3l8 4v5c0 4.5-3.2 8.5-8 10-4.8-1.5-8-5.5-8-10V7z" />,
};

function relativeTime(iso: string | null): string {
  if (!iso) return "";
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} hr ago`;
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

// Aggregates real signals already fetched elsewhere in the app (e-invoice
// readiness issues, the hash-chained audit log, pending approvals) into one
// feed instead of the bell being a bare shortcut to Workflows — every item
// here links to the real record it's about, nothing here is synthesized.
// Read state is tracked client-side only (see lib/notificationReads.ts),
// the same disclosed, session-local pattern already used for "Recent"
// conversations on the Ask page.
export function NotificationBell() {
  const { show, showEinvoiceDetail, askRole, approvalsCount } = useAppState();
  const capabilities = PERSONAS[askRole].capabilities;
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [loadedOnce, setLoadedOnce] = useState(false);
  const [tab, setTab] = useState<"all" | "unread">("all");
  const [readIds, setReadIds] = useState<Set<string>>(() => getReadIds());

  useEffect(() => {
    let active = true;
    const load = async () => {
      const collected: NotificationItem[] = [];

      try {
        const readiness = await fetchEinvoiceReadiness();
        readiness.critical.records.slice(0, 3).forEach((record) => {
          collected.push({
            id: `inv-${record.id}`,
            category: "invoicing",
            title: `${record.supplier_name} needs attention`,
            detail: record.readiness_reason || "Missing required MyInvois fields.",
            time: record.created_at,
            onOpen: () => showEinvoiceDetail(`real-${record.id}`),
          });
        });
      } catch {
        // Readiness endpoint unreachable — just don't surface invoicing items this round.
      }

      if (capabilities.viewAudit) {
        try {
          const [disclosures, workflow] = await Promise.all([fetchAuditLog(), fetchWorkflowAudit()]);
          const disclosureItems: NotificationItem[] = disclosures.entries.map((entry: AuditEntry) => ({
            id: `audit-d-${entry.id}`,
            category: "audit",
            title: disclosureTitle(entry.token, entry.authorized),
            detail: `${humanize(entry.role)} · ${entry.authorized ? "Allowed" : "Denied"}`,
            time: entry.ts,
            onOpen: () => show("audit"),
          }));
          const workflowItems: NotificationItem[] = workflow.entries.map((entry: WorkflowAuditEntry) => ({
            id: `audit-w-${entry.id}`,
            category: "audit",
            title: humanize(entry.event_type),
            detail: humanize(entry.actor_role),
            time: entry.created_at,
            onOpen: () => show("audit"),
          }));
          collected.push(
            ...[...disclosureItems, ...workflowItems]
              .sort((a, b) => new Date(b.time ?? 0).getTime() - new Date(a.time ?? 0).getTime())
              .slice(0, 3),
          );
        } catch {
          // Audit endpoints unreachable — skip audit items this round.
        }
      }

      if (!active) return;
      setItems(collected.sort((a, b) => new Date(b.time ?? 0).getTime() - new Date(a.time ?? 0).getTime()));
      setLoadedOnce(true);
    };
    void load();
    const timer = window.setInterval(load, 60000);
    return () => { active = false; window.clearInterval(timer); };
  }, [askRole, capabilities.viewAudit, show, showEinvoiceDetail]);

  const allItems = useMemo<NotificationItem[]>(() => {
    const list = [...items];
    if (approvalsCount > 0) {
      list.unshift({
        id: "approvals-summary",
        category: "approvals",
        title: `${approvalsCount} item${approvalsCount === 1 ? "" : "s"} waiting for review`,
        detail: "Recommendations and outreach drafts in Workflows.",
        time: null,
        onOpen: () => show("approvals"),
      });
    }
    return list;
  }, [items, approvalsCount, show]);

  const unreadCount = allItems.filter((item) => !readIds.has(item.id)).length;
  const visibleItems = tab === "unread" ? allItems.filter((item) => !readIds.has(item.id)) : allItems;

  const openItem = (item: NotificationItem) => {
    setOpen(false);
    markRead(item.id);
    setReadIds(getReadIds());
    item.onOpen();
  };

  const markAllRead = () => {
    markManyRead(allItems.map((item) => item.id));
    setReadIds(getReadIds());
  };

  return (
    <div
      className="fb-notif"
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node)) setOpen(false);
      }}
    >
      <button
        className="fb-topbar-icon-btn"
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="true"
        aria-expanded={open}
        title="Notifications"
        aria-label="Notifications"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.73 21a2 2 0 0 1-3.46 0" /></svg>
        {unreadCount > 0 && <span className="fb-nav-badge fb-topbar-badge">{unreadCount > 9 ? "9+" : unreadCount}</span>}
      </button>
      {open && (
        <div className="fb-notif-panel" role="menu">
          <div className="fb-notif-head">
            <span className="fb-notif-head-title">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.73 21a2 2 0 0 1-3.46 0" /></svg>
              Notifications
              {unreadCount > 0 && <span className="fb-notif-head-badge">{unreadCount} new</span>}
            </span>
            <button className="fb-notif-mark-all" type="button" onClick={markAllRead} disabled={unreadCount === 0}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m3 12 4 4L18 5" /><path d="m9 16 2 2L20 8" /></svg>
              Mark all read
            </button>
          </div>

          <div className="fb-notif-tabs" role="tablist">
            <button type="button" role="tab" aria-selected={tab === "all"} className={tab === "all" ? "is-current" : ""} onClick={() => setTab("all")}>All ({allItems.length})</button>
            <button type="button" role="tab" aria-selected={tab === "unread"} className={tab === "unread" ? "is-current" : ""} onClick={() => setTab("unread")}>Unread ({unreadCount})</button>
          </div>

          <div className="fb-notif-list">
            {visibleItems.map((item) => (
              <button key={item.id} className={"fb-notif-item" + (readIds.has(item.id) ? "" : " is-unread")} type="button" role="menuitem" onClick={() => openItem(item)}>
                <span className={"fb-notif-item-icon is-" + item.category} aria-hidden="true">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{CATEGORY_ICON[item.category]}</svg>
                </span>
                <span className="fb-notif-item-body">
                  <span className="fb-notif-item-row">
                    <strong>{item.title}</strong>
                    <span className="fb-notif-item-time">
                      {!readIds.has(item.id) && <span className="fb-notif-dot" aria-hidden="true" />}
                      {relativeTime(item.time)}
                    </span>
                  </span>
                  <span className="fb-notif-item-detail">{item.detail}</span>
                </span>
              </button>
            ))}
            {loadedOnce && visibleItems.length === 0 && (
              <div className="fb-notif-empty">{tab === "unread" ? "No unread notifications." : "You're all caught up."}</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
