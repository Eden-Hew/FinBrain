alter table public.telegram_update_receipts enable row level security;
alter table public.integration_status enable row level security;

alter table public.telegram_update_receipts force row level security;
alter table public.integration_status force row level security;

revoke all on table public.telegram_update_receipts from anon, authenticated;
revoke all on table public.integration_status from anon, authenticated;
