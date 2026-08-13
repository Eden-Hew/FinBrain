create table if not exists public.telegram_update_receipts (
  update_id bigint primary key,
  message_ref_hash text unique,
  actor_ref text not null,
  source_record_id text,
  update_kind text not null,
  status text default 'received' not null,
  failure_code text,
  created_at timestamptz default now() not null,
  updated_at timestamptz default now() not null,
  constraint telegram_update_receipts_status_valid check (
    status in ('received', 'ignored', 'drafted', 'confirmed', 'protected', 'ready', 'failed', 'cancelled')
  )
);

create table if not exists public.integration_status (
  integration_key text primary key,
  status text not null,
  mode text not null,
  detector_ready boolean default false not null,
  last_heartbeat_at timestamptz default now() not null,
  last_update_at timestamptz,
  failure_code text,
  constraint integration_status_value_valid check (
    status in ('starting', 'healthy', 'degraded', 'stopped')
  )
);

create index if not exists telegram_update_receipts_source_record_idx
  on public.telegram_update_receipts (source_record_id);

create index if not exists telegram_update_receipts_actor_created_idx
  on public.telegram_update_receipts (actor_ref, created_at desc);

create index if not exists telegram_update_receipts_status_updated_idx
  on public.telegram_update_receipts (status, updated_at desc);

create index if not exists tokenized_content_source_created_idx
  on public.tokenized_content (source_system, created_at desc);
