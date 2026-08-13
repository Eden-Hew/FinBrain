export type Role =
  | "general_employee"
  | "finance_ops"
  | "owner_director"
  | "compliance";

export interface QueryResponse {
  answer: string;
  model_answer: string;
  model_question: string;
  sources_used: number;
  mode: "morpheus" | "gemini" | "offline-demo";
}

export interface AuditEntry {
  id: number;
  role: string;
  token: string;
  authorized: boolean;
  query_hash: string;
  ts: string;
}

export interface AuditResponse {
  entries: AuditEntry[];
  chain_valid: boolean;
}

export type ProcessingStatus = "protected" | "ready" | "failed_enrichment";

export interface IngestionRequest {
  role: Role;
  source_record_id: string;
  source_system: string;
  record_type: string;
  text: string;
  occurred_at: string | null;
  metadata: Record<string, string>;
  refresh: boolean;
}

export interface IngestionResponse {
  source_record_id: string;
  content_text: string;
  summary: string | null;
  processing_status: ProcessingStatus;
  enrichment_mode: string | null;
  created: boolean;
  refreshed: boolean;
  submitted_as: Role;
  authorization_mode: "demo-role";
}

export interface TelegramIntegrationStatus {
  configured: boolean;
  mode: string;
  status: "healthy" | "degraded" | "offline" | "stopped" | "starting" | "not_configured";
  detector_ready: boolean;
  last_heartbeat_at: string | null;
  last_update_at: string | null;
}

export interface ProtectedIngestionRecord {
  source_record_id: string;
  source_system: string;
  record_type: string | null;
  content_excerpt: string;
  summary: string | null;
  structured_summary: {
    category?: string;
    priority?: string;
    action_required?: boolean;
  } | null;
  processing_status: ProcessingStatus;
  enrichment_mode: string | null;
  occurred_at: string | null;
  created_at: string;
  updated_at: string;
  safe_metadata: Record<string, string>;
}

const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function parse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export async function askQuestion(question: string, role: Role): Promise<QueryResponse> {
  return parse<QueryResponse>(
    await fetch(`${BASE_URL}/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, role }),
    }),
  );
}

export async function fetchAuditLog(role: Role): Promise<AuditResponse> {
  return parse<AuditResponse>(await fetch(`${BASE_URL}/audit-log?role=${role}`));
}

export async function ingestRecord(payload: IngestionRequest): Promise<IngestionResponse> {
  return parse<IngestionResponse>(
    await fetch(`${BASE_URL}/ingestion`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  );
}

export async function fetchTelegramStatus(): Promise<TelegramIntegrationStatus> {
  return parse<TelegramIntegrationStatus>(
    await fetch(`${BASE_URL}/integrations/telegram/status`),
  );
}

export async function fetchTelegramRecords(): Promise<ProtectedIngestionRecord[]> {
  return parse<ProtectedIngestionRecord[]>(
    await fetch(`${BASE_URL}/ingestion-records?source_system=telegram&limit=12`),
  );
}
