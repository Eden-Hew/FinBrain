alter table public.conversations
  add column context_customer_id bigint references public.customers(id) on delete set null,
  add column context_updated_at timestamptz;
create index conversations_customer_context_idx on public.conversations
  (tenant_id, context_customer_id) where context_customer_id is not null;
