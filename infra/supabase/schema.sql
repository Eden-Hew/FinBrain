create extension if not exists vector;

create table if not exists tokenized_content (
  id bigint generated always as identity primary key,
  source_record_id text unique not null,
  content_text text not null,
  embedding vector(768) not null,
  record_type text,
  summary text,
  created_at timestamptz default now() not null
);

create table if not exists token_vault (
  token text primary key,
  entity_type text not null,
  encrypted_value bytea not null,
  nonce bytea not null,
  allowed_roles text[] not null,
  sensitivity text default 'high' not null,
  source_record_id text not null,
  created_at timestamptz default now() not null
);

create table if not exists audit_log (
  id bigint generated always as identity primary key,
  prev_hash text not null,
  event_hash text not null,
  user_role text not null,
  token text not null,
  authorized boolean not null,
  query_hash text not null,
  ts timestamptz default now() not null
);

create index if not exists tokenized_content_embedding_idx
  on tokenized_content using hnsw (embedding vector_cosine_ops);

