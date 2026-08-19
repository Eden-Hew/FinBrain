-- Financial Dashboard: real Revenue & AR analytics need two things einvoice_records
-- never had. `due_date` is required for AR aging (current/30/60/90+); `paid_at` is
-- required for "outstanding AR" to mean anything at all -- previously status only
-- ever held "pending"/"validated", so a validated invoice would show as forever
-- outstanding. Both are kept orthogonal to `status` (document status) rather than
-- overloading it with a payment-status value, matching how real invoicing systems
-- separate the two. No new table, so no new RLS policy needed -- the existing
-- einvoice_records policies already cover these columns.

alter table public.einvoice_records add column if not exists due_date date;
alter table public.einvoice_records add column if not exists paid_at date;

create index if not exists einvoice_records_ar_aging_idx
  on public.einvoice_records (tenant_id, status, paid_at, due_date);
