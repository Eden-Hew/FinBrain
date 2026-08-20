-- Email-linked profiles recalculate tenant-scoped attention after protected persistence.
grant select on public.einvoice_records to finbrain_worker;

create policy finbrain_worker_einvoice_attention_read on public.einvoice_records
  for select to finbrain_worker
  using(tenant_id=public.finbrain_tenant_id());
