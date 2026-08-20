create table public.customer_endpoints (
 id bigint generated always as identity primary key, tenant_id uuid not null references public.tenants(id),
 customer_id bigint not null references public.customers(id) on delete restrict, channel text not null check(channel in ('email','telegram')),
 endpoint_token text not null, verification_status text not null check(verification_status in ('observed','verified','revoked')),
 verified_by_user_id uuid, verified_at timestamptz, created_at timestamptz not null default now(),
 unique(tenant_id,customer_id,channel,endpoint_token)
);
create table public.outreach_actions (
 id text primary key, tenant_id uuid not null references public.tenants(id), customer_id bigint not null references public.customers(id),
 customer_endpoint_id bigint not null references public.customer_endpoints(id), channel text not null check(channel='email'),
 protected_subject text not null, protected_body text not null,
 status text not null check(status in ('draft','pending_approval','approved','sending','sent','failed','delivery_unknown','replied','rejected','cancelled')),
 idempotency_key text not null, created_by_user_id uuid not null, approved_by_user_id uuid,
 approved_at timestamptz, send_started_at timestamptz, sent_at timestamptz, replied_at timestamptz,
 provider_message_ref_hash text, failure_code text, attempt_count integer not null default 0,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 unique(tenant_id,idempotency_key), unique(tenant_id,provider_message_ref_hash)
);
create table public.outreach_evidence (
 id bigint generated always as identity primary key, tenant_id uuid not null references public.tenants(id),
 outreach_action_id text not null references public.outreach_actions(id) on delete cascade,
 tokenized_content_id bigint not null references public.tokenized_content(id) on delete restrict,
 purpose text not null default 'supporting', unique(outreach_action_id,tokenized_content_id)
);
create index customer_endpoints_customer_idx on public.customer_endpoints(tenant_id,customer_id,verification_status);
create index outreach_queue_idx on public.outreach_actions(status,created_at) where status in ('approved','sending');
create index outreach_customer_idx on public.outreach_actions(tenant_id,customer_id,created_at desc);
alter table public.customer_endpoints enable row level security; alter table public.customer_endpoints force row level security;
alter table public.outreach_actions enable row level security; alter table public.outreach_actions force row level security;
alter table public.outreach_evidence enable row level security; alter table public.outreach_evidence force row level security;
revoke all on public.customer_endpoints,public.outreach_actions,public.outreach_evidence from anon,authenticated;
grant select,insert,update on public.customer_endpoints,public.outreach_actions,public.outreach_evidence to finbrain_app;
grant select,insert,update on public.customer_endpoints,public.outreach_actions,public.outreach_evidence to finbrain_worker;
grant usage,select on sequence public.customer_endpoints_id_seq,public.outreach_evidence_id_seq to finbrain_app,finbrain_worker;
create policy finbrain_customer_endpoints_read on public.customer_endpoints to finbrain_app
  for select using(tenant_id=public.finbrain_tenant_id() and public.finbrain_role() in ('finance_ops','owner_director'));
create policy finbrain_customer_endpoints_insert on public.customer_endpoints to finbrain_app
  for insert with check(tenant_id=public.finbrain_tenant_id() and public.finbrain_role() in ('finance_ops','owner_director'));
create policy finbrain_customer_endpoints_update on public.customer_endpoints to finbrain_app
  for update using(tenant_id=public.finbrain_tenant_id() and public.finbrain_role()='owner_director')
  with check(tenant_id=public.finbrain_tenant_id() and public.finbrain_role()='owner_director');
create policy finbrain_outreach_actions_read on public.outreach_actions to finbrain_app
  for select using(tenant_id=public.finbrain_tenant_id() and public.finbrain_role() in ('finance_ops','owner_director','compliance'));
create policy finbrain_outreach_actions_insert on public.outreach_actions to finbrain_app
  for insert with check(tenant_id=public.finbrain_tenant_id() and public.finbrain_role() in ('finance_ops','owner_director') and status='draft');
create policy finbrain_outreach_actions_update on public.outreach_actions to finbrain_app
  for update using(tenant_id=public.finbrain_tenant_id() and public.finbrain_role() in ('finance_ops','owner_director'))
  with check(tenant_id=public.finbrain_tenant_id() and (
    public.finbrain_role()='owner_director' or
    (public.finbrain_role()='finance_ops' and status in ('pending_approval','cancelled'))
  ));
create policy finbrain_outreach_evidence on public.outreach_evidence to finbrain_app using(tenant_id=public.finbrain_tenant_id()) with check(tenant_id=public.finbrain_tenant_id());
create policy finbrain_worker_customer_endpoints on public.customer_endpoints to finbrain_worker using(true) with check(true);
create policy finbrain_worker_outreach_actions on public.outreach_actions to finbrain_worker using(true) with check(true);
create policy finbrain_worker_outreach_evidence on public.outreach_evidence to finbrain_worker using(true) with check(true);
