// Mirrors backend/app/security/tokenize.py's LABEL_TOKEN_MAP and AMOUNT_BANDS.
// Renders masked-value tokens (e.g. "PERSON_a1b2c3d4e5") as a small badge
// instead of raw text, so a masked value reads as an intentional privacy
// feature rather than corrupted data.

const TOKEN_LABELS: Record<string, string> = {
  PERSON: "Name",
  NRIC: "ID number",
  PHONE: "Phone",
  EMAIL: "Email",
  BANKACC: "Bank account",
  CARD: "Card number",
  ADDR: "Address",
  ORG: "Company",
  MISC: "Masked value",
};

const AMOUNT_BANDS = [500, 1000, 2500, 5000, 10000, 25000, 50000, 100000];

function amountBandLabel(index: number): string {
  if (index <= 0) return "under RM 500";
  if (index >= AMOUNT_BANDS.length) return `RM ${AMOUNT_BANDS[AMOUNT_BANDS.length - 1].toLocaleString()}+`;
  return `RM ${AMOUNT_BANDS[index - 1].toLocaleString()}–${AMOUNT_BANDS[index].toLocaleString()}`;
}

const MASK_ICON = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="4" y="10" width="16" height="10" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" />
  </svg>
);

export function MaskedText({ text }: { text: string }) {
  const re = /\b(PERSON|NRIC|PHONE|EMAIL|BANKACC|CARD|ADDR|ORG|MISC)_[0-9a-f]{6,12}\b|\bAMOUNT_BAND_(\d+)_[0-9a-f]{6,12}\b/g;
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let key = 0;

  while ((match = re.exec(text)) !== null) {
    if (match.index > lastIndex) parts.push(text.slice(lastIndex, match.index));
    const label = match[1] ? (TOKEN_LABELS[match[1]] ?? "Masked value") : amountBandLabel(Number(match[2]));
    parts.push(
      <span className="fb-mask-badge" key={key++}>
        {MASK_ICON}
        {label}
      </span>,
    );
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < text.length) parts.push(text.slice(lastIndex));
  return <>{parts}</>;
}
