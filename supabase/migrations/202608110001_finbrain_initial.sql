create extension if not exists vector with schema extensions;

create table if not exists public.tokenized_content (
  id bigint generated always as identity primary key,
  source_record_id text unique not null,
  content_text text not null,
  embedding extensions.vector(768) not null,
  record_type text,
  summary text,
  created_at timestamptz default now() not null
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

create index if not exists audit_log_ts_idx on public.audit_log (ts desc);

alter table public.tokenized_content enable row level security;
alter table public.token_vault enable row level security;
alter table public.audit_log enable row level security;

alter table public.tokenized_content force row level security;
alter table public.token_vault force row level security;
alter table public.audit_log force row level security;

revoke all on table public.tokenized_content from anon, authenticated;
revoke all on table public.token_vault from anon, authenticated;
revoke all on table public.audit_log from anon, authenticated;

drop policy if exists "role_based_vault_access" on public.token_vault;
create policy "role_based_vault_access" on public.token_vault
  for select to authenticated
  using (
    coalesce(auth.jwt() ->> 'user_role', '') <> ''
    and allowed_roles @> jsonb_build_array(auth.jwt() ->> 'user_role')
  );

drop policy if exists "compliance_only_audit_read" on public.audit_log;
create policy "compliance_only_audit_read" on public.audit_log
  for select to authenticated
  using ((auth.jwt() ->> 'user_role') = 'compliance');
