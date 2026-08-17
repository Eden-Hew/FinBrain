alter table public.token_vault
  add column if not exists key_version integer not null default 1,
  add column if not exists masked_value text not null default '[restricted]',
  add column if not exists encryption_algorithm text not null default 'AES-256-GCM';

create table if not exists public.protected_token_registry (
  token text primary key,
  entity_type text not null,
  masked_value text not null,
  created_at timestamptz not null default now()
);

create table if not exists public.vault_key_versions (
  version integer primary key,
  wrapped_key bytea not null,
  wrap_nonce bytea not null,
  status text not null check (status in ('pending', 'active', 'decrypt_only', 'retired')),
  created_at timestamptz not null default now(),
  activated_at timestamptz,
  retired_at timestamptz
);

create unique index if not exists vault_key_one_active_idx
  on public.vault_key_versions ((status)) where status = 'active';

create table if not exists public.vault_rotation_jobs (
  id bigint generated always as identity primary key,
  from_version integer not null references public.vault_key_versions(version),
  to_version integer not null references public.vault_key_versions(version),
  status text not null check (status in ('pending', 'running', 'completed', 'failed')),
  rows_total integer not null,
  rows_rotated integer not null default 0,
  last_token text,
  failure_code text,
  started_at timestamptz not null default now(),
  completed_at timestamptz
);

alter table public.vault_key_versions enable row level security;
alter table public.vault_key_versions force row level security;
alter table public.vault_rotation_jobs enable row level security;
alter table public.vault_rotation_jobs force row level security;
alter table public.protected_token_registry enable row level security;
alter table public.protected_token_registry force row level security;
revoke all on table public.vault_key_versions, public.vault_rotation_jobs,
  public.protected_token_registry from anon, authenticated;

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'finbrain_app') then
    create role finbrain_app nologin nobypassrls;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'finbrain_worker') then
    create role finbrain_worker nologin nobypassrls;
  end if;
end
$$;

grant finbrain_app, finbrain_worker to postgres;
grant usage on schema public to finbrain_app, finbrain_worker;
grant usage, select on all sequences in schema public to finbrain_app, finbrain_worker;
grant select, insert, update on public.tokenized_content to finbrain_app, finbrain_worker;
grant select, insert on public.token_vault to finbrain_app, finbrain_worker;
grant update on public.token_vault to finbrain_worker;
grant select, insert on public.protected_token_registry to finbrain_app, finbrain_worker;
grant select on public.vault_key_versions to finbrain_app;
grant select, insert, update on public.vault_key_versions to finbrain_worker;
grant select, insert, update on public.vault_rotation_jobs to finbrain_worker;
grant select, insert on public.audit_log, public.workflow_audit_log to finbrain_app, finbrain_worker;
grant select, insert, update, delete on public.conversations,
  public.conversation_turns, public.conversation_turn_citations to finbrain_app;
grant select, insert, update on public.process_recommendations,
  public.recommendation_evidence, public.recommendation_decisions to finbrain_app;
grant select, insert, update on public.structured_ingestion_batches to finbrain_app, finbrain_worker;
grant select, insert, update on public.integration_status,
  public.telegram_update_receipts, public.email_sync_state,
  public.email_ingestion_receipts to finbrain_worker;
grant select on public.integration_status to finbrain_app;
grant select, insert, update on public.email_sync_state,
  public.email_ingestion_receipts to finbrain_app;

create or replace function public.finbrain_role()
returns text language sql stable set search_path = ''
as $$ select coalesce(current_setting('app.user_role', true), '') $$;

create or replace function public.finbrain_user_id()
returns uuid language sql stable set search_path = ''
as $$ select nullif(current_setting('app.user_id', true), '')::uuid $$;

grant execute on function public.finbrain_role() to finbrain_app, finbrain_worker;
grant execute on function public.finbrain_user_id() to finbrain_app, finbrain_worker;

drop policy if exists finbrain_app_content on public.tokenized_content;
create policy finbrain_app_content on public.tokenized_content to finbrain_app
  using (public.finbrain_role() <> '')
  with check (public.finbrain_role() <> '');

drop policy if exists finbrain_worker_content on public.tokenized_content;
create policy finbrain_worker_content on public.tokenized_content to finbrain_worker
  using (true) with check (true);

drop policy if exists finbrain_app_vault on public.token_vault;
create policy finbrain_app_vault on public.token_vault
  for select to finbrain_app using (allowed_roles ? public.finbrain_role());

drop policy if exists finbrain_app_vault_insert on public.token_vault;
create policy finbrain_app_vault_insert on public.token_vault
  for insert to finbrain_app with check (public.finbrain_role() <> '');

drop policy if exists finbrain_worker_vault on public.token_vault;
create policy finbrain_worker_vault on public.token_vault to finbrain_worker
  using (true) with check (true);

drop policy if exists finbrain_app_token_registry on public.protected_token_registry;
create policy finbrain_app_token_registry on public.protected_token_registry to finbrain_app
  using (public.finbrain_role() <> '') with check (public.finbrain_role() <> '');

drop policy if exists finbrain_worker_token_registry on public.protected_token_registry;
create policy finbrain_worker_token_registry on public.protected_token_registry
  to finbrain_worker using (true) with check (true);

drop policy if exists finbrain_app_key_read on public.vault_key_versions;
create policy finbrain_app_key_read on public.vault_key_versions
  for select to finbrain_app using (status in ('active', 'decrypt_only'));

drop policy if exists finbrain_worker_keys on public.vault_key_versions;
create policy finbrain_worker_keys on public.vault_key_versions to finbrain_worker
  using (true) with check (true);

drop policy if exists finbrain_worker_rotation_jobs on public.vault_rotation_jobs;
create policy finbrain_worker_rotation_jobs on public.vault_rotation_jobs to finbrain_worker
  using (true) with check (true);

drop policy if exists finbrain_owned_conversations on public.conversations;
create policy finbrain_owned_conversations on public.conversations to finbrain_app
  using (
    created_by_user_id = public.finbrain_user_id()
    or public.finbrain_role() = 'compliance'
  )
  with check (created_by_user_id = public.finbrain_user_id());

drop policy if exists finbrain_conversation_turns on public.conversation_turns;
create policy finbrain_conversation_turns on public.conversation_turns to finbrain_app
  using (exists (
    select 1 from public.conversations c where c.id = conversation_id
  ))
  with check (exists (
    select 1 from public.conversations c where c.id = conversation_id
  ));

drop policy if exists finbrain_conversation_citations on public.conversation_turn_citations;
create policy finbrain_conversation_citations on public.conversation_turn_citations to finbrain_app
  using (exists (
    select 1 from public.conversation_turns t where t.id = turn_id
  ))
  with check (exists (
    select 1 from public.conversation_turns t where t.id = turn_id
  ));

drop policy if exists finbrain_audit_insert on public.audit_log;
create policy finbrain_audit_insert on public.audit_log
  for insert to finbrain_app with check (public.finbrain_role() <> '');
drop policy if exists finbrain_audit_compliance_read on public.audit_log;
create policy finbrain_audit_compliance_read on public.audit_log
  for select to finbrain_app using (public.finbrain_role() = 'compliance');

drop policy if exists finbrain_workflow_insert on public.workflow_audit_log;
create policy finbrain_workflow_insert on public.workflow_audit_log
  for insert to finbrain_app with check (public.finbrain_role() <> '');
drop policy if exists finbrain_workflow_compliance_read on public.workflow_audit_log;
create policy finbrain_workflow_compliance_read on public.workflow_audit_log
  for select to finbrain_app using (public.finbrain_role() = 'compliance');

drop policy if exists finbrain_worker_audit_insert on public.audit_log;
create policy finbrain_worker_audit_insert on public.audit_log
  for insert to finbrain_worker with check (true);
drop policy if exists finbrain_worker_workflow_insert on public.workflow_audit_log;
create policy finbrain_worker_workflow_insert on public.workflow_audit_log
  for insert to finbrain_worker with check (true);

drop policy if exists finbrain_recommendation_read on public.process_recommendations;
create policy finbrain_recommendation_read on public.process_recommendations
  for select to finbrain_app
  using (public.finbrain_role() in ('finance_ops', 'owner_director', 'compliance'));
drop policy if exists finbrain_recommendation_insert on public.process_recommendations;
create policy finbrain_recommendation_insert on public.process_recommendations
  for insert to finbrain_app
  with check (public.finbrain_role() in ('finance_ops', 'owner_director'));
drop policy if exists finbrain_recommendation_update on public.process_recommendations;
create policy finbrain_recommendation_update on public.process_recommendations
  for update to finbrain_app using (public.finbrain_role() = 'owner_director')
  with check (public.finbrain_role() = 'owner_director');

drop policy if exists finbrain_recommendation_evidence on public.recommendation_evidence;
create policy finbrain_recommendation_evidence on public.recommendation_evidence to finbrain_app
  using (exists (
    select 1 from public.process_recommendations r where r.id = recommendation_id
  ))
  with check (exists (
    select 1 from public.process_recommendations r where r.id = recommendation_id
  ));

drop policy if exists finbrain_recommendation_decisions on public.recommendation_decisions;
create policy finbrain_recommendation_decisions on public.recommendation_decisions to finbrain_app
  using (public.finbrain_role() in ('finance_ops', 'owner_director', 'compliance'))
  with check (public.finbrain_role() = 'owner_director');

drop policy if exists finbrain_structured_batches on public.structured_ingestion_batches;
create policy finbrain_structured_batches on public.structured_ingestion_batches to finbrain_app
  using (public.finbrain_role() <> '') with check (public.finbrain_role() <> '');
drop policy if exists finbrain_worker_structured_batches on public.structured_ingestion_batches;
create policy finbrain_worker_structured_batches on public.structured_ingestion_batches
  to finbrain_worker using (true) with check (true);

drop policy if exists finbrain_app_integration_status on public.integration_status;
create policy finbrain_app_integration_status on public.integration_status
  for select to finbrain_app
  using (public.finbrain_role() in ('finance_ops', 'owner_director', 'compliance'));
drop policy if exists finbrain_worker_integration_status on public.integration_status;
create policy finbrain_worker_integration_status on public.integration_status to finbrain_worker
  using (true) with check (true);

drop policy if exists finbrain_app_email_sync_state on public.email_sync_state;
create policy finbrain_app_email_sync_state on public.email_sync_state to finbrain_app
  using (public.finbrain_role() in ('finance_ops', 'owner_director'))
  with check (public.finbrain_role() in ('finance_ops', 'owner_director'));
drop policy if exists finbrain_worker_email_sync_state on public.email_sync_state;
create policy finbrain_worker_email_sync_state on public.email_sync_state to finbrain_worker
  using (true) with check (true);

drop policy if exists finbrain_app_email_receipts on public.email_ingestion_receipts;
create policy finbrain_app_email_receipts on public.email_ingestion_receipts to finbrain_app
  using (public.finbrain_role() in ('finance_ops', 'owner_director'))
  with check (public.finbrain_role() in ('finance_ops', 'owner_director'));
drop policy if exists finbrain_worker_email_receipts on public.email_ingestion_receipts;
create policy finbrain_worker_email_receipts on public.email_ingestion_receipts
  to finbrain_worker using (true) with check (true);

drop policy if exists finbrain_worker_telegram_receipts on public.telegram_update_receipts;
create policy finbrain_worker_telegram_receipts on public.telegram_update_receipts
  to finbrain_worker using (true) with check (true);

create or replace function public.finbrain_audit_tail(chain_name text)
returns text
language plpgsql
security definer
set search_path = ''
as $$
declare result text;
begin
  if chain_name = 'disclosure' then
    select event_hash into result from public.audit_log order by id desc limit 1;
  elsif chain_name = 'workflow' then
    select event_hash into result from public.workflow_audit_log order by id desc limit 1;
  else
    raise exception 'unsupported audit chain';
  end if;
  return coalesce(result, 'genesis');
end;
$$;
revoke execute on function public.finbrain_audit_tail(text) from public, anon, authenticated;
grant execute on function public.finbrain_audit_tail(text) to finbrain_app, finbrain_worker;

create or replace function public.reject_audit_mutation()
returns trigger language plpgsql set search_path = ''
as $$
begin
  if current_user in ('postgres', 'supabase_admin') then
    if tg_op = 'UPDATE' then return new; end if;
    return old;
  end if;
  raise exception 'audit rows are append-only';
end;
$$;

drop trigger if exists audit_log_append_only on public.audit_log;
create trigger audit_log_append_only before update or delete on public.audit_log
for each row execute function public.reject_audit_mutation();

drop trigger if exists workflow_audit_log_append_only on public.workflow_audit_log;
create trigger workflow_audit_log_append_only before update or delete on public.workflow_audit_log
for each row execute function public.reject_audit_mutation();
