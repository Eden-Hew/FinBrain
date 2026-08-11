alter table tokenized_content enable row level security;
alter table token_vault enable row level security;
alter table audit_log enable row level security;

create policy "authenticated_content_read" on tokenized_content
  for select to authenticated using (true);

create policy "role_based_vault_access" on token_vault
  for select to authenticated
  using ((auth.jwt() ->> 'user_role') = any(allowed_roles));

create policy "compliance_only_audit_read" on audit_log
  for select to authenticated
  using ((auth.jwt() ->> 'user_role') = 'compliance');

-- Backend ingestion and audit writes use the service role, which bypasses RLS.

