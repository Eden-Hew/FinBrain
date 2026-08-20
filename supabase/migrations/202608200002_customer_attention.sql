create table public.customer_attention_snapshots (
  id bigint generated always as identity primary key,
  tenant_id uuid not null references public.tenants(id),
  customer_id bigint not null references public.customers(id) on delete restrict,
  score integer not null check (score between 0 and 100),
  priority text not null check (priority in ('urgent','high','monitoring','healthy')),
  calculation_version text not null,
  input_fingerprint text not null,
  calculated_at timestamptz not null default now(),
  constraint customer_attention_input_unique unique (tenant_id, customer_id, input_fingerprint)
);
create index customer_attention_latest_idx on public.customer_attention_snapshots
  (tenant_id, customer_id, calculated_at desc, id desc);

create table public.customer_attention_signals (
  id bigint generated always as identity primary key,
  tenant_id uuid not null references public.tenants(id),
  snapshot_id bigint not null references public.customer_attention_snapshots(id) on delete cascade,
  signal_type text not null,
  points integer not null check (points >= 0),
  label text not null,
  freshness text not null check (freshness in ('current','aging','stale','undated')),
  confidence double precision not null check (confidence between 0 and 1),
  tokenized_content_id bigint references public.tokenized_content(id) on delete restrict,
  einvoice_record_id bigint references public.einvoice_records(id) on delete restrict,
  occurred_at timestamptz,
  details jsonb not null default '{}'::jsonb,
  check (tokenized_content_id is not null or einvoice_record_id is not null)
);
create index customer_attention_signal_snapshot_idx on public.customer_attention_signals
  (tenant_id, snapshot_id);

alter table public.customer_attention_snapshots enable row level security;
alter table public.customer_attention_snapshots force row level security;
alter table public.customer_attention_signals enable row level security;
alter table public.customer_attention_signals force row level security;
revoke all on public.customer_attention_snapshots, public.customer_attention_signals from anon, authenticated;
grant select, insert on public.customer_attention_snapshots, public.customer_attention_signals to finbrain_app;
grant select, insert on public.customer_attention_snapshots, public.customer_attention_signals to finbrain_worker;
grant usage, select on sequence public.customer_attention_snapshots_id_seq,
  public.customer_attention_signals_id_seq to finbrain_app, finbrain_worker;
create policy finbrain_attention_snapshots on public.customer_attention_snapshots to finbrain_app
  using (tenant_id = public.finbrain_tenant_id() and public.finbrain_role() <> '')
  with check (tenant_id = public.finbrain_tenant_id() and public.finbrain_role() in ('finance_ops','owner_director','compliance'));
create policy finbrain_attention_signals on public.customer_attention_signals to finbrain_app
  using (tenant_id = public.finbrain_tenant_id() and public.finbrain_role() <> '')
  with check (tenant_id = public.finbrain_tenant_id() and public.finbrain_role() in ('finance_ops','owner_director','compliance'));
create policy finbrain_worker_attention_snapshots on public.customer_attention_snapshots to finbrain_worker using (true) with check (true);
create policy finbrain_worker_attention_signals on public.customer_attention_signals to finbrain_worker using (true) with check (true);
