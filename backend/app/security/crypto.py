import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import get_settings


def derive_key(info: bytes) -> bytes:
    secret = get_settings().token_root_secret.encode()
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=info).derive(secret)


def encrypt_value(value: str, key: bytes) -> tuple[bytes, bytes]:
    nonce = os.urandom(12)
    return AESGCM(key).encrypt(nonce, value.encode(), None), nonce


def decrypt_value(ciphertext: bytes, nonce: bytes, key: bytes) -> str:
    return AESGCM(key).decrypt(nonce, ciphertext, None).decode()
