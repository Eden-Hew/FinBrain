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
  insufficient_evidence: boolean;
  citations: QueryCitation[];
}

export interface QueryCitation {
  citation_id: string;
  source_record_id: string;
  source_system: string;
  record_type: string | null;
  occurred_at: string | null;
  protected_excerpt: string;
  similarity: number;
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

export interface EmailIntegrationStatus {
  configured: boolean;
  status: string;
  folder_name: string;
  last_uid: number;
  last_sync_at: string | null;
  failure_code: string | null;
}

export interface EmailSyncResponse {
  examined: number;
  protected: number;
  ready: number;
  failed: number;
  last_uid: number;
}

export interface RecommendationEvidence {
  citation_id: string;
  source_record_id: string;
  source_system: string;
  record_type: string | null;
  occurred_at: string | null;
  evidence_excerpt: string;
  relevance_reason: string;
}

export interface ProcessRecommendation {
  id: number;
  title: string;
  problem_statement: string;
  recommendation: string;
  expected_benefit: string;
  suggested_owner: string;
  success_metric: string;
  category: string;
  priority: "low" | "medium" | "high";
  confidence: number;
  status: "proposed" | "approved" | "rejected" | "implemented" | "dismissed";
  analysis_window_start: string;
  analysis_window_end: string;
  record_count: number;
  source_systems: string[];
  enrichment_mode: string;
  evidence: RecommendationEvidence[];
  created_at: string;
  updated_at: string;
}

export interface WorkflowAuditEntry {
  id: number;
  event_type: string;
  actor_role: string;
  actor_ref: string;
  resource_type: string;
  resource_id: string;
  event_payload: Record<string, unknown>;
  created_at: string;
}

export interface WorkflowAuditResponse {
  entries: WorkflowAuditEntry[];
  chain_valid: boolean;
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

export async function fetchEmailStatus(): Promise<EmailIntegrationStatus> {
  return parse<EmailIntegrationStatus>(await fetch(`${BASE_URL}/integrations/email/status`));
}

export async function syncEmail(): Promise<EmailSyncResponse> {
  return parse<EmailSyncResponse>(
    await fetch(`${BASE_URL}/integrations/email/sync`, { method: "POST" }),
  );
}

export async function fetchEmailRecords(): Promise<ProtectedIngestionRecord[]> {
  return parse<ProtectedIngestionRecord[]>(
    await fetch(`${BASE_URL}/ingestion-records?source_system=email&limit=12`),
  );
}

export async function analyzeProcesses(): Promise<ProcessRecommendation> {
  return parse<ProcessRecommendation>(
    await fetch(`${BASE_URL}/process-analysis`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        window_days: 30,
        source_systems: ["telegram", "email"],
        minimum_evidence: 3,
        role: "owner_director",
      }),
    }),
  );
}

export async function fetchRecommendations(
  role: Role = "owner_director",
): Promise<ProcessRecommendation[]> {
  return parse<ProcessRecommendation[]>(await fetch(`${BASE_URL}/recommendations?role=${role}`));
}

export async function decideRecommendation(
  id: number,
  decision: "approve" | "reject" | "mark-implemented",
  comment = "",
): Promise<ProcessRecommendation> {
  return parse<ProcessRecommendation>(
    await fetch(`${BASE_URL}/recommendations/${id}/${decision}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role: "owner_director", comment }),
    }),
  );
}

export async function fetchWorkflowAudit(): Promise<WorkflowAuditResponse> {
  return parse<WorkflowAuditResponse>(
    await fetch(`${BASE_URL}/workflow-audit?role=compliance`),
  );
}
