-- Phase 6: entity resolution, first cut. A canonical `customers` table resolved
-- by deterministic name normalization (corporate suffix stripped, casing and
-- punctuation collapsed -- see app/services/entity_resolution.py). Wired up for
-- e-invoice buyer names only: that is the one place in the schema where a
-- business name is stored as a plain, structured column rather than PII-protected
-- free text behind a token. Linking a TokenizedContent record's PERSON_/ORG_
-- entity to a customer would require either a new detected+tokenized entity type
-- or an authorized detokenization pass -- a real, separate design decision, not
-- part of this first cut. Embedding-similarity-based fuzzy matching is likewise a
-- documented future step, not built here.

create table if not exists public.customers (
  id bigint generated always as identity primary key,
  tenant_id uuid not null references public.tenants(id),
  canonical_name text not null,
  normalized_name text not null,
  created_at timestamptz default now() not null,
  constraint customers_tenant_normalized_unique unique (tenant_id, normalized_name)
);

create index if not exists customers_tenant_idx on public.customers (tenant_id);

alter table public.customers enable row level security;
alter table public.customers force row level security;
revoke all on table public.customers from anon, authenticated;

grant select, insert, update on public.customers to finbrain_app;

drop policy if exists finbrain_customers on public.customers;
create policy finbrain_customers on public.customers to finbrain_app
  using (tenant_id = public.finbrain_tenant_id() and public.finbrain_role() <> '')
  with check (tenant_id = public.finbrain_tenant_id() and public.finbrain_role() <> '');

alter table public.einvoice_records
  add column if not exists buyer_customer_id bigint references public.customers(id);

create index if not exists einvoice_records_buyer_customer_idx
  on public.einvoice_records (buyer_customer_id);
