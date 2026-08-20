import { accessToken, supabase } from "../auth/supabase";

export type Role =
  | "general_employee"
  | "finance_ops"
  | "owner_director"
  | "compliance";

export type QueryIntent =
  | "semantic"
  | "lookup"
  | "analyze_all"
  | "list_records"
  | "list_sources"
  | "count_records"
  | "count_sources";

export interface QueryResponse {
  answer: string;
  model_answer: string;
  model_question: string;
  query_intent: QueryIntent;
  sources_used: number;
  mode: "morpheus" | "gemini" | "offline-demo" | "no-evidence" | "conversation-clarification" | "structured-filter" | "structured-lookup";
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
  disclosure_session_ref: string;
  single_use_grants: number;
  vault_key_version: number;
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
  actor_ref: string;
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
  authorization_mode: "supabase-jwt";
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

export class ApiError extends Error {
  constructor(
    public readonly code: string,
    public readonly status: number,
    public readonly requestId: string | null,
  ) {
    super(code);
    this.name = "ApiError";
  }
}

async function parse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(
      body.detail ?? `request_failed_${response.status}`,
      response.status,
      response.headers.get("X-Request-ID"),
    );
  }
  return response.json() as Promise<T>;
}

// Internal plumbing codes (thrown by accessToken() when there's no session)
// leak straight into `Error.message` — translate the ones we know about
// instead of showing a snake_case string on an initial page load.
export function friendlyLoadError(message: string): string {
  if (message === "authentication_required") return "Your session has expired — please log in again.";
  if (message === "insufficient_role") return "Your role doesn't have access to this data.";
  return "Couldn't load this page right now — try refreshing.";
}

async function authenticatedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = await accessToken();
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${BASE_URL}${path}`, { ...init, headers });
  if (response.status === 401) {
    const body = await response.clone().json().catch(() => ({}));
    const terminalCodes = new Set([
      "expired_access_token",
      "invalid_access_token",
      "invalid_signature",
      "invalid_issuer",
      "invalid_audience",
      "invalid_supabase_role",
      "missing_tenant_claim",
      "missing_exp_claim",
      "missing_iss_claim",
      "missing_sub_claim",
      "missing_aud_claim",
      "invalid_identity_claims",
    ]);
    if (terminalCodes.has(body.detail)) {
      await supabase.auth.signOut();
    }
  }
  return response;
}

export async function askQuestion(
  question: string,
  conversationId?: string | null,
): Promise<QueryResponse> {
  return parse<QueryResponse>(
    await authenticatedFetch("/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, conversation_id: conversationId || null }),
    }),
  );
}

export async function fetchCitationDetail(
  turnId: number,
  citationId: string,
): Promise<CitationDetail> {
  return parse<CitationDetail>(
    await authenticatedFetch(`/query-turns/${turnId}/citations/${encodeURIComponent(citationId)}`),
  );
}

export async function compareTurnRoles(
  turnId: number,
  comparisonRoles: Role[],
): Promise<RoleComparisonResponse> {
  return parse<RoleComparisonResponse>(
    await authenticatedFetch(`/query-turns/${turnId}/compare-roles`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        comparison_roles: comparisonRoles,
      }),
    }),
  );
}

export async function createRecommendationFromTurn(
  turnId: number,
  actionId = "recommended-action",
  suggestedOwner?: string,
): Promise<ProcessRecommendation> {
  return parse<ProcessRecommendation>(
    await authenticatedFetch(`/query-turns/${turnId}/recommendations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action_id: actionId, suggested_owner: suggestedOwner }),
    }),
  );
}

export async function fetchAuditLog(): Promise<AuditResponse> {
  return parse<AuditResponse>(await authenticatedFetch("/audit-log"));
}

export async function ingestRecord(payload: IngestionRequest): Promise<IngestionResponse> {
  return parse<IngestionResponse>(
    await authenticatedFetch("/ingestion", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  );
}

function uploadHeaders(file: File, previewDigest?: string): HeadersInit {
  return {
    "Content-Type": file.type || "application/octet-stream",
    "X-FinBrain-Filename": file.name,
    "X-FinBrain-Record-Type": file.name.toLowerCase().endsWith(".csv")
      ? "invoice_register"
      : "uploaded_document",
    ...(previewDigest ? { "X-FinBrain-Preview-Digest": previewDigest } : {}),
  };
}

export async function previewUpload(file: File): Promise<UploadPreviewResponse> {
  return parse<UploadPreviewResponse>(
    await authenticatedFetch("/uploads/preview", {
      method: "POST",
      headers: uploadHeaders(file),
      body: file,
    }),
  );
}

export async function commitUpload(
  file: File,
  previewDigest: string,
): Promise<UploadCommitResponse> {
  return parse<UploadCommitResponse>(
    await authenticatedFetch("/uploads/commit", {
      method: "POST",
      headers: uploadHeaders(file, previewDigest),
      body: file,
    }),
  );
}

export async function fetchTelegramStatus(): Promise<TelegramIntegrationStatus> {
  return parse<TelegramIntegrationStatus>(
    await authenticatedFetch("/integrations/telegram/status"),
  );
}

export async function fetchTelegramRecords(): Promise<ProtectedIngestionRecord[]> {
  return parse<ProtectedIngestionRecord[]>(
    await authenticatedFetch("/ingestion-records?source_system=telegram&limit=12"),
  );
}

export async function fetchEmailStatus(): Promise<EmailIntegrationStatus> {
  return parse<EmailIntegrationStatus>(await authenticatedFetch("/integrations/email/status"));
}

export async function syncEmail(): Promise<EmailSyncResponse> {
  return parse<EmailSyncResponse>(
    await authenticatedFetch("/integrations/email/sync", { method: "POST" }),
  );
}

export async function fetchEmailRecords(): Promise<ProtectedIngestionRecord[]> {
  return parse<ProtectedIngestionRecord[]>(
    await authenticatedFetch("/ingestion-records?source_system=email&limit=12"),
  );
}

export async function analyzeProcesses(): Promise<ProcessRecommendation> {
  return parse<ProcessRecommendation>(
    await authenticatedFetch("/process-analysis", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        window_days: 30,
        source_systems: ["telegram", "email"],
        minimum_evidence: 3,
      }),
    }),
  );
}

export async function fetchRecommendations(): Promise<ProcessRecommendation[]> {
  return parse<ProcessRecommendation[]>(await authenticatedFetch("/recommendations"));
}

export async function decideRecommendation(
  id: number,
  decision: "approve" | "reject" | "mark-implemented",
  comment = "",
): Promise<ProcessRecommendation> {
  return parse<ProcessRecommendation>(
    await authenticatedFetch(`/recommendations/${id}/${decision}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ comment }),
    }),
  );
}

export interface EInvoiceApiRecord {
  id: number;
  supplier_name: string;
  supplier_tin: string | null;
  buyer_name: string | null;
  buyer_customer_id: number | null;
  invoice_no: string | null;
  issue_date: string | null;
  due_date: string | null;
  currency: string | null;
  tax_type: string | null;
  tax_rate: string | null;
  total_amount: string;
  status: "review" | "pending" | "submitted" | "validated";
  paid_at: string | null;
  created_at: string;
  document_available: boolean;
  readiness_reason: string;
  uin: string | null;
}

export interface EinvoiceDocumentUrl {
  url: string;
  expires_in: number;
}

export interface EinvoiceReadinessCategory {
  label: "critical" | "warning" | "passing";
  count: number;
  records: EInvoiceApiRecord[];
}

export interface EinvoiceReadinessResponse {
  score: number;
  total_records: number;
  passing_count: number;
  critical: EinvoiceReadinessCategory;
  warning: EinvoiceReadinessCategory;
  passing: EinvoiceReadinessCategory;
}

export interface EinvoiceOutreachDraft {
  id: number;
  einvoice_record_id: number;
  channel: "telegram" | "email";
  draft_text: string;
  status: "draft" | "approved" | "rejected";
  created_at: string;
  decided_at: string | null;
}

export async function fetchEinvoiceReadiness(): Promise<EinvoiceReadinessResponse> {
  return parse<EinvoiceReadinessResponse>(await authenticatedFetch("/einvoice-readiness"));
}

export async function requestEinvoiceFix(
  recordId: number,
  channel: "telegram" | "email",
): Promise<EinvoiceOutreachDraft> {
  return parse<EinvoiceOutreachDraft>(
    await authenticatedFetch(`/einvoice-readiness/${recordId}/request-fix`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ channel }),
    }),
  );
}

export async function fetchEinvoiceDocumentUrl(recordId: number): Promise<EinvoiceDocumentUrl> {
  return parse<EinvoiceDocumentUrl>(
    await authenticatedFetch(`/einvoice-readiness/${recordId}/document`),
  );
}

export async function fetchEinvoicePdfBlob(recordId: number): Promise<Blob> {
  const response = await authenticatedFetch(`/einvoice-records/${recordId}/pdf`);
  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}));
    throw new Error(errorBody.detail ?? `Failed to load invoice PDF (${response.status})`);
  }
  return response.blob();
}

export async function fetchEinvoiceRecords(): Promise<EInvoiceApiRecord[]> {
  return parse<EInvoiceApiRecord[]>(await authenticatedFetch("/einvoice-records"));
}

export interface EInvoiceCreatePayload {
  supplier_name: string;
  supplier_tin?: string | null;
  buyer_name?: string | null;
  invoice_no?: string | null;
  issue_date?: string | null;
  currency?: string | null;
  tax_type?: string | null;
  tax_rate?: string | null;
  total_amount: string;
}

export async function createEinvoiceRecord(payload: EInvoiceCreatePayload): Promise<EInvoiceApiRecord> {
  return parse<EInvoiceApiRecord>(
    await authenticatedFetch("/einvoice-records", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  );
}

export interface InvoiceExtraction {
  supplier_name: string | null;
  supplier_tin: string | null;
  buyer_name: string | null;
  invoice_no: string | null;
  issue_date: string | null;
  currency: string | null;
  tax_type: string | null;
  tax_rate: string | null;
  total_amount: string | null;
}

export async function extractEinvoiceFields(file: File): Promise<InvoiceExtraction> {
  return parse<InvoiceExtraction>(
    await authenticatedFetch("/einvoice-records/extract", {
      method: "POST",
      headers: { "Content-Type": "application/pdf" },
      body: file,
    }),
  );
}

export async function uploadEinvoiceDocument(recordId: number, file: File): Promise<EInvoiceApiRecord> {
  return parse<EInvoiceApiRecord>(
    await authenticatedFetch(`/einvoice-records/${recordId}/document`, {
      method: "POST",
      headers: { "Content-Type": "application/pdf" },
      body: file,
    }),
  );
}

export async function fetchEinvoiceRecord(recordId: number): Promise<EInvoiceApiRecord> {
  return parse<EInvoiceApiRecord>(await authenticatedFetch(`/einvoice-records/${recordId}`));
}

export async function approveEinvoiceRecord(recordId: number): Promise<EInvoiceApiRecord> {
  return parse<EInvoiceApiRecord>(
    await authenticatedFetch(`/einvoice-records/${recordId}/approve`, { method: "POST" }),
  );
}

export async function markEinvoicePaid(
  recordId: number,
  paidAt?: string,
): Promise<EInvoiceApiRecord> {
  return parse<EInvoiceApiRecord>(
    await authenticatedFetch(`/einvoice-records/${recordId}/mark-paid`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ paid_at: paidAt ?? null }),
    }),
  );
}

export async function fetchEinvoiceOutreachDrafts(): Promise<EinvoiceOutreachDraft[]> {
  return parse<EinvoiceOutreachDraft[]>(await authenticatedFetch("/einvoice-outreach-drafts"));
}

export async function decideEinvoiceOutreach(
  id: number,
  decision: "approve" | "reject",
): Promise<EinvoiceOutreachDraft> {
  return parse<EinvoiceOutreachDraft>(
    await authenticatedFetch(`/einvoice-outreach-drafts/${id}/${decision}`, { method: "POST" }),
  );
}

export type FinancePeriod = "month" | "quarter" | "year";

export interface RevenuePeriodPoint {
  period_label: string;
  period_start: string;
  total_amount: string;
}

export interface ARAgingBucket {
  label: "current" | "1-30" | "31-60" | "61-90" | "90+";
  count: number;
  total_amount: string;
}

export interface TopCustomer {
  customer_id: number;
  name: string;
  total_amount: string;
  invoice_count: number;
}

export interface InvoiceStatusBreakdown {
  label: "pending" | "outstanding" | "paid";
  count: number;
  total_amount: string;
}

export interface FinanceSummaryResponse {
  period: FinancePeriod;
  period_start: string;
  period_end: string;
  total_revenue: string;
  prior_period_revenue: string;
  revenue_change_pct: number | null;
  outstanding_ar: string;
  ar_aging: ARAgingBucket[];
  revenue_trend: RevenuePeriodPoint[];
  top_customers: TopCustomer[];
  status_breakdown: InvoiceStatusBreakdown[];
  validated_invoice_count: number;
  avg_days_to_pay: number | null;
}

export async function fetchFinanceSummary(
  period: FinancePeriod,
  offset: number,
): Promise<FinanceSummaryResponse> {
  return parse<FinanceSummaryResponse>(
    await authenticatedFetch(`/finance/summary?period=${period}&offset=${offset}`),
  );
}

export async function fetchWorkflowAudit(): Promise<WorkflowAuditResponse> {
  return parse<WorkflowAuditResponse>(
    await authenticatedFetch("/workflow-audit"),
  );
}
