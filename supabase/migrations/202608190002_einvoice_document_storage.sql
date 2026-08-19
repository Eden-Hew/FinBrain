alter table public.einvoice_records
  add column if not exists document_storage_path text;
