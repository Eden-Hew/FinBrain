create table if not exists public.conversations (
  id text primary key,
  status text default 'active' not null check (status in ('active', 'expired', 'deleted')),
  created_at timestamptz default now() not null,
  updated_at timestamptz default now() not null,
  expires_at timestamptz not null
);

create table if not exists public.conversation_turns (
  id bigint generated always as identity primary key,
  conversation_id text not null references public.conversations(id) on delete cascade,
  sequence_number integer not null check (sequence_number > 0),
  user_role text not null,
  protected_question text not null,
  protected_answer text not null,
  query_intent text not null,
  source_systems jsonb not null check (jsonb_typeof(source_systems) = 'array'),
  reasoning_mode text not null,
  insufficient_evidence boolean not null,
  created_at timestamptz default now() not null,
  constraint conversation_turn_sequence_unique unique (conversation_id, sequence_number)
);

create table if not exists public.conversation_turn_citations (
  id bigint generated always as identity primary key,
  turn_id bigint not null references public.conversation_turns(id) on delete cascade,
  ordinal integer not null check (ordinal > 0),
  tokenized_content_id bigint not null references public.tokenized_content(id) on delete restrict,
  constraint conversation_citation_ordinal_unique unique (turn_id, ordinal),
  constraint conversation_citation_record_unique unique (turn_id, tokenized_content_id)
);

create index if not exists conversation_turn_sequence_idx
  on public.conversation_turns (conversation_id, sequence_number desc);
create index if not exists conversation_expiry_idx
  on public.conversations (status, expires_at);
create index if not exists conversation_citation_turn_idx
  on public.conversation_turn_citations (turn_id, ordinal);

alter table public.conversations enable row level security;
alter table public.conversation_turns enable row level security;
alter table public.conversation_turn_citations enable row level security;
alter table public.conversations force row level security;
alter table public.conversation_turns force row level security;
alter table public.conversation_turn_citations force row level security;

revoke all on table public.conversations from anon, authenticated;
revoke all on table public.conversation_turns from anon, authenticated;
revoke all on table public.conversation_turn_citations from anon, authenticated;
