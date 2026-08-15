create table if not exists public.user_roles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  user_role text not null check (
    user_role in ('general_employee', 'finance_ops', 'owner_director', 'compliance')
  ),
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.conversations
  add column if not exists created_by_user_id uuid references auth.users(id) on delete set null;

alter table public.process_recommendations
  add column if not exists created_by_user_id uuid references auth.users(id) on delete set null;

alter table public.audit_log
  add column if not exists actor_ref text not null default 'legacy';

create index if not exists conversations_created_by_user_idx
  on public.conversations (created_by_user_id, updated_at desc);

create index if not exists recommendations_created_by_user_idx
  on public.process_recommendations (created_by_user_id, created_at desc);

create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists user_roles_set_updated_at on public.user_roles;
create trigger user_roles_set_updated_at
before update on public.user_roles
for each row execute function public.set_updated_at();

create or replace function public.custom_access_token_hook(event jsonb)
returns jsonb
language plpgsql
stable
set search_path = ''
as $$
declare
  claims jsonb;
  assigned_role text;
begin
  select role_row.user_role
    into assigned_role
    from public.user_roles as role_row
   where role_row.user_id = (event ->> 'user_id')::uuid
     and role_row.active;

  claims := event -> 'claims';
  claims := jsonb_set(
    claims,
    '{user_role}',
    coalesce(to_jsonb(assigned_role), 'null'::jsonb),
    true
  );
  return jsonb_set(event, '{claims}', claims, true);
end;
$$;

grant usage on schema public to supabase_auth_admin;
grant execute on function public.custom_access_token_hook(jsonb) to supabase_auth_admin;
revoke execute on function public.custom_access_token_hook(jsonb)
  from anon, authenticated, public;

grant select on table public.user_roles to supabase_auth_admin;
revoke all on table public.user_roles from anon, authenticated;

alter table public.user_roles enable row level security;
alter table public.user_roles force row level security;

drop policy if exists "auth hook can read active roles" on public.user_roles;
create policy "auth hook can read active roles"
  on public.user_roles
  for select
  to supabase_auth_admin
  using (true);

alter table public.conversations enable row level security;
alter table public.conversations force row level security;
alter table public.process_recommendations enable row level security;
alter table public.process_recommendations force row level security;
alter table public.audit_log enable row level security;
alter table public.audit_log force row level security;

revoke all on table public.conversations from anon, authenticated;
revoke all on table public.process_recommendations from anon, authenticated;
revoke all on table public.audit_log from anon, authenticated;
