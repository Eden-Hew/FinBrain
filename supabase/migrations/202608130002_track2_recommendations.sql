create table if not exists public.email_sync_state (
  connector_key text primary key,
  mailbox_ref text not null,
  folder_name text not null,
  last_uid bigint default 0 not null,
  last_sync_at timestamptz,
  status text default 'idle' not null,
  failure_code text,
  created_at timestamptz default now() not null,
  updated_at timestamptz default now() not null,
  constraint email_sync_state_status_valid
    check (status in ('idle', 'syncing', 'healthy', 'degraded', 'stopped'))
);

create table if not exists public.email_ingestion_receipts (
  message_ref_hash text primary key,
  source_record_id text unique,
  status text default 'received' not null,
  failure_code text,
  received_at timestamptz default now() not null,
  processed_at timestamptz,
  constraint email_ingestion_receipts_status_valid
    check (status in ('received', 'protected', 'ready', 'failed', 'ignored'))
);

create table if not exists public.process_recommendations (
  id bigint generated always as identity primary key,
  fingerprint text unique not null,
  title text not null,
  problem_statement text not null,
  recommendation text not null,
  expected_benefit text not null,
  suggested_owner text not null,
  success_metric text not null,
  category text not null,
  priority text not null check (priority in ('low', 'medium', 'high')),
  confidence double precision not null check (confidence between 0 and 1),
  status text default 'proposed' not null
    check (status in ('proposed', 'approved', 'rejected', 'implemented', 'dismissed')),
  analysis_window_start timestamptz not null,
  analysis_window_end timestamptz not null,
  record_count integer not null check (record_count > 0),
  source_systems jsonb not null check (jsonb_typeof(source_systems) = 'array'),
  enrichment_mode text not null,
  created_at timestamptz default now() not null,
  updated_at timestamptz default now() not null
);

create table if not exists public.recommendation_evidence (
  id bigint generated always as identity primary key,
  recommendation_id bigint not null references public.process_recommendations(id) on delete cascade,
  tokenized_content_id bigint not null references public.tokenized_content(id) on delete restrict,
  evidence_excerpt text not null,
  relevance_reason text not null,
  created_at timestamptz default now() not null,
  constraint recommendation_evidence_record_unique
    unique (recommendation_id, tokenized_content_id)
);

create table if not exists public.recommendation_decisions (
  id bigint generated always as identity primary key,
  recommendation_id bigint not null references public.process_recommendations(id) on delete cascade,
  decision text not null check (decision in ('approved', 'rejected', 'implemented')),
  actor_role text not null,
  actor_ref text not null,
  protected_comment text,
  created_at timestamptz default now() not null
);

create table if not exists public.workflow_audit_log (
  id bigint generated always as identity primary key,
  prev_hash text not null,
  event_hash text not null,
  event_type text not null,
  actor_role text not null,
  actor_ref text not null,
  resource_type text not null,
  resource_id text not null,
  event_payload jsonb not null check (jsonb_typeof(event_payload) = 'object'),
  created_at timestamptz default now() not null
);

create index if not exists email_receipts_status_received_idx
  on public.email_ingestion_receipts (status, received_at desc);
create index if not exists process_recommendations_status_created_idx
  on public.process_recommendations (status, created_at desc);
create index if not exists recommendation_evidence_recommendation_idx
  on public.recommendation_evidence (recommendation_id);
create index if not exists recommendation_decisions_recommendation_idx
  on public.recommendation_decisions (recommendation_id, created_at desc);
create index if not exists workflow_audit_created_idx
  on public.workflow_audit_log (created_at desc);

alter table public.email_sync_state enable row level security;
alter table public.email_ingestion_receipts enable row level security;
alter table public.process_recommendations enable row level security;
alter table public.recommendation_evidence enable row level security;
alter table public.recommendation_decisions enable row level security;
alter table public.workflow_audit_log enable row level security;

alter table public.email_sync_state force row level security;
alter table public.email_ingestion_receipts force row level security;
alter table public.process_recommendations force row level security;
alter table public.recommendation_evidence force row level security;
alter table public.recommendation_decisions force row level security;
alter table public.workflow_audit_log force row level security;

revoke all on table public.email_sync_state from anon, authenticated;
revoke all on table public.email_ingestion_receipts from anon, authenticated;
revoke all on table public.process_recommendations from anon, authenticated;
revoke all on table public.recommendation_evidence from anon, authenticated;
revoke all on table public.recommendation_decisions from anon, authenticated;
revoke all on table public.workflow_audit_log from anon, authenticated;
