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
