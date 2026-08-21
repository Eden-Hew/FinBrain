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

// Backend fallback for a customer whose display name never resolved (e.g. "[person — restricted]") —
// distinct from the PERSON_xxxxx mask tokens MaskedText handles, so it needs its own check.
export function isPlaceholderName(name: string): boolean {
  return /^\[.*\]$/.test(name.trim());
}

// Presentational-only casing fix so "GOHSHENGKAI" / "xiao ming" / "Meranti Trading" don't
// look like three different conventions side by side — never touches the underlying data.
export function displayCase(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return trimmed;
  const isAllUpper = trimmed === trimmed.toUpperCase() && trimmed !== trimmed.toLowerCase();
  const isAllLower = trimmed === trimmed.toLowerCase() && trimmed !== trimmed.toUpperCase();
  if (!isAllUpper && !isAllLower) return trimmed;
  return trimmed
    .toLowerCase()
    .split(" ")
    .map((word) => (word ? word.charAt(0).toUpperCase() + word.slice(1) : word))
    .join(" ");
}
