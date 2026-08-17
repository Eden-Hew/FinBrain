import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import get_settings


def derive_key_from_secret(secret: bytes, *, info: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=info).derive(secret)


def derive_key(info: bytes) -> bytes:
    """Compatibility helper for keyed fingerprints that are not vault ciphertext."""
    return derive_key_from_secret(
        get_settings().token_identity_secret.encode(),
        info=info,
    )


def encrypt_value(value: str, key: bytes, aad: bytes | None = None) -> tuple[bytes, bytes]:
    nonce = os.urandom(12)
    return AESGCM(key).encrypt(nonce, value.encode(), aad), nonce


def decrypt_value(
    ciphertext: bytes,
    nonce: bytes,
    key: bytes,
    aad: bytes | None = None,
) -> str:
    return AESGCM(key).decrypt(nonce, ciphertext, aad).decode()
