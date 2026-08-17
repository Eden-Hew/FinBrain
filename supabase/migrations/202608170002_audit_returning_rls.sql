create or replace function public.finbrain_actor_ref()
returns text language sql stable set search_path = ''
as $$ select coalesce(current_setting('app.actor_ref', true), '') $$;

grant execute on function public.finbrain_actor_ref() to finbrain_app, finbrain_worker;

drop policy if exists finbrain_audit_compliance_read on public.audit_log;
drop policy if exists finbrain_audit_read on public.audit_log;
create policy finbrain_audit_read on public.audit_log
  for select to finbrain_app
  using (
    public.finbrain_role() = 'compliance'
    or actor_ref = public.finbrain_actor_ref()
  );

drop policy if exists finbrain_workflow_compliance_read on public.workflow_audit_log;
drop policy if exists finbrain_workflow_read on public.workflow_audit_log;
create policy finbrain_workflow_read on public.workflow_audit_log
  for select to finbrain_app
  using (
    public.finbrain_role() = 'compliance'
    or actor_ref = public.finbrain_actor_ref()
  );

drop policy if exists finbrain_worker_audit_read on public.audit_log;
create policy finbrain_worker_audit_read on public.audit_log
  for select to finbrain_worker using (true);

drop policy if exists finbrain_worker_workflow_read on public.workflow_audit_log;
create policy finbrain_worker_workflow_read on public.workflow_audit_log
  for select to finbrain_worker using (true);
