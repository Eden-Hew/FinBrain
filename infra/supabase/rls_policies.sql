alter table tokenized_content enable row level security;
alter table token_vault enable row level security;
alter table audit_log enable row level security;

alter table tokenized_content force row level security;
alter table token_vault force row level security;
alter table audit_log force row level security;

-- Until tenant IDs and verified auth are implemented, business content is not
-- exposed through the Data API. The trusted FastAPI database role owns runtime
-- access. These grants can be expanded alongside tenant-scoped policies later.
revoke all on table tokenized_content from anon, authenticated;
revoke all on table token_vault from anon, authenticated;
revoke all on table audit_log from anon, authenticated;

drop policy if exists "role_based_vault_access" on token_vault;
create policy "role_based_vault_access" on token_vault
  for select to authenticated
  using (
    coalesce(auth.jwt() ->> 'user_role', '') <> ''
    and allowed_roles @> jsonb_build_array(auth.jwt() ->> 'user_role')
  );

drop policy if exists "compliance_only_audit_read" on audit_log;
create policy "compliance_only_audit_read" on audit_log
  for select to authenticated
  using ((auth.jwt() ->> 'user_role') = 'compliance');

-- Authorization claims must come from a Custom Access Token Auth Hook or
-- raw_app_meta_data. Never authorize from raw_user_meta_data, which users can edit.
