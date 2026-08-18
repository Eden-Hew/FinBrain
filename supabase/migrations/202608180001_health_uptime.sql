alter table public.integration_status
  add column if not exists started_at timestamptz;
