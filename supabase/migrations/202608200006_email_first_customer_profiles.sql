-- Email-first customer profiles are additive. Existing customers remain confirmed.
alter table public.customers
  add column profile_status text not null default 'confirmed'
    check(profile_status in ('provisional','confirmed')),
  add column identity_review_status text not null default 'clear'
    check(identity_review_status in ('clear','review_required')),
  add column profile_origin text not null default 'manual'
    check(profile_origin in ('manual','einvoice','email')),
  add column primary_name_token text;

alter table public.customer_endpoints
  add column origin text not null default 'manual'
    check(origin in ('manual','inbound_email'));

do $$
begin
  if exists (
    select 1 from public.customer_endpoints
    group by tenant_id, channel, endpoint_token
    having count(*) > 1
  ) then
    raise exception 'duplicate customer endpoint ownership must be resolved before migration';
  end if;
end $$;

alter table public.customer_endpoints
  drop constraint customer_endpoints_tenant_id_customer_id_channel_endpoint_t_key;
alter table public.customer_endpoints
  add constraint customer_endpoint_tenant_channel_token_unique
  unique(tenant_id,channel,endpoint_token);

create table public.customer_identity_claims (
  id bigint generated always as identity primary key,
  tenant_id uuid not null references public.tenants(id),
  customer_id bigint not null references public.customers(id) on delete restrict,
  endpoint_id bigint not null references public.customer_endpoints(id) on delete restrict,
  identity_token text not null,
  claim_basis text not null check(claim_basis in ('display_name','self_identification')),
  confidence double precision not null check(confidence >= 0 and confidence <= 1),
  evidence_content_id bigint not null references public.tokenized_content(id) on delete restrict,
  status text not null default 'observed'
    check(status in ('observed','accepted','rejected','conflicting')),
  occurrence_count integer not null default 1 check(occurrence_count > 0),
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  reviewed_by_user_id uuid,
  reviewed_at timestamptz,
  unique(tenant_id,customer_id,endpoint_id,identity_token,claim_basis)
);
create index customer_identity_claims_review_idx
  on public.customer_identity_claims(tenant_id,customer_id,status,last_seen_at desc);

alter table public.customer_identity_claims enable row level security;
alter table public.customer_identity_claims force row level security;
revoke all on public.customer_identity_claims from anon,authenticated;
grant select,insert,update on public.customer_identity_claims to finbrain_app,finbrain_worker;
grant usage,select on sequence public.customer_identity_claims_id_seq to finbrain_app,finbrain_worker;

create policy finbrain_customer_identity_claims_read on public.customer_identity_claims
  for select to finbrain_app
  using(tenant_id=public.finbrain_tenant_id() and public.finbrain_role() in ('finance_ops','owner_director','compliance'));
create policy finbrain_customer_identity_claims_owner_update on public.customer_identity_claims
  for update to finbrain_app
  using(tenant_id=public.finbrain_tenant_id() and public.finbrain_role()='owner_director')
  with check(tenant_id=public.finbrain_tenant_id() and public.finbrain_role()='owner_director');
create policy finbrain_worker_customer_identity_claims on public.customer_identity_claims
  to finbrain_worker using(tenant_id=public.finbrain_tenant_id())
  with check(tenant_id=public.finbrain_tenant_id());

-- The email worker now creates and updates only profiles in its scoped tenant.
grant select,insert,update on public.customers to finbrain_worker;
grant usage,select on sequence public.customers_id_seq to finbrain_worker;
create policy finbrain_worker_customers on public.customers to finbrain_worker
  using(tenant_id=public.finbrain_tenant_id())
  with check(tenant_id=public.finbrain_tenant_id());

alter table public.email_ingestion_receipts
  drop constraint email_ingestion_receipts_correlation_status_check,
  add constraint email_ingestion_receipts_correlation_status_check
    check(correlation_status in ('correlated','ambiguous','identity_conflict'));

alter table public.email_reply_correlations
  drop constraint email_reply_correlations_status_check,
  add constraint email_reply_correlations_status_check
    check(status in ('correlated','ambiguous','identity_conflict'));
