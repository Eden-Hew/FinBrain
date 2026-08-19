-- Multi-tenancy rollout, slice 1: conversations, process_recommendations, and
-- einvoice_records families. Denormalizes tenant_id onto every table (including
-- FK-linked children) rather than relying solely on transitive RLS through the
-- parent, and appends "and tenant_id = public.finbrain_tenant_id()" to every
-- existing policy. Backfills every existing row to the default tenant.

alter table public.conversations add column if not exists tenant_id uuid;
alter table public.conversation_turns add column if not exists tenant_id uuid;
alter table public.conversation_turn_citations add column if not exists tenant_id uuid;
alter table public.process_recommendations add column if not exists tenant_id uuid;
alter table public.recommendation_evidence add column if not exists tenant_id uuid;
alter table public.recommendation_decisions add column if not exists tenant_id uuid;
alter table public.einvoice_records add column if not exists tenant_id uuid;
alter table public.einvoice_outreach_drafts add column if not exists tenant_id uuid;

update public.conversations set tenant_id = '00000000-0000-0000-0000-000000000001' where tenant_id is null;
update public.conversation_turns set tenant_id = '00000000-0000-0000-0000-000000000001' where tenant_id is null;
update public.conversation_turn_citations set tenant_id = '00000000-0000-0000-0000-000000000001' where tenant_id is null;
update public.process_recommendations set tenant_id = '00000000-0000-0000-0000-000000000001' where tenant_id is null;
update public.recommendation_evidence set tenant_id = '00000000-0000-0000-0000-000000000001' where tenant_id is null;
update public.recommendation_decisions set tenant_id = '00000000-0000-0000-0000-000000000001' where tenant_id is null;
update public.einvoice_records set tenant_id = '00000000-0000-0000-0000-000000000001' where tenant_id is null;
update public.einvoice_outreach_drafts set tenant_id = '00000000-0000-0000-0000-000000000001' where tenant_id is null;

alter table public.conversations
  alter column tenant_id set not null,
  add constraint conversations_tenant_fkey foreign key (tenant_id) references public.tenants(id);
alter table public.conversation_turns
  alter column tenant_id set not null,
  add constraint conversation_turns_tenant_fkey foreign key (tenant_id) references public.tenants(id);
alter table public.conversation_turn_citations
  alter column tenant_id set not null,
  add constraint conversation_turn_citations_tenant_fkey foreign key (tenant_id) references public.tenants(id);
alter table public.process_recommendations
  alter column tenant_id set not null,
  add constraint process_recommendations_tenant_fkey foreign key (tenant_id) references public.tenants(id);
alter table public.recommendation_evidence
  alter column tenant_id set not null,
  add constraint recommendation_evidence_tenant_fkey foreign key (tenant_id) references public.tenants(id);
alter table public.recommendation_decisions
  alter column tenant_id set not null,
  add constraint recommendation_decisions_tenant_fkey foreign key (tenant_id) references public.tenants(id);
alter table public.einvoice_records
  alter column tenant_id set not null,
  add constraint einvoice_records_tenant_fkey foreign key (tenant_id) references public.tenants(id);
alter table public.einvoice_outreach_drafts
  alter column tenant_id set not null,
  add constraint einvoice_outreach_drafts_tenant_fkey foreign key (tenant_id) references public.tenants(id);

create index if not exists conversations_tenant_idx on public.conversations (tenant_id, updated_at desc);
create index if not exists conversation_turns_tenant_idx on public.conversation_turns (tenant_id);
create index if not exists conversation_turn_citations_tenant_idx on public.conversation_turn_citations (tenant_id);
create index if not exists process_recommendations_tenant_idx on public.process_recommendations (tenant_id, created_at desc);
create index if not exists recommendation_evidence_tenant_idx on public.recommendation_evidence (tenant_id);
create index if not exists recommendation_decisions_tenant_idx on public.recommendation_decisions (tenant_id);
create index if not exists einvoice_records_tenant_idx on public.einvoice_records (tenant_id, status);
create index if not exists einvoice_outreach_drafts_tenant_idx on public.einvoice_outreach_drafts (tenant_id);

-- Re-declare each policy with the tenant predicate appended (drop + recreate,
-- matching this repo's existing migration convention).

drop policy if exists finbrain_owned_conversations on public.conversations;
create policy finbrain_owned_conversations on public.conversations to finbrain_app
  using (
    tenant_id = public.finbrain_tenant_id()
    and (created_by_user_id = public.finbrain_user_id() or public.finbrain_role() = 'compliance')
  )
  with check (tenant_id = public.finbrain_tenant_id() and created_by_user_id = public.finbrain_user_id());

drop policy if exists finbrain_conversation_turns on public.conversation_turns;
create policy finbrain_conversation_turns on public.conversation_turns to finbrain_app
  using (
    tenant_id = public.finbrain_tenant_id()
    and exists (select 1 from public.conversations c where c.id = conversation_id)
  )
  with check (
    tenant_id = public.finbrain_tenant_id()
    and exists (select 1 from public.conversations c where c.id = conversation_id)
  );

drop policy if exists finbrain_conversation_citations on public.conversation_turn_citations;
create policy finbrain_conversation_citations on public.conversation_turn_citations to finbrain_app
  using (
    tenant_id = public.finbrain_tenant_id()
    and exists (select 1 from public.conversation_turns t where t.id = turn_id)
  )
  with check (
    tenant_id = public.finbrain_tenant_id()
    and exists (select 1 from public.conversation_turns t where t.id = turn_id)
  );

drop policy if exists finbrain_recommendation_read on public.process_recommendations;
create policy finbrain_recommendation_read on public.process_recommendations
  for select to finbrain_app
  using (tenant_id = public.finbrain_tenant_id() and public.finbrain_role() in ('finance_ops', 'owner_director', 'compliance'));
drop policy if exists finbrain_recommendation_insert on public.process_recommendations;
create policy finbrain_recommendation_insert on public.process_recommendations
  for insert to finbrain_app
  with check (tenant_id = public.finbrain_tenant_id() and public.finbrain_role() in ('finance_ops', 'owner_director'));
drop policy if exists finbrain_recommendation_update on public.process_recommendations;
create policy finbrain_recommendation_update on public.process_recommendations
  for update to finbrain_app using (tenant_id = public.finbrain_tenant_id() and public.finbrain_role() = 'owner_director')
  with check (tenant_id = public.finbrain_tenant_id() and public.finbrain_role() = 'owner_director');

drop policy if exists finbrain_recommendation_evidence on public.recommendation_evidence;
create policy finbrain_recommendation_evidence on public.recommendation_evidence to finbrain_app
  using (
    tenant_id = public.finbrain_tenant_id()
    and exists (select 1 from public.process_recommendations r where r.id = recommendation_id)
  )
  with check (
    tenant_id = public.finbrain_tenant_id()
    and exists (select 1 from public.process_recommendations r where r.id = recommendation_id)
  );

drop policy if exists finbrain_recommendation_decisions on public.recommendation_decisions;
create policy finbrain_recommendation_decisions on public.recommendation_decisions to finbrain_app
  using (tenant_id = public.finbrain_tenant_id() and public.finbrain_role() in ('finance_ops', 'owner_director', 'compliance'))
  with check (tenant_id = public.finbrain_tenant_id() and public.finbrain_role() = 'owner_director');

drop policy if exists finbrain_einvoice_records on public.einvoice_records;
create policy finbrain_einvoice_records on public.einvoice_records
  for select to finbrain_app using (tenant_id = public.finbrain_tenant_id());
drop policy if exists finbrain_einvoice_records_write on public.einvoice_records;
create policy finbrain_einvoice_records_write on public.einvoice_records
  for insert to finbrain_app with check (tenant_id = public.finbrain_tenant_id());
drop policy if exists finbrain_einvoice_records_update on public.einvoice_records;
create policy finbrain_einvoice_records_update on public.einvoice_records
  for update to finbrain_app
  using (tenant_id = public.finbrain_tenant_id())
  with check (tenant_id = public.finbrain_tenant_id());

drop policy if exists finbrain_outreach_read on public.einvoice_outreach_drafts;
create policy finbrain_outreach_read on public.einvoice_outreach_drafts
  for select to finbrain_app using (tenant_id = public.finbrain_tenant_id());
drop policy if exists finbrain_outreach_insert on public.einvoice_outreach_drafts;
create policy finbrain_outreach_insert on public.einvoice_outreach_drafts
  for insert to finbrain_app with check (tenant_id = public.finbrain_tenant_id());
drop policy if exists finbrain_outreach_decide on public.einvoice_outreach_drafts;
create policy finbrain_outreach_decide on public.einvoice_outreach_drafts
  for update to finbrain_app
  using (tenant_id = public.finbrain_tenant_id() and public.finbrain_role() = 'owner_director')
  with check (tenant_id = public.finbrain_tenant_id() and public.finbrain_role() = 'owner_director');
