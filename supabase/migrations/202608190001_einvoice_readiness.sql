create table if not exists public.einvoice_records (
  id bigint generated always as identity primary key,
  supplier_name text not null,
  supplier_tin text,
  buyer_name text,
  invoice_no text,
  issue_date date,
  currency text,
  tax_type text,
  tax_rate text,
  total_amount numeric(12, 2) not null,
  status text default 'pending' not null
    check (status in ('review', 'pending', 'submitted', 'validated')),
  source_record_id text,
  created_at timestamptz default now() not null,
  updated_at timestamptz default now() not null
);

create table if not exists public.einvoice_outreach_drafts (
  id bigint generated always as identity primary key,
  einvoice_record_id bigint not null references public.einvoice_records(id) on delete cascade,
  channel text not null check (channel in ('telegram', 'email')),
  draft_text text not null,
  status text default 'draft' not null
    check (status in ('draft', 'approved', 'rejected')),
  created_by_user_id uuid,
  decided_by_user_id uuid,
  created_at timestamptz default now() not null,
  decided_at timestamptz
);

create index if not exists einvoice_records_status_idx
  on public.einvoice_records (status, created_at desc);
create index if not exists einvoice_outreach_drafts_status_idx
  on public.einvoice_outreach_drafts (status, created_at desc);
create index if not exists einvoice_outreach_drafts_record_idx
  on public.einvoice_outreach_drafts (einvoice_record_id);

alter table public.einvoice_records enable row level security;
alter table public.einvoice_outreach_drafts enable row level security;

alter table public.einvoice_records force row level security;
alter table public.einvoice_outreach_drafts force row level security;

revoke all on table public.einvoice_records from anon, authenticated;
revoke all on table public.einvoice_outreach_drafts from anon, authenticated;

grant select, insert, update on public.einvoice_records to finbrain_app;
grant select, insert, update on public.einvoice_outreach_drafts to finbrain_app;

drop policy if exists finbrain_einvoice_records on public.einvoice_records;
create policy finbrain_einvoice_records on public.einvoice_records
  for select to finbrain_app using (true);

drop policy if exists finbrain_einvoice_records_write on public.einvoice_records;
create policy finbrain_einvoice_records_write on public.einvoice_records
  for insert to finbrain_app with check (true);

drop policy if exists finbrain_outreach_read on public.einvoice_outreach_drafts;
create policy finbrain_outreach_read on public.einvoice_outreach_drafts
  for select to finbrain_app using (true);

drop policy if exists finbrain_outreach_insert on public.einvoice_outreach_drafts;
create policy finbrain_outreach_insert on public.einvoice_outreach_drafts
  for insert to finbrain_app with check (true);

drop policy if exists finbrain_outreach_decide on public.einvoice_outreach_drafts;
create policy finbrain_outreach_decide on public.einvoice_outreach_drafts
  for update to finbrain_app
  using (public.finbrain_role() = 'owner_director')
  with check (public.finbrain_role() = 'owner_director');
