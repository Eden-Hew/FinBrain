-- Phase 5: the recommendations scheduler runs as finbrain_worker, iterating
-- tenants one at a time. process_recommendations/recommendation_evidence
-- previously granted only finbrain_app -- the manual "Analyze Processes"
-- button's role -- with no worker access at all, so a background scheduler
-- calling the exact same service-layer function would have been rejected
-- outright by RLS. Mirrors the existing tokenized_content/token_vault worker
-- pattern: unrestricted RLS for the worker role, with the real tenant scoping
-- enforced by the explicit tenant_id filter already in the Python service layer.
--
-- recommendation_decisions is intentionally left untouched -- the scheduler only
-- ever creates proposals, never approves/rejects/implements them; that stays a
-- human, finbrain_app-only action.

grant select, insert on public.process_recommendations, public.recommendation_evidence
  to finbrain_worker;

drop policy if exists finbrain_worker_recommendation_read on public.process_recommendations;
create policy finbrain_worker_recommendation_read on public.process_recommendations
  for select to finbrain_worker using (true);

drop policy if exists finbrain_worker_recommendation_insert on public.process_recommendations;
create policy finbrain_worker_recommendation_insert on public.process_recommendations
  for insert to finbrain_worker with check (true);

drop policy if exists finbrain_worker_recommendation_evidence on public.recommendation_evidence;
create policy finbrain_worker_recommendation_evidence on public.recommendation_evidence
  to finbrain_worker using (true) with check (true);
