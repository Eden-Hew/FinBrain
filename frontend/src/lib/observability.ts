import * as Sentry from "@sentry/react";

const dsn = import.meta.env.VITE_SENTRY_DSN;

// No-op unless VITE_SENTRY_DSN is set, mirroring the backend's SENTRY_DSN gate in
// app/observability.py. sendDefaultPii stays false: FinBrain's entire design tokenizes
// PII before it ever reaches the client, and Sentry's default capture (request/response
// bodies, breadcrumbs) would work against that if left on.
export function initObservability(): void {
  if (!dsn) return;
  Sentry.init({
    dsn,
    environment: import.meta.env.VITE_SENTRY_ENVIRONMENT ?? "development",
    tracesSampleRate: Number(import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE ?? 0),
    sendDefaultPii: false,
  });
}
