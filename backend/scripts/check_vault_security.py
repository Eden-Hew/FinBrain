from sqlalchemy import text

from app.config import get_settings
from app.db import SessionLocal, engine, set_rls_context, set_worker_context
from app.services.audit import write_audit_entry
from app.services.workflow_audit import write_workflow_event


def _role_counts(role: str) -> tuple[int, int]:
    with engine.connect() as connection, connection.begin():
        connection.execute(
            text(
                "select set_config('app.user_id', :user_id, true), "
                "set_config('app.user_role', :user_role, true), "
                "set_config('app.actor_ref', :actor_ref, true)"
            ),
            {
                "user_id": "00000000-0000-0000-0000-000000000001",
                "user_role": role,
                "actor_ref": f"security-check:{role}",
            },
        )
        connection.execute(text("set local role finbrain_app"))
        registry_count = connection.scalar(
            text("select count(*) from public.protected_token_registry")
        )
        vault_count = connection.scalar(text("select count(*) from public.token_vault"))
        return int(registry_count or 0), int(vault_count or 0)


def main() -> None:
    if get_settings().database_backend != "postgresql":
        raise SystemExit("DATABASE_URL is not PostgreSQL/Supabase")
    general_registry, general_vault = _role_counts("general_employee")
    compliance_registry, compliance_vault = _role_counts("compliance")
    if general_registry == 0:
        raise SystemExit("The protected token registry is unexpectedly empty.")
    if general_registry != compliance_registry:
        raise SystemExit("Safe token registry visibility differs between authenticated roles.")
    if general_vault >= general_registry:
        raise SystemExit("General employee ciphertext access is not restricted by RLS.")
    if compliance_vault != compliance_registry:
        raise SystemExit("Compliance cannot read every seeded vault row.")
    with SessionLocal() as worker_db:
        set_worker_context(worker_db)
        worker_identity = worker_db.execute(
            text("select current_user, session_user")
        ).one()
        worker_policies = worker_db.execute(
            text(
                "select policyname, cmd, with_check from pg_policies "
                "where schemaname = 'public' and tablename = 'workflow_audit_log' "
                "and 'finbrain_worker' = any(roles)"
            )
        ).all()
        write_workflow_event(
            worker_db,
            event_type="security_check",
            actor_role="system_worker",
            actor_ref="security-check",
            resource_type="vault",
            resource_id="rollback",
            event_payload={},
        )
        worker_db.rollback()
    if worker_identity.current_user != "finbrain_worker":
        raise SystemExit("Worker session did not enter the finbrain_worker database role.")
    if not any(row.cmd == "INSERT" and row.with_check == "true" for row in worker_policies):
        raise SystemExit("The worker workflow-audit insert policy is missing.")
    with SessionLocal() as app_db:
        set_rls_context(
            app_db,
            user_id="00000000-0000-0000-0000-000000000001",
            user_role="general_employee",
            actor_ref="security-check:application",
            tenant_id="00000000-0000-0000-0000-000000000001",
        )
        write_audit_entry(
            app_db,
            "general_employee",
            "SECURITY_CHECK_0000000000",
            False,
            "security-check",
            tenant_id="00000000-0000-0000-0000-000000000001",
            actor_ref="security-check:application",
        )
        write_workflow_event(
            app_db,
            event_type="security_check",
            actor_role="general_employee",
            actor_ref="security-check:application",
            resource_type="vault",
            resource_id="rollback",
            tenant_id="00000000-0000-0000-0000-000000000001",
            event_payload={},
        )
        app_db.rollback()
    print(f"Safe token registry visible to authenticated roles: {general_registry}")
    print(f"General employee ciphertext rows: {general_vault}/{general_registry}")
    print(f"Compliance ciphertext rows: {compliance_vault}/{compliance_registry}")
    print(
        "Worker database role: "
        f"{worker_identity.current_user} (session: {worker_identity.session_user})"
    )
    print("Application and worker audit INSERT ... RETURNING checks passed.")
    print("Live vault RLS role check passed.")


if __name__ == "__main__":
    main()
