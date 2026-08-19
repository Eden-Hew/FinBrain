-- Multi-tenancy foundation: tenants table, tenant-scoped membership, and the
-- finbrain_tenant_id() RLS helper. Every existing row backfills to one 'default'
-- tenant so this migration is zero-data-loss for the current single-org deployment.

create table if not exists public.tenants (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  slug text not null unique,
  created_at timestamptz not null default now()
);

insert into public.tenants (id, name, slug)
values ('00000000-0000-0000-0000-000000000001', 'Default Workspace', 'default')
on conflict (slug) do nothing;

-- user_roles: add tenant_id, backfill, then switch the primary key to
-- (user_id, tenant_id) so a user can belong to more than one tenant.
alter table public.user_roles
  add column if not exists tenant_id uuid references public.tenants(id);

update public.user_roles
  set tenant_id = '00000000-0000-0000-0000-000000000001'
  where tenant_id is null;

alter table public.user_roles
  alter column tenant_id set not null;

alter table public.user_roles drop constraint if exists user_roles_pkey;
alter table public.user_roles add primary key (user_id, tenant_id);

create or replace function public.finbrain_tenant_id()
returns uuid language sql stable set search_path = ''
as $$ select nullif(current_setting('app.tenant_id', true), '')::uuid $$;

grant execute on function public.finbrain_tenant_id() to finbrain_app, finbrain_worker;

grant select on table public.tenants to finbrain_app, finbrain_worker;
alter table public.tenants enable row level security;
alter table public.tenants force row level security;
revoke all on table public.tenants from anon, authenticated;

drop policy if exists finbrain_tenants_read on public.tenants;
create policy finbrain_tenants_read on public.tenants
  for select to finbrain_app, finbrain_worker using (true);

-- Auth hook now also injects tenant_id (a user's first active membership --
-- multi-tenant-per-user *switching* is a later UI feature, not required here).
create or replace function public.custom_access_token_hook(event jsonb)
returns jsonb
language plpgsql
stable
set search_path = ''
as $$
declare
  claims jsonb;
  assigned_role text;
  assigned_tenant uuid;
begin
  select role_row.user_role, role_row.tenant_id
    into assigned_role, assigned_tenant
    from public.user_roles as role_row
   where role_row.user_id = (event ->> 'user_id')::uuid
     and role_row.active
   order by role_row.created_at
   limit 1;

  claims := event -> 'claims';
  claims := jsonb_set(
    claims,
    '{user_role}',
    coalesce(to_jsonb(assigned_role), 'null'::jsonb),
    true
  );
  claims := jsonb_set(
    claims,
    '{tenant_id}',
    coalesce(to_jsonb(assigned_tenant), 'null'::jsonb),
    true
  );
  return jsonb_set(event, '{claims}', claims, true);
end;
$$;
