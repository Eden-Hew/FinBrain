from uuid import UUID

from app.auth.principal import AuthPrincipal
from app.schemas import UserRole

USER_IDS = {
    UserRole.GENERAL_EMPLOYEE: UUID("10000000-0000-0000-0000-000000000001"),
    UserRole.FINANCE_OPS: UUID("20000000-0000-0000-0000-000000000002"),
    UserRole.OWNER_DIRECTOR: UUID("30000000-0000-0000-0000-000000000003"),
    UserRole.COMPLIANCE: UUID("40000000-0000-0000-0000-000000000004"),
}


def principal(role: UserRole = UserRole.GENERAL_EMPLOYEE) -> AuthPrincipal:
    return AuthPrincipal(
        user_id=USER_IDS[role],
        email=f"{role.value}@finbrain.test",
        role=role,
    )
