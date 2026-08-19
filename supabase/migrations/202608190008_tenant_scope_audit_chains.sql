-- Multi-tenancy rollout, slice 3: audit_log and workflow_audit_log become
-- per-tenant hash chains instead of one global chain. tenant_id is nullable —
-- NULL is reserved for genuinely system-level events (e.g. vault key rotation)
-- that aren't owned by any one tenant. Every tenant-owned event (recommendations,
-- einvoice, disclosure) must pass its real tenant_id so its chain can be verified
-- independently of any other tenant's, and so a compliance user at tenant A can
-- never see tenant B's audit trail.

alter table public.audit_log add column if not exists tenant_id uuid references public.tenants(id);
alter table public.workflow_audit_log add column if not exists tenant_id uuid references public.tenants(id);

-- Existing rows predate multi-tenancy entirely; they become part of the
-- default tenant's chain rather than the system chain, since they were in
-- fact all actions taken within the single pre-existing workspace.
update public.audit_log set tenant_id = '00000000-0000-0000-0000-000000000001' where tenant_id is null;
update public.workflow_audit_log set tenant_id = '00000000-0000-0000-0000-000000000001' where tenant_id is null;

create index if not exists audit_log_tenant_idx on public.audit_log (tenant_id, id);
create index if not exists workflow_audit_log_tenant_idx on public.workflow_audit_log (tenant_id, id);

-- finbrain_audit_tail gains a tenant_id parameter (nullable, for the system chain)
-- and filters the "tail" lookup to that one chain instead of the whole table.
-- Drop the old single-argument overload so nothing can accidentally call it and
-- read across all tenants' chains at once.
drop function if exists public.finbrain_audit_tail(text);

create or replace function public.finbrain_audit_tail(chain_name text, for_tenant_id uuid)
returns text language plpgsql security definer set search_path = ''
as $$
declare result text;
begin
  if chain_name = 'disclosure' then
    select event_hash into result from public.audit_log
      where tenant_id is not distinct from for_tenant_id
      order by id desc limit 1;
  elsif chain_name = 'workflow' then
    select event_hash into result from public.workflow_audit_log
      where tenant_id is not distinct from for_tenant_id
      order by id desc limit 1;
  else raise exception 'unsupported audit chain'; end if;
  return coalesce(result, 'genesis');
end;
$$;

grant execute on function public.finbrain_audit_tail(text, uuid) to finbrain_app, finbrain_worker;

drop policy if exists finbrain_audit_read on public.audit_log;
create policy finbrain_audit_read on public.audit_log for select to finbrain_app
  using (
    (tenant_id = public.finbrain_tenant_id() or tenant_id is null)
    and (public.finbrain_role() = 'compliance' or actor_ref = public.finbrain_actor_ref())
  );

drop policy if exists finbrain_audit_insert on public.audit_log;
create policy finbrain_audit_insert on public.audit_log
  for insert to finbrain_app
  with check (tenant_id = public.finbrain_tenant_id() and public.finbrain_role() <> '');

drop policy if exists finbrain_workflow_read on public.workflow_audit_log;
create policy finbrain_workflow_read on public.workflow_audit_log for select to finbrain_app
  using (
    (tenant_id = public.finbrain_tenant_id() or tenant_id is null)
    and (public.finbrain_role() = 'compliance' or actor_ref = public.finbrain_actor_ref())
  );

drop policy if exists finbrain_workflow_insert on public.workflow_audit_log;
create policy finbrain_workflow_insert on public.workflow_audit_log
  for insert to finbrain_app
  with check (tenant_id = public.finbrain_tenant_id() and public.finbrain_role() <> '');

-- Worker insert policies (finbrain_worker_audit_insert / finbrain_worker_workflow_insert)
-- are intentionally left as `with check (true)` — the vault-rotation worker writes
-- system-level events with tenant_id = NULL, which these policies must still allow.
