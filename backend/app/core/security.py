"""Password hashing (argon2) + opaque access-token minting/hashing.

Tokens are random opaque strings handed to the client once; we persist only their
SHA-256 so the auth dependency can look a user up by token in one indexed query.
SHA-256 (not argon2) is correct here: the token already has ~256 bits of entropy, and a
salted password hash can't be looked up by value. Passwords, which are low-entropy, use
argon2.
"""

import hashlib
import secrets

from argon2 import PasswordHasher

_ph = PasswordHasher()


def new_opaque_token() -> str:
    """A fresh URL-safe access token (~256 bits)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Stable SHA-256 of an opaque token, for indexed lookup."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except Exception:  # noqa: BLE001 - mismatch / malformed hash = not verified
        return False
