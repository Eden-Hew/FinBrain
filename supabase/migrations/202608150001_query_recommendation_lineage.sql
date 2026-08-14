alter table public.conversation_turns
  add column if not exists protected_brief jsonb;

alter table public.process_recommendations
  add column if not exists origin_type text not null default 'process_analysis',
  add column if not exists origin_turn_id bigint
    references public.conversation_turns(id) on delete set null,
  add column if not exists origin_query_hash text;

alter table public.process_recommendations
  drop constraint if exists process_recommendations_origin_type_valid;

alter table public.process_recommendations
  add constraint process_recommendations_origin_type_valid
  check (origin_type in ('process_analysis', 'query_brief', 'verification_gap'));

create index if not exists process_recommendations_origin_turn_idx
  on public.process_recommendations (origin_type, origin_turn_id);

-- These protected artifacts remain backend-only, matching the existing forced-RLS posture.
alter table public.conversation_turns enable row level security;
alter table public.conversation_turns force row level security;
alter table public.process_recommendations enable row level security;
alter table public.process_recommendations force row level security;

revoke all on table public.conversation_turns from anon, authenticated;
revoke all on table public.process_recommendations from anon, authenticated;
