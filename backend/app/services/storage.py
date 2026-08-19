"""Thin client for Supabase Storage — private bucket uploads and short-lived signed URLs.

Uses the service_role key directly against the Storage REST API rather than pulling in the
full supabase-py SDK, since this is the only Storage operation the backend needs.
"""
import httpx

from app.config import get_settings


class StorageError(RuntimeError):
    pass


class StorageNotConfiguredError(StorageError):
    pass


def _require_service_role() -> tuple[str, str]:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise StorageNotConfiguredError("SUPABASE_SERVICE_ROLE_KEY is not configured")
    return settings.supabase_url.rstrip("/"), settings.supabase_service_role_key


def _auth_headers(service_role_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {service_role_key}", "apikey": service_role_key}


def ensure_bucket(bucket: str) -> None:
    """Create the bucket as private if it doesn't already exist. Idempotent."""
    base_url, key = _require_service_role()
    with httpx.Client(timeout=15) as client:
        response = client.post(
            f"{base_url}/storage/v1/bucket",
            headers=_auth_headers(key),
            json={"id": bucket, "name": bucket, "public": False},
        )
        already_exists = "already exists" in response.text.lower()
        if response.status_code not in (200, 201) and not already_exists:
            raise StorageError(
                f"failed to create bucket '{bucket}': {response.status_code} {response.text}"
            )


def upload_bytes(bucket: str, path: str, data: bytes, *, content_type: str) -> None:
    base_url, key = _require_service_role()
    headers = _auth_headers(key)
    headers["Content-Type"] = content_type
    headers["x-upsert"] = "true"
    with httpx.Client(timeout=30) as client:
        response = client.post(
            f"{base_url}/storage/v1/object/{bucket}/{path}", headers=headers, content=data
        )
        if response.status_code not in (200, 201):
            raise StorageError(f"failed to upload '{path}': {response.status_code} {response.text}")


def create_signed_url(bucket: str, path: str, *, expires_in: int = 300) -> str:
    base_url, key = _require_service_role()
    with httpx.Client(timeout=15) as client:
        response = client.post(
            f"{base_url}/storage/v1/object/sign/{bucket}/{path}",
            headers=_auth_headers(key),
            json={"expiresIn": expires_in},
        )
        if response.status_code != 200:
            raise StorageError(f"failed to sign '{path}': {response.status_code} {response.text}")
        signed_path = response.json()["signedURL"]
        return f"{base_url}/storage/v1{signed_path}"
