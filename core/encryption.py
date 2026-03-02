"""
AES-256-GCM private key encryption/decryption.
Uses PBKDF2-HMAC-SHA256 key derivation with 310,000 iterations.
Private keys are NEVER logged or stored in plaintext anywhere.
"""

from __future__ import annotations

import base64
import os
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend


# Sizes in bytes
_SALT_SIZE = 16
_NONCE_SIZE = 12
_KEY_SIZE = 32
_PBKDF2_ITERATIONS = 310_000


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    """
    Derive a 32-byte AES key from passphrase using PBKDF2-HMAC-SHA256.

    Args:
        passphrase: User-supplied passphrase string.
        salt: Random 16-byte salt.

    Returns:
        32-byte derived key.
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=_KEY_SIZE,
        salt=salt,
        iterations=_PBKDF2_ITERATIONS,
        backend=default_backend(),
    )
    return kdf.derive(passphrase.encode("utf-8"))


def encrypt_private_key(plaintext: str, passphrase: str, salt: Optional[bytes] = None) -> str:
    """
    Encrypt a private key string using AES-256-GCM.

    Steps:
        1. Generate random 16-byte salt (or use provided).
        2. Derive 32-byte key via PBKDF2-HMAC-SHA256 (310,000 iterations).
        3. Generate random 12-byte nonce.
        4. AES-256-GCM encrypt the plaintext.
        5. Return base64(salt + nonce + ciphertext_with_tag).

    Args:
        plaintext: Private key string to encrypt.
        passphrase: User passphrase for key derivation.
        salt: Optional salt bytes (random if not provided).

    Returns:
        Base64-encoded encrypted blob (salt + nonce + ciphertext + GCM tag).
    """
    if not passphrase:
        raise ValueError("Passphrase cannot be empty")

    salt = salt or os.urandom(_SALT_SIZE)
    nonce = os.urandom(_NONCE_SIZE)
    key = _derive_key(passphrase, salt)

    aesgcm = AESGCM(key)
    # GCM tag (16 bytes) is appended to ciphertext automatically
    ciphertext_with_tag = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)

    blob = salt + nonce + ciphertext_with_tag
    return base64.b64encode(blob).decode("ascii")


def decrypt_private_key(encrypted_b64: str, passphrase: str) -> str:
    """
    Decrypt a private key previously encrypted with encrypt_private_key.

    Args:
        encrypted_b64: Base64-encoded encrypted blob from encrypt_private_key.
        passphrase: User passphrase for key derivation.

    Returns:
        Decrypted private key string.

    Raises:
        ValueError: If the passphrase is wrong or data is corrupted.
    """
    if not passphrase:
        raise ValueError("Passphrase cannot be empty")

    try:
        blob = base64.b64decode(encrypted_b64.encode("ascii"))
    except Exception as exc:
        raise ValueError("Invalid encrypted data (base64 decode failed)") from exc

    if len(blob) < _SALT_SIZE + _NONCE_SIZE + 16:  # 16 = min GCM tag
        raise ValueError("Encrypted data is too short")

    salt = blob[:_SALT_SIZE]
    nonce = blob[_SALT_SIZE : _SALT_SIZE + _NONCE_SIZE]
    ciphertext_with_tag = blob[_SALT_SIZE + _NONCE_SIZE :]

    key = _derive_key(passphrase, salt)
    aesgcm = AESGCM(key)

    try:
        plaintext_bytes = aesgcm.decrypt(nonce, ciphertext_with_tag, None)
    except Exception as exc:
        raise ValueError("Decryption failed — wrong passphrase or corrupted data") from exc

    return plaintext_bytes.decode("utf-8")
