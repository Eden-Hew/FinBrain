-- Customer-facing Telegram onboarding and governed overdue reminders.
-- Raw identifiers/contact values stay in the versioned vault; these tables store tokens only.

alter table public.customer_endpoints
  add column if not exists delivery_token text,
  add column if not exists last_interaction_at timestamptz;

alter table public.customer_endpoints
  drop constraint if exists customer_endpoints_channel_check;
alter table public.customer_endpoints
  add constraint customer_endpoints_channel_check check (channel in ('email','phone','telegram'));

update public.customer_endpoints
set delivery_token = endpoint_token
where channel = 'email' and delivery_token is null;

create index if not exists customer_endpoints_delivery_idx
  on public.customer_endpoints (tenant_id, delivery_token)
  where delivery_token is not null;
create index if not exists customer_endpoints_channel_status_idx
  on public.customer_endpoints (tenant_id, channel, verification_status);

create table if not exists public.telegram_onboarding_sessions (
  id bigint generated always as identity primary key,
  tenant_id uuid not null references public.tenants(id),
  telegram_endpoint_token text not null,
  telegram_delivery_token text not null,
  name_token text,
  email_token text,
  phone_token text,
  customer_id bigint references public.customers(id) on delete restrict,
  profile_content_id bigint references public.tokenized_content(id) on delete restrict,
  status text not null default 'awaiting_consent' check (status in (
    'awaiting_consent','awaiting_name','awaiting_gmail','awaiting_phone',
    'reconciling','awaiting_message','completed','review_required','cancelled','failed'
  )),
  failure_code text,
  consented_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, telegram_endpoint_token)
);

create index if not exists telegram_onboarding_tenant_status_idx
  on public.telegram_onboarding_sessions (tenant_id, status, updated_at);

drop trigger if exists telegram_onboarding_set_updated_at
  on public.telegram_onboarding_sessions;
create trigger telegram_onboarding_set_updated_at
before update on public.telegram_onboarding_sessions
for each row execute function public.set_updated_at();

alter table public.telegram_update_receipts
  add column if not exists tenant_id uuid references public.tenants(id),
  add column if not exists customer_id bigint references public.customers(id) on delete restrict,
  add column if not exists onboarding_session_id bigint
    references public.telegram_onboarding_sessions(id) on delete restrict;

update public.telegram_update_receipts
set tenant_id = '00000000-0000-0000-0000-000000000001'
where tenant_id is null;

alter table public.telegram_update_receipts alter column tenant_id set not null;
alter table public.telegram_update_receipts
  drop constraint if exists telegram_update_receipts_status_valid;
alter table public.telegram_update_receipts
  add constraint telegram_update_receipts_status_valid check (status in (
    'received','ignored','drafted','confirmed','protected','ready','failed','cancelled',
    'onboarding','awaiting_input'
  ));
create index if not exists telegram_receipts_tenant_status_idx
  on public.telegram_update_receipts (tenant_id, status, updated_at);

alter table public.einvoice_records
  add column if not exists buyer_email_token text,
  add column if not exists buyer_phone_token text;
create index if not exists einvoice_buyer_email_token_idx
  on public.einvoice_records (tenant_id, buyer_email_token)
  where buyer_email_token is not null;
create index if not exists einvoice_buyer_phone_token_idx
  on public.einvoice_records (tenant_id, buyer_phone_token)
  where buyer_phone_token is not null;

alter table public.outreach_actions
  alter column created_by_user_id drop not null,
  add column if not exists created_by_actor_ref text,
  add column if not exists origin_type text not null default 'manual',
  add column if not exists origin_invoice_id bigint
    references public.einvoice_records(id) on delete restrict,
  add column if not exists scheduled_for timestamptz;

alter table public.outreach_actions
  drop constraint if exists outreach_actions_channel_check;
alter table public.outreach_actions
  add constraint outreach_actions_channel_check check (channel in ('email','telegram'));
alter table public.outreach_actions
  drop constraint if exists outreach_actions_creator_check;
alter table public.outreach_actions
  add constraint outreach_actions_creator_check check (
    created_by_user_id is not null or created_by_actor_ref is not null
  );
create index if not exists outreach_worker_queue_idx
  on public.outreach_actions (tenant_id, channel, status, scheduled_for, created_at)
  where status in ('approved','sending');
create index if not exists outreach_invoice_idx
  on public.outreach_actions (tenant_id, origin_invoice_id, created_at desc)
  where origin_invoice_id is not null;

create table if not exists public.tenant_outreach_policies (
  tenant_id uuid primary key references public.tenants(id),
  telegram_reminders_enabled boolean not null default false,
  grace_days integer not null default 1 check (grace_days between 0 and 365),
  repeat_interval_days integer not null default 7 check (repeat_interval_days between 1 and 365),
  max_reminders integer not null default 3 check (max_reminders between 1 and 20),
  require_approval boolean not null default true,
  policy_version integer not null default 1 check (policy_version > 0),
  updated_by_user_id uuid references auth.users(id) on delete set null,
  updated_at timestamptz not null default now()
);

drop trigger if exists tenant_outreach_policy_set_updated_at
  on public.tenant_outreach_policies;
create trigger tenant_outreach_policy_set_updated_at
before update on public.tenant_outreach_policies
for each row execute function public.set_updated_at();

alter table public.telegram_onboarding_sessions enable row level security;
alter table public.telegram_onboarding_sessions force row level security;
alter table public.tenant_outreach_policies enable row level security;
alter table public.tenant_outreach_policies force row level security;

revoke all on public.telegram_onboarding_sessions, public.tenant_outreach_policies
  from anon, authenticated;
grant select on public.telegram_onboarding_sessions to finbrain_app;
grant select, insert, update on public.telegram_onboarding_sessions to finbrain_worker;
grant select, insert, update on public.tenant_outreach_policies to finbrain_app;
grant select on public.tenant_outreach_policies to finbrain_worker;
grant usage, select on sequence public.telegram_onboarding_sessions_id_seq
  to finbrain_worker;

create policy finbrain_app_telegram_onboarding_read
  on public.telegram_onboarding_sessions for select to finbrain_app
  using (
    tenant_id = public.finbrain_tenant_id()
    and public.finbrain_role() in ('finance_ops','owner_director','compliance')
  );
create policy finbrain_worker_telegram_onboarding
  on public.telegram_onboarding_sessions to finbrain_worker
  using (tenant_id = public.finbrain_tenant_id())
  with check (tenant_id = public.finbrain_tenant_id());

create policy finbrain_app_outreach_policy_read
  on public.tenant_outreach_policies for select to finbrain_app
  using (
    tenant_id = public.finbrain_tenant_id()
    and public.finbrain_role() in ('finance_ops','owner_director','compliance')
  );
create policy finbrain_app_outreach_policy_insert
  on public.tenant_outreach_policies for insert to finbrain_app
  with check (
    tenant_id = public.finbrain_tenant_id()
    and public.finbrain_role() = 'owner_director'
  );
create policy finbrain_app_outreach_policy_update
  on public.tenant_outreach_policies for update to finbrain_app
  using (
    tenant_id = public.finbrain_tenant_id()
    and public.finbrain_role() = 'owner_director'
  )
  with check (
    tenant_id = public.finbrain_tenant_id()
    and public.finbrain_role() = 'owner_director'
  );
create policy finbrain_worker_outreach_policy_read
  on public.tenant_outreach_policies for select to finbrain_worker
  using (tenant_id = public.finbrain_tenant_id());

drop policy if exists finbrain_worker_telegram_receipts
  on public.telegram_update_receipts;
create policy finbrain_worker_telegram_receipts
  on public.telegram_update_receipts to finbrain_worker
  using (tenant_id = public.finbrain_tenant_id())
  with check (tenant_id = public.finbrain_tenant_id());

drop policy if exists finbrain_worker_customer_endpoints on public.customer_endpoints;
create policy finbrain_worker_customer_endpoints
  on public.customer_endpoints to finbrain_worker
  using (tenant_id = public.finbrain_tenant_id())
  with check (tenant_id = public.finbrain_tenant_id());

drop policy if exists finbrain_worker_outreach_actions on public.outreach_actions;
create policy finbrain_worker_outreach_actions
  on public.outreach_actions to finbrain_worker
  using (tenant_id = public.finbrain_tenant_id())
  with check (tenant_id = public.finbrain_tenant_id());

drop policy if exists finbrain_worker_outreach_evidence on public.outreach_evidence;
create policy finbrain_worker_outreach_evidence
  on public.outreach_evidence to finbrain_worker
  using (tenant_id = public.finbrain_tenant_id())
  with check (tenant_id = public.finbrain_tenant_id());
