create table if not exists public.structured_ingestion_batches (
  batch_ref text primary key,
  schema_name text not null,
  origin_channel text not null,
  status text not null,
  total_rows integer not null check (total_rows >= 0),
  valid_rows integer not null check (valid_rows >= 0),
  failed_rows integer not null check (failed_rows >= 0),
  protected_rows integer not null check (protected_rows >= 0),
  ready_rows integer not null check (ready_rows >= 0),
  failure_code text,
  created_at timestamptz default now() not null,
  updated_at timestamptz default now() not null,
  constraint structured_ingestion_batch_status_valid
    check (status in ('validated', 'protecting', 'enriching', 'ready', 'partial', 'failed')),
  constraint structured_ingestion_batch_counts_valid
    check (
      valid_rows <= total_rows
      and protected_rows <= valid_rows
      and ready_rows <= protected_rows
    )
);

create index if not exists structured_ingestion_status_created_idx
  on public.structured_ingestion_batches (status, created_at desc);

alter table public.structured_ingestion_batches enable row level security;
alter table public.structured_ingestion_batches force row level security;

revoke all on table public.structured_ingestion_batches from anon, authenticated;
