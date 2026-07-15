"""Password-based encryption for champ-guide export/import.

PBKDF2-HMAC-SHA256 derives a key from the user's password + a random salt;
Fernet (AES-128-CBC + HMAC) encrypts the JSON payload with that key. The
salt and iteration count travel in cleartext alongside the ciphertext —
they aren't secret, they just let a future import re-derive the same key.
"""
import base64
import json
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

PBKDF2_ITERATIONS = 390_000  # current OWASP-recommended minimum for PBKDF2-HMAC-SHA256


def _derive_key(password: str, salt: bytes, iterations: int) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations)
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


def encrypt_payload(payload: dict, password: str) -> dict:
    """Returns {salt, iterations, ciphertext} (JSON-safe strings)."""
    salt = os.urandom(16)
    key = _derive_key(password, salt, PBKDF2_ITERATIONS)
    token = Fernet(key).encrypt(json.dumps(payload).encode("utf-8"))
    return {
        "salt": base64.b64encode(salt).decode("ascii"),
        "iterations": PBKDF2_ITERATIONS,
        "ciphertext": token.decode("ascii"),
    }


def decrypt_payload(salt_b64: str, iterations: int, ciphertext: str, password: str) -> dict:
    """Raises ValueError on a wrong password or corrupt/tampered ciphertext."""
    try:
        salt = base64.b64decode(salt_b64)
        key = _derive_key(password, salt, int(iterations))
        plaintext = Fernet(key).decrypt(ciphertext.encode("ascii"))
        return json.loads(plaintext)
    except (InvalidToken, ValueError, TypeError, KeyError) as exc:
        raise ValueError("wrong password or corrupt file") from exc
