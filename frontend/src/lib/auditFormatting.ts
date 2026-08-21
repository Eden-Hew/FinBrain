// Generic word-by-word title casing mangles the two branded terms this app
// actually uses elsewhere -- "SOP" (a real acronym, shown as its own type
// badge on Workflows) and "e-Invoice"/"e-Invoicing" (the sidebar nav label) --
// into "Sop" and "Einvoice". Fix those up after the generic pass rather than
// hardcoding every event_type, so unrecognized event types still degrade
// gracefully to plain title case.
export function humanize(value: string) {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
    .replace(/\bSop\b/g, "SOP")
    .replace(/\bEinvoice/g, "e-Invoice");
}

// Every disclosure row otherwise carries the identical hardcoded title
// ("Disclosure decision") — the one thing that actually varies per row is
// what kind of masked value was at stake and whether it was allowed, so say
// that in plain language instead of repeating a static label on every row.
const DISCLOSURE_NOUNS: Record<string, string> = {
  PERSON: "personal details",
  NRIC: "an ID number",
  PHONE: "a phone number",
  EMAIL: "an email address",
  BANKACC: "bank account details",
  CARD: "card details",
  ADDR: "an address",
  ORG: "organization details",
};

export function disclosureTitle(token: string, authorized: boolean) {
  const noun = token.startsWith("AMOUNT_BAND") ? "a financial amount" : (DISCLOSURE_NOUNS[token.split("_")[0]] ?? "protected details");
  return authorized ? `Viewed ${noun}` : `Blocked from ${noun}`;
}
