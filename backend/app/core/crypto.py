"""Symmetric encryption for secrets stored at rest (Item 16).

Bring-your-own LLM API keys are supplied per product over the API and must never
be persisted in plaintext, never logged, and never returned in a response. They
are encrypted here with Fernet (AES-128-CBC + HMAC-SHA256, authenticated) and
decrypted only at generation time inside ``services/llm/client.resolve_llm_config``.

The Fernet key is *derived* from ``settings.SECRET_KEY`` rather than being a
separate env var: ``SECRET_KEY`` is already required, already validated to ≥ 32
characters, and already the app's root secret, so introducing a second key to
manage would add operational surface without adding isolation. Derivation is a
plain SHA-256 of the secret — deterministic (the same secret always yields the
same key, so existing ciphertext stays readable across restarts) and it maps an
arbitrary-length passphrase onto Fernet's required 32 url-safe-base64 bytes.

Rotating ``SECRET_KEY`` therefore invalidates stored credentials: they decrypt to
``None`` and the affected products silently fall back to the admin-default LLM.
That is the intended failure mode — a lost key must not surface as a 500.
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

import structlog
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

logger = structlog.get_logger(__name__)


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    """Return the process-wide Fernet built from the derived ``SECRET_KEY``."""
    digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plaintext: str) -> str:
    """Encrypt *plaintext* and return the url-safe Fernet token."""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str) -> str | None:
    """Decrypt a Fernet *token*, or return ``None`` when it cannot be read.

    Returns ``None`` — rather than raising — for a token written under a rotated
    or different ``SECRET_KEY``, so the caller degrades to the admin-default
    credential instead of failing the scrape. The token itself is never logged.
    """
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError, TypeError) as exc:
        logger.warning("llm_credential_decrypt_failed", error=type(exc).__name__)
        return None


def mask_secret(plaintext: str) -> str:
    """Return a non-reversible display hint for a secret (e.g. ``…f4c2``).

    Used by the credential read endpoints so an operator can tell *which* key is
    stored without the response ever carrying enough to use it.
    """
    tail = plaintext[-4:] if len(plaintext) >= 4 else ""
    return f"…{tail}" if tail else "…"
