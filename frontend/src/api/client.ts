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
  mode: "morpheus" | "gemini" | "offline-demo" | "structured-filter";
  insufficient_evidence: boolean;
  citations: QueryCitation[];
  conversation_id: string | null;
  turn_id: number | null;
  protected_intelligence_brief: CustomerIntelligenceBrief | null;
  intelligence_brief: CustomerIntelligenceBrief | null;
  exposure_receipt: ExposureReceipt | null;
}

export interface QueryCitation {
  citation_id: string;
  source_record_id: string;
  source_system: string;
  record_type: string | null;
  occurred_at: string | null;
  protected_excerpt: string;
  similarity: number;
  freshness: "current" | "aging" | "stale" | "undated";
  age_days: number | null;
  relation: "supporting" | "contradicting" | "stale" | "missing";
}

export interface IntelligenceClaim {
  id: string;
  statement: string;
  citation_ids: string[];
  relation: "supporting" | "contradicting" | "stale" | "missing";
}

export interface IntelligenceTimelineEvent {
  occurred_at: string | null;
  label: string;
  detail: string;
  citation_ids: string[];
}

export interface IntelligenceAction {
  id: string;
  title: string;
  rationale: string;
  suggested_owner: string;
  priority: "low" | "medium" | "high";
  citation_ids: string[];
}

export interface CustomerIntelligenceBrief {
  subject_label: string;
  status: "healthy" | "needs_attention" | "at_risk" | "insufficient_evidence";
  executive_summary: string;
  claims: IntelligenceClaim[];
  timeline: IntelligenceTimelineEvent[];
  open_commitments: IntelligenceClaim[];
  risks: IntelligenceClaim[];
  missing_information: IntelligenceClaim[];
  recommended_action: IntelligenceAction | null;
}

export interface ExposureReceipt {
  request_id: string;
  query_hash: string;
  reasoning_mode: string;
  reasoning_model: string | null;
  external_ai_used: boolean;
  privacy_preflight_passed: boolean;
  recognized_sensitive_fields: number;
  protected_question_tokens: number;
  protected_context_tokens: number;
  restored_tokens: number;
  withheld_tokens: number;
  active_role: Role;
  sources_supplied: number;
}

export interface CitationDetail {
  citation: QueryCitation;
  authorized_excerpt: string;
  restored_tokens: number;
  withheld_tokens: number;
  access_explanation: string;
  query_hash: string;
}

export interface RoleComparisonResult {
  role: Role;
  answer: string;
  restored_tokens: number;
  withheld_tokens: number;
  policy_explanations: string[];
}

export interface RoleComparisonResponse {
  turn_id: number;
  query_hash: string;
  protected_answer: string;
  results: RoleComparisonResult[];
}

export interface AuditEntry {
  id: number;
  role: string;
  token: string;
  authorized: boolean;
  query_hash: string;
  previous_hash: string;
  entry_hash: string;
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

export interface UploadProtectedItem {
  row_number: number | null;
  source_record_id: string;
  content_text: string;
  processing_status: ProcessingStatus;
  enrichment_mode: string | null;
}

export interface UploadIssue {
  code: string;
  row_number: number | null;
  field: string | null;
}

export interface UploadPreviewResponse {
  preview_digest: string;
  input_kind: string;
  schema_name: string | null;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  protected_preview: UploadProtectedItem[];
  issues: UploadIssue[];
  warnings: string[];
}

export interface UploadCommitResponse {
  preview_digest: string;
  input_kind: string;
  schema_name: string | null;
  status: "ready" | "partial" | "failed";
  total_rows: number;
  valid_rows: number;
  failed_rows: number;
  protected_rows: number;
  ready_rows: number;
  rows: UploadProtectedItem[];
  issues: UploadIssue[];
  warnings: string[];
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
  origin_type: "process_analysis" | "query_brief" | "verification_gap";
  origin_turn_id: number | null;
  origin_query_hash: string | null;
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
  previous_hash: string;
  entry_hash: string;
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

export async function askQuestion(
  question: string,
  role: Role,
  conversationId?: string | null,
): Promise<QueryResponse> {
  return parse<QueryResponse>(
    await fetch(`${BASE_URL}/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, role, conversation_id: conversationId || null }),
    }),
  );
}

export async function fetchCitationDetail(
  turnId: number,
  citationId: string,
  role: Role,
): Promise<CitationDetail> {
  return parse<CitationDetail>(
    await fetch(
      `${BASE_URL}/query-turns/${turnId}/citations/${encodeURIComponent(citationId)}?role=${role}`,
    ),
  );
}

export async function compareTurnRoles(
  turnId: number,
  requestingRole: Role,
  comparisonRoles: Role[],
): Promise<RoleComparisonResponse> {
  return parse<RoleComparisonResponse>(
    await fetch(`${BASE_URL}/query-turns/${turnId}/compare-roles`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        requesting_role: requestingRole,
        comparison_roles: comparisonRoles,
      }),
    }),
  );
}

export async function createRecommendationFromTurn(
  turnId: number,
  role: Role,
  actionId = "recommended-action",
  suggestedOwner?: string,
): Promise<ProcessRecommendation> {
  return parse<ProcessRecommendation>(
    await fetch(`${BASE_URL}/query-turns/${turnId}/recommendations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role, action_id: actionId, suggested_owner: suggestedOwner }),
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

function uploadHeaders(file: File, role: Role, previewDigest?: string): HeadersInit {
  return {
    "Content-Type": file.type || "application/octet-stream",
    "X-FinBrain-Filename": file.name,
    "X-FinBrain-Record-Type": file.name.toLowerCase().endsWith(".csv")
      ? "invoice_register"
      : "uploaded_document",
    "X-FinBrain-Role": role,
    ...(previewDigest ? { "X-FinBrain-Preview-Digest": previewDigest } : {}),
  };
}

export async function previewUpload(file: File, role: Role): Promise<UploadPreviewResponse> {
  return parse<UploadPreviewResponse>(
    await fetch(`${BASE_URL}/uploads/preview`, {
      method: "POST",
      headers: uploadHeaders(file, role),
      body: file,
    }),
  );
}

export async function commitUpload(
  file: File,
  role: Role,
  previewDigest: string,
): Promise<UploadCommitResponse> {
  return parse<UploadCommitResponse>(
    await fetch(`${BASE_URL}/uploads/commit`, {
      method: "POST",
      headers: uploadHeaders(file, role, previewDigest),
      body: file,
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

export async function analyzeProcesses(role: Role): Promise<ProcessRecommendation> {
  return parse<ProcessRecommendation>(
    await fetch(`${BASE_URL}/process-analysis`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        window_days: 30,
        source_systems: ["telegram", "email"],
        minimum_evidence: 3,
        role,
      }),
    }),
  );
}

export async function fetchRecommendations(role: Role): Promise<ProcessRecommendation[]> {
  return parse<ProcessRecommendation[]>(await fetch(`${BASE_URL}/recommendations?role=${role}`));
}

export async function decideRecommendation(
  id: number,
  decision: "approve" | "reject" | "mark-implemented",
  role: Role,
  comment = "",
): Promise<ProcessRecommendation> {
  return parse<ProcessRecommendation>(
    await fetch(`${BASE_URL}/recommendations/${id}/${decision}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role, comment }),
    }),
  );
}

export async function fetchWorkflowAudit(role: Role): Promise<WorkflowAuditResponse> {
  return parse<WorkflowAuditResponse>(
    await fetch(`${BASE_URL}/workflow-audit?role=${role}`),
  );
}
