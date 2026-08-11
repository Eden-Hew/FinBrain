create extension if not exists vector with schema extensions;

create table if not exists public.tokenized_content (
  id bigint generated always as identity primary key,
  source_record_id text unique not null,
  content_text text not null,
  embedding extensions.vector(768),
  record_type text,
  summary text,
  source_system text default 'legacy' not null,
  occurred_at timestamptz,
  content_fingerprint text,
  safe_metadata jsonb default '{}'::jsonb not null
    check (jsonb_typeof(safe_metadata) = 'object'),
  structured_summary jsonb
    check (structured_summary is null or jsonb_typeof(structured_summary) = 'object'),
  processing_status text default 'protected' not null
    check (processing_status in ('protected', 'ready', 'failed_enrichment')),
  processing_error text,
  enrichment_mode text,
  created_at timestamptz default now() not null,
  updated_at timestamptz default now() not null
);

create table if not exists public.token_vault (
  token text primary key,
  entity_type text not null,
  encrypted_value bytea not null,
  nonce bytea not null,
  allowed_roles jsonb not null check (jsonb_typeof(allowed_roles) = 'array'),
  sensitivity text default 'high' not null,
  source_record_id text not null,
  created_at timestamptz default now() not null
);

create table if not exists public.audit_log (
  id bigint generated always as identity primary key,
  prev_hash text not null,
  event_hash text not null,
  user_role text not null,
  token text not null,
  authorized boolean not null,
  query_hash text not null,
  ts timestamptz default now() not null
);

create index if not exists tokenized_content_embedding_idx
  on public.tokenized_content using hnsw (embedding extensions.vector_cosine_ops);

create index if not exists tokenized_content_processing_status_idx
  on public.tokenized_content (processing_status);

create index if not exists tokenized_content_source_system_idx
  on public.tokenized_content (source_system, occurred_at desc);

create index if not exists audit_log_ts_idx on public.audit_log (ts desc);
