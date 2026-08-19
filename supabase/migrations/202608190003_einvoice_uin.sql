alter table public.einvoice_records
  add column if not exists uin text;
