alter table public.email_ingestion_receipts
  add column customer_id bigint references public.customers(id),
  add column outreach_action_id text references public.outreach_actions(id),
  add column in_reply_to_ref_hash text,
  add column correlation_status text check(correlation_status in ('correlated','ambiguous')),
  add column correlated_at timestamptz;
create index email_receipt_outreach_idx on public.email_ingestion_receipts(outreach_action_id)
  where outreach_action_id is not null;

create table public.email_reply_correlations (
  id bigint generated always as identity primary key,
  tenant_id uuid not null references public.tenants(id),
  email_receipt_ref_hash text not null references public.email_ingestion_receipts(message_ref_hash),
  outreach_action_id text not null references public.outreach_actions(id),
  matched_reference_hash text not null,
  customer_id bigint not null references public.customers(id),
  tokenized_content_id bigint not null references public.tokenized_content(id),
  status text not null default 'correlated' check(status in ('correlated','ambiguous')),
  created_at timestamptz not null default now(),
  unique(email_receipt_ref_hash,outreach_action_id)
);
create index email_reply_customer_idx on public.email_reply_correlations
  (tenant_id,customer_id,created_at desc);
alter table public.email_reply_correlations enable row level security;
alter table public.email_reply_correlations force row level security;
revoke all on public.email_reply_correlations from anon,authenticated;
grant select on public.email_reply_correlations to finbrain_app;
grant select,insert on public.email_reply_correlations to finbrain_worker;
grant update on public.email_ingestion_receipts to finbrain_worker;
grant usage,select on sequence public.email_reply_correlations_id_seq to finbrain_worker;
create policy finbrain_email_reply_read on public.email_reply_correlations to finbrain_app
  for select using(tenant_id=public.finbrain_tenant_id() and public.finbrain_role()<>'');
create policy finbrain_email_reply_worker on public.email_reply_correlations to finbrain_worker
  using(true) with check(true);
