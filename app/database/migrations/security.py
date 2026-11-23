"""Cryptographic and password security utilities for user authentication (Phase 3B)."""

import hashlib
import secrets
from typing import Tuple


def hash_password(password: str) -> str:
    """Hash a password using PBKDF2-HMAC-SHA256 with 600,000 iterations and a random 16-byte salt."""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        600000,
    )
    return f"pbkdf2:sha256:600000:{salt}:{dk.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against the stored PBKDF2 hash."""
    try:
        parts = hashed_password.split(":")
        if len(parts) != 5:
            return False
        scheme, algo, iterations_str, salt, hash_hex = parts
        if scheme != "pbkdf2" or algo != "sha256":
            return False
        iterations = int(iterations_str)
        dk = hashlib.pbkdf2_hmac(
            "sha256",
            plain_password.encode("utf-8"),
            salt.encode("utf-8"),
            iterations,
        )
        return secrets.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


def generate_secure_token(length_bytes: int = 24) -> str:
    """Generate a URL-safe random string for account initialization or password resets."""
    return secrets.token_urlsafe(length_bytes)

