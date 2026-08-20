create table public.customer_aliases (
  id bigint generated always as identity primary key,
  tenant_id uuid not null references public.tenants(id),
  customer_id bigint not null references public.customers(id) on delete restrict,
  alias_token text not null,
  alias_type text not null,
  match_status text not null check (match_status in ('verified','probable','ambiguous','rejected')),
  confidence double precision not null check (confidence between 0 and 1),
  source_system text not null,
  source_record_id text,
  created_by_user_id uuid,
  reviewed_by_user_id uuid,
  created_at timestamptz not null default now(),
  reviewed_at timestamptz,
  constraint customer_alias_unique unique (tenant_id, customer_id, alias_token)
);
create index customer_alias_lookup_idx on public.customer_aliases
  (tenant_id, alias_token, match_status);

create table public.customer_record_links (
  id bigint generated always as identity primary key,
  tenant_id uuid not null references public.tenants(id),
  customer_id bigint not null references public.customers(id) on delete restrict,
  tokenized_content_id bigint not null references public.tokenized_content(id) on delete restrict,
  alias_id bigint references public.customer_aliases(id) on delete restrict,
  match_status text not null check (match_status in ('verified','probable','ambiguous','rejected')),
  confidence double precision not null check (confidence between 0 and 1),
  match_basis text not null,
  created_by_user_id uuid,
  reviewed_by_user_id uuid,
  created_at timestamptz not null default now(),
  reviewed_at timestamptz,
  constraint customer_record_link_unique
    unique (tenant_id, customer_id, tokenized_content_id, match_basis)
);
create index customer_record_links_customer_idx on public.customer_record_links
  (tenant_id, customer_id, match_status, created_at desc);
create index customer_record_links_content_idx on public.customer_record_links
  (tenant_id, tokenized_content_id);

alter table public.customer_aliases enable row level security;
alter table public.customer_aliases force row level security;
alter table public.customer_record_links enable row level security;
alter table public.customer_record_links force row level security;
revoke all on public.customer_aliases, public.customer_record_links from anon, authenticated;
grant select, insert, update on public.customer_aliases, public.customer_record_links to finbrain_app;
grant select, insert, update on public.customer_aliases, public.customer_record_links to finbrain_worker;
grant usage, select on sequence public.customers_id_seq,
  public.customer_aliases_id_seq, public.customer_record_links_id_seq
  to finbrain_app, finbrain_worker;

create policy finbrain_customer_aliases on public.customer_aliases to finbrain_app
  using (tenant_id = public.finbrain_tenant_id() and public.finbrain_role() <> '')
  with check (tenant_id = public.finbrain_tenant_id() and public.finbrain_role() in ('finance_ops','owner_director','compliance'));
create policy finbrain_customer_links on public.customer_record_links to finbrain_app
  using (tenant_id = public.finbrain_tenant_id() and public.finbrain_role() <> '')
  with check (tenant_id = public.finbrain_tenant_id() and public.finbrain_role() in ('finance_ops','owner_director','compliance'));
create policy finbrain_worker_customer_aliases on public.customer_aliases to finbrain_worker
  using (true) with check (true);
create policy finbrain_worker_customer_links on public.customer_record_links to finbrain_worker
  using (true) with check (true);
