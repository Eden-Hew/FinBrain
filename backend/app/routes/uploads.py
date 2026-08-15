import re

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.auth.principal import AuthPrincipal
from app.config import get_settings
from app.db import get_db
from app.integrations.telegram.extractors import ExtractionError
from app.schemas import UploadCommitResponse, UploadPreviewResponse, UserRole
from app.services.upload_ingestion import commit_upload, preview_upload

router = APIRouter(prefix="/uploads", tags=["uploads"])
RECORD_TYPE_PATTERN = re.compile(r"^[a-z0-9_.-]{1,64}$")


async def _bounded_body(request: Request) -> bytes:
    limit = get_settings().structured_csv_max_file_bytes
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise HTTPException(status_code=413, detail="file_too_large")
        chunks.append(chunk)
    if not chunks:
        raise HTTPException(status_code=422, detail="empty_file")
    return b"".join(chunks)


def _metadata(
    filename: str,
    record_type: str,
) -> tuple[str, str]:
    if not RECORD_TYPE_PATTERN.fullmatch(record_type):
        raise HTTPException(status_code=422, detail="invalid_record_type")
    return filename, record_type


@router.post("/preview", response_model=UploadPreviewResponse)
async def preview(
    request: Request,
    filename: str = Header(alias="X-FinBrain-Filename", max_length=255),
    record_type: str = Header(default="uploaded_document", alias="X-FinBrain-Record-Type"),
    _principal: AuthPrincipal = Depends(
        require_roles(UserRole.FINANCE_OPS, UserRole.OWNER_DIRECTOR)
    ),
) -> UploadPreviewResponse:
    _metadata(filename, record_type)
    data = await _bounded_body(request)
    try:
        return preview_upload(
            data,
            filename=filename,
            mime_type=request.headers.get("content-type", "application/octet-stream"),
            record_type=record_type,
        )
    except ExtractionError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/commit", response_model=UploadCommitResponse)
async def commit(
    request: Request,
    filename: str = Header(alias="X-FinBrain-Filename", max_length=255),
    record_type: str = Header(default="uploaded_document", alias="X-FinBrain-Record-Type"),
    _principal: AuthPrincipal = Depends(
        require_roles(UserRole.FINANCE_OPS, UserRole.OWNER_DIRECTOR)
    ),
    preview_digest: str = Header(alias="X-FinBrain-Preview-Digest", min_length=64, max_length=64),
    db: Session = Depends(get_db),
) -> UploadCommitResponse:
    _metadata(filename, record_type)
    data = await _bounded_body(request)
    try:
        return commit_upload(
            db,
            data,
            filename=filename,
            mime_type=request.headers.get("content-type", "application/octet-stream"),
            record_type=record_type,
            expected_digest=preview_digest,
        )
    except ExtractionError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ValueError as error:
        status = 409 if str(error) == "preview_digest_mismatch" else 422
        raise HTTPException(status_code=status, detail=str(error)) from error
