-- Multi-tenancy rollout, slice 2: tokenized_content, token_vault, and
-- protected_token_registry. Tokens are now derived with tenant identity baked into
-- their HMAC input (see security/tokenize.py), so token strings are already unique
-- per (tenant, raw value) — no primary-key changes needed here, just an added
-- tenant_id column for RLS/filtering and a tenant predicate on the user-facing
-- (finbrain_app) policies. Worker policies stay unrestricted: background ingestion
-- (Telegram/email) is still one shared, global identity until Phase 2b gives it
-- real per-tenant credentials.

alter table public.tokenized_content add column if not exists tenant_id uuid;
alter table public.token_vault add column if not exists tenant_id uuid;
alter table public.protected_token_registry add column if not exists tenant_id uuid;

update public.tokenized_content set tenant_id = '00000000-0000-0000-0000-000000000001' where tenant_id is null;
update public.token_vault set tenant_id = '00000000-0000-0000-0000-000000000001' where tenant_id is null;
update public.protected_token_registry set tenant_id = '00000000-0000-0000-0000-000000000001' where tenant_id is null;

alter table public.tokenized_content
  alter column tenant_id set not null,
  add constraint tokenized_content_tenant_fkey foreign key (tenant_id) references public.tenants(id);
alter table public.token_vault
  alter column tenant_id set not null,
  add constraint token_vault_tenant_fkey foreign key (tenant_id) references public.tenants(id);
alter table public.protected_token_registry
  alter column tenant_id set not null,
  add constraint protected_token_registry_tenant_fkey foreign key (tenant_id) references public.tenants(id);

create index if not exists tokenized_content_tenant_idx
  on public.tokenized_content (tenant_id, processing_status, occurred_at desc);
create index if not exists token_vault_tenant_idx on public.token_vault (tenant_id);
create index if not exists protected_token_registry_tenant_idx on public.protected_token_registry (tenant_id);

drop policy if exists finbrain_app_content on public.tokenized_content;
create policy finbrain_app_content on public.tokenized_content to finbrain_app
  using (tenant_id = public.finbrain_tenant_id() and public.finbrain_role() <> '')
  with check (tenant_id = public.finbrain_tenant_id() and public.finbrain_role() <> '');

drop policy if exists finbrain_app_vault on public.token_vault;
create policy finbrain_app_vault on public.token_vault
  for select to finbrain_app
  using (tenant_id = public.finbrain_tenant_id() and allowed_roles ? public.finbrain_role());

drop policy if exists finbrain_app_vault_insert on public.token_vault;
create policy finbrain_app_vault_insert on public.token_vault
  for insert to finbrain_app
  with check (tenant_id = public.finbrain_tenant_id() and public.finbrain_role() <> '');

drop policy if exists finbrain_app_token_registry on public.protected_token_registry;
create policy finbrain_app_token_registry on public.protected_token_registry to finbrain_app
  using (tenant_id = public.finbrain_tenant_id() and public.finbrain_role() <> '')
  with check (tenant_id = public.finbrain_tenant_id() and public.finbrain_role() <> '');

-- finbrain_worker_content / finbrain_worker_vault / finbrain_worker_token_registry
-- are intentionally left unchanged (using (true)) — see comment above.
