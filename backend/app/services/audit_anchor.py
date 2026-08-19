from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLogEntry, Tenant, WorkflowAuditEntry

GENESIS = "genesis"
_CHAIN_MODELS = {"disclosure": AuditLogEntry, "workflow": WorkflowAuditEntry}


@dataclass(frozen=True, slots=True)
class ChainAnchor:
    tenant_id: str | None
    chain: str
    tail_hash: str


def all_tenant_ids(db: Session) -> list[str]:
    return [str(row) for row in db.scalars(select(Tenant.id)).all()]


def chain_tail_hashes(db: Session, tenant_id: str | None) -> list[ChainAnchor]:
    """Current tail (latest event_hash) of both hash chains for one tenant, or the
    system chain when tenant_id is None."""
    anchors = []
    for chain, model in _CHAIN_MODELS.items():
        tail = db.scalar(
            select(model.event_hash)
            .where(model.tenant_id == tenant_id)
            .order_by(model.id.desc())
            .limit(1)
        )
        anchors.append(ChainAnchor(tenant_id=tenant_id, chain=chain, tail_hash=tail or GENESIS))
    return anchors


def all_chain_anchors(db: Session) -> list[ChainAnchor]:
    """One ChainAnchor per (chain, tenant) pair, plus the system (tenant_id=None) chain."""
    anchors = chain_tail_hashes(db, None)
    for tenant_id in all_tenant_ids(db):
        anchors.extend(chain_tail_hashes(db, tenant_id))
    return anchors


def anchor_is_still_present(db: Session, anchor: ChainAnchor) -> bool:
    """True if the previously-anchored tail hash still exists, unchanged, in this
    tenant's chain. A hash is a SHA-256 digest over immutable event content plus the
    previous hash, so this check alone is sufficient: if that exact digest still
    exists under the same tenant_id, nothing between genesis and that point could
    have been altered without also changing the digest itself. If it is gone --
    deleted, or the row's tenant_id/hash was edited -- the chain was tampered with
    after the anchor was taken.
    """
    if anchor.tail_hash == GENESIS:
        return True
    model = _CHAIN_MODELS[anchor.chain]
    exists = db.scalar(
        select(model.id).where(
            model.tenant_id == anchor.tenant_id, model.event_hash == anchor.tail_hash
        )
    )
    return exists is not None
