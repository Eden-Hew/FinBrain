alter table public.tokenized_content
  alter column embedding drop not null,
  add column if not exists source_system text default 'legacy' not null,
  add column if not exists occurred_at timestamptz,
  add column if not exists content_fingerprint text,
  add column if not exists safe_metadata jsonb default '{}'::jsonb not null,
  add column if not exists structured_summary jsonb,
  add column if not exists processing_status text default 'protected' not null,
  add column if not exists processing_error text,
  add column if not exists enrichment_mode text,
  add column if not exists updated_at timestamptz default now() not null;

update public.tokenized_content
set
  source_system = coalesce(record_type, 'legacy'),
  processing_status = case when embedding is null then 'protected' else 'ready' end,
  updated_at = coalesce(created_at, now())
where source_system = 'legacy' or processing_status = 'protected';

alter table public.tokenized_content
  drop constraint if exists tokenized_content_safe_metadata_object,
  add constraint tokenized_content_safe_metadata_object
    check (jsonb_typeof(safe_metadata) = 'object'),
  drop constraint if exists tokenized_content_structured_summary_object,
  add constraint tokenized_content_structured_summary_object
    check (structured_summary is null or jsonb_typeof(structured_summary) = 'object'),
  drop constraint if exists tokenized_content_processing_status_valid,
  add constraint tokenized_content_processing_status_valid
    check (processing_status in ('protected', 'ready', 'failed_enrichment'));

create index if not exists tokenized_content_processing_status_idx
  on public.tokenized_content (processing_status);

create index if not exists tokenized_content_source_system_idx
  on public.tokenized_content (source_system, occurred_at desc);
