drop policy if exists finbrain_einvoice_records_update on public.einvoice_records;
create policy finbrain_einvoice_records_update on public.einvoice_records
  for update to finbrain_app using (true) with check (true);
