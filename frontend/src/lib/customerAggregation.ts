import type { EInvoiceApiRecord } from "../api/client";

export function formatRm(total: number): string {
  return "RM " + total.toLocaleString("en-MY", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function toAmount(value: string): number {
  return Number(value) || 0;
}

export function isOutstanding(r: EInvoiceApiRecord): boolean {
  return r.status === "validated" && !r.paid_at;
}

export function isOverdue(r: EInvoiceApiRecord, today: Date): boolean {
  return isOutstanding(r) && !!r.due_date && new Date(r.due_date) < today;
}

export type PriorityTier = "urgent" | "high" | "monitoring" | "healthy";

// Simplified stand-in for the full spec's cross-source attention score —
// invoicing data (specifically, days overdue) is the only real signal
// available without backend work, so the tiers are grounded in that alone.
export function priorityTier(overdueDays: number, hasOverdue: boolean): PriorityTier {
  if (!hasOverdue) return "healthy";
  if (overdueDays > 60) return "urgent";
  if (overdueDays > 30) return "high";
  return "monitoring";
}

export interface CustomerAggregate {
  key: string;
  name: string;
  invoices: EInvoiceApiRecord[];
  outstandingTotal: number;
  overdueTotal: number;
  oldestOverdueDate: string | null;
  oldestOverdueDays: number;
  blockerCount: number;
  tier: PriorityTier;
}

export function buildCustomers(records: EInvoiceApiRecord[], blockerIds: Set<number>): CustomerAggregate[] {
  const today = new Date();
  const groups = new Map<string, EInvoiceApiRecord[]>();
  for (const r of records) {
    const key = r.buyer_customer_id != null ? `id:${r.buyer_customer_id}` : `name:${(r.buyer_name ?? "Unknown buyer").trim().toLowerCase()}`;
    const bucket = groups.get(key);
    if (bucket) bucket.push(r); else groups.set(key, [r]);
  }
  const out: CustomerAggregate[] = [];
  for (const [key, invoices] of groups) {
    const name = invoices[0].buyer_name?.trim() || "Unknown buyer";
    const outstandingTotal = invoices.filter(isOutstanding).reduce((sum, r) => sum + toAmount(r.total_amount), 0);
    const overdue = invoices.filter((r) => isOverdue(r, today));
    const overdueTotal = overdue.reduce((sum, r) => sum + toAmount(r.total_amount), 0);
    let oldestOverdueDate: string | null = null;
    for (const r of overdue) {
      if (r.due_date && (!oldestOverdueDate || r.due_date < oldestOverdueDate)) oldestOverdueDate = r.due_date;
    }
    const oldestOverdueDays = oldestOverdueDate
      ? Math.floor((today.getTime() - new Date(oldestOverdueDate).getTime()) / 86400000)
      : 0;
    const blockerCount = invoices.filter((r) => blockerIds.has(r.id)).length;
    out.push({
      key, name, invoices, outstandingTotal, overdueTotal, oldestOverdueDate, oldestOverdueDays, blockerCount,
      tier: priorityTier(oldestOverdueDays, overdue.length > 0),
    });
  }
  const tierRank: Record<PriorityTier, number> = { urgent: 0, high: 1, monitoring: 2, healthy: 3 };
  return out.sort((a, b) =>
    tierRank[a.tier] - tierRank[b.tier]
    || b.oldestOverdueDays - a.oldestOverdueDays
    || b.overdueTotal - a.overdueTotal
    || b.outstandingTotal - a.outstandingTotal);
}
