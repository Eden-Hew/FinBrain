from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser, require_roles
from app.auth.principal import AuthPrincipal
from app.db import get_db
from app.schemas import (
    EInvoiceCreatePayload,
    EinvoiceDocumentUrlResponse,
    EinvoiceOutreachDraftResponse,
    EinvoiceReadinessResponse,
    EInvoiceRecordResponse,
    InvoiceExtraction,
    RequestFixPayload,
    UserRole,
)
from app.services.einvoice_extraction import extract_invoice_fields
from app.services.einvoice_readiness import (
    approve_record,
    compute_readiness,
    create_outreach_draft,
    create_record,
    decide_outreach,
    get_document_url,
    get_record,
    list_outreach_drafts,
    list_records,
    upload_record_document,
)

router = APIRouter(tags=["einvoice-readiness"])

_READINESS_ROLES = (UserRole.FINANCE_OPS, UserRole.OWNER_DIRECTOR, UserRole.COMPLIANCE)
_MANAGE_ROLES = (UserRole.FINANCE_OPS, UserRole.OWNER_DIRECTOR)
_MAX_DOCUMENT_BYTES = 10_000_000


async def _bounded_pdf_body(request: Request) -> bytes:
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > _MAX_DOCUMENT_BYTES:
            raise HTTPException(status_code=413, detail="file_too_large")
        chunks.append(chunk)
    if not chunks:
        raise HTTPException(status_code=422, detail="empty_file")
    return b"".join(chunks)


@router.get("/einvoice-records", response_model=list[EInvoiceRecordResponse])
def einvoice_records(
    _principal: CurrentUser,
    db: Session = Depends(get_db),
) -> list[EInvoiceRecordResponse]:
    return list_records(db)


@router.post("/einvoice-records", response_model=EInvoiceRecordResponse)
def einvoice_record_create(
    payload: EInvoiceCreatePayload,
    principal: AuthPrincipal = Depends(require_roles(*_MANAGE_ROLES)),
    db: Session = Depends(get_db),
) -> EInvoiceRecordResponse:
    return create_record(db, payload, role=principal.role, actor_ref=principal.actor_ref)


@router.post("/einvoice-records/extract", response_model=InvoiceExtraction)
async def einvoice_record_extract(
    request: Request,
    _principal: AuthPrincipal = Depends(require_roles(*_MANAGE_ROLES)),
) -> InvoiceExtraction:
    content_type = request.headers.get("content-type", "")
    if content_type != "application/pdf":
        raise HTTPException(status_code=422, detail="only_pdf_supported")
    data = await _bounded_pdf_body(request)
    try:
        return extract_invoice_fields(data, filename="invoice.pdf", mime_type="application/pdf")
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post("/einvoice-records/{record_id}/document", response_model=EInvoiceRecordResponse)
async def einvoice_record_upload_document(
    record_id: int,
    request: Request,
    principal: AuthPrincipal = Depends(require_roles(*_MANAGE_ROLES)),
    db: Session = Depends(get_db),
) -> EInvoiceRecordResponse:
    content_type = request.headers.get("content-type", "")
    if content_type != "application/pdf":
        raise HTTPException(status_code=422, detail="only_pdf_supported")
    data = await _bounded_pdf_body(request)
    try:
        return upload_record_document(
            db, record_id, data, role=principal.role, actor_ref=principal.actor_ref
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/einvoice-records/{record_id}", response_model=EInvoiceRecordResponse)
def einvoice_record(
    record_id: int,
    _principal: CurrentUser,
    db: Session = Depends(get_db),
) -> EInvoiceRecordResponse:
    try:
        return get_record(db, record_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/einvoice-records/{record_id}/approve", response_model=EInvoiceRecordResponse)
def einvoice_record_approve(
    record_id: int,
    principal: AuthPrincipal = Depends(require_roles(UserRole.OWNER_DIRECTOR)),
    db: Session = Depends(get_db),
) -> EInvoiceRecordResponse:
    try:
        return approve_record(db, record_id, role=principal.role, actor_ref=principal.actor_ref)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/einvoice-readiness", response_model=EinvoiceReadinessResponse)
def readiness(
    principal: AuthPrincipal = Depends(require_roles(*_READINESS_ROLES)),
    db: Session = Depends(get_db),
) -> EinvoiceReadinessResponse:
    return compute_readiness(db, role=principal.role, actor_ref=principal.actor_ref)


@router.post(
    "/einvoice-readiness/{record_id}/request-fix",
    response_model=EinvoiceOutreachDraftResponse,
)
def request_fix(
    record_id: int,
    payload: RequestFixPayload,
    principal: AuthPrincipal = Depends(require_roles(*_MANAGE_ROLES)),
    db: Session = Depends(get_db),
) -> EinvoiceOutreachDraftResponse:
    try:
        return create_outreach_draft(
            db,
            record_id,
            channel=payload.channel,
            role=principal.role,
            actor_ref=principal.actor_ref,
            created_by_user_id=str(principal.user_id),
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get(
    "/einvoice-readiness/{record_id}/document",
    response_model=EinvoiceDocumentUrlResponse,
)
def readiness_document(
    record_id: int,
    _principal: AuthPrincipal = Depends(require_roles(*_READINESS_ROLES)),
    db: Session = Depends(get_db),
) -> EinvoiceDocumentUrlResponse:
    try:
        return get_document_url(db, record_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/einvoice-outreach-drafts", response_model=list[EinvoiceOutreachDraftResponse])
def outreach_drafts(
    _principal: AuthPrincipal = Depends(require_roles(*_READINESS_ROLES)),
    db: Session = Depends(get_db),
) -> list[EinvoiceOutreachDraftResponse]:
    return list_outreach_drafts(db)


def _decide(
    draft_id: int,
    decision: str,
    principal: AuthPrincipal,
    db: Session,
) -> EinvoiceOutreachDraftResponse:
    try:
        return decide_outreach(
            db,
            draft_id,
            decision=decision,
            role=principal.role,
            actor_ref=principal.actor_ref,
        )
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post(
    "/einvoice-outreach-drafts/{draft_id}/approve",
    response_model=EinvoiceOutreachDraftResponse,
)
def approve_outreach(
    draft_id: int,
    principal: AuthPrincipal = Depends(require_roles(UserRole.OWNER_DIRECTOR)),
    db: Session = Depends(get_db),
) -> EinvoiceOutreachDraftResponse:
    return _decide(draft_id, "approved", principal, db)


@router.post(
    "/einvoice-outreach-drafts/{draft_id}/reject",
    response_model=EinvoiceOutreachDraftResponse,
)
def reject_outreach(
    draft_id: int,
    principal: AuthPrincipal = Depends(require_roles(UserRole.OWNER_DIRECTOR)),
    db: Session = Depends(get_db),
) -> EinvoiceOutreachDraftResponse:
    return _decide(draft_id, "rejected", principal, db)
