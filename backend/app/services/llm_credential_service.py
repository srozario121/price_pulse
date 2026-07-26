"""Per-product BYO LLM credential storage (Item 16).

Encryption lives here rather than in the route layer so there is exactly one
place where a plaintext key is turned into a stored value, and exactly one place
that reads it back. The routes never touch ``core.crypto`` and never see the
ciphertext.
"""

from __future__ import annotations

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_secret, encrypt_secret, mask_secret
from app.models.product_llm_credential import ProductLLMCredential
from app.schemas.llm_credential import ProductLLMCredentialRead, ProductLLMCredentialWrite

logger = structlog.get_logger(__name__)


async def get_credential(session: AsyncSession, product_id: int) -> ProductLLMCredential | None:
    """Return the stored credential row for *product_id*, or ``None``."""
    return await session.scalar(
        select(ProductLLMCredential).where(ProductLLMCredential.product_id == product_id)
    )


async def upsert_credential(
    session: AsyncSession, product_id: int, body: ProductLLMCredentialWrite
) -> ProductLLMCredential:
    """Create or replace *product_id*'s credential, encrypting the key at rest.

    ``PUT`` semantics: the whole credential is replaced, so switching provider
    never leaves a stale ``azure_endpoint`` behind to be picked up later.
    """
    credential = await get_credential(session, product_id)
    encrypted = encrypt_secret(body.api_key)
    if credential is None:
        credential = ProductLLMCredential(product_id=product_id)
        session.add(credential)
    credential.provider = body.provider
    credential.model = body.model
    credential.encrypted_api_key = encrypted
    credential.azure_endpoint = body.azure_endpoint
    credential.azure_api_version = body.azure_api_version
    await session.flush()
    await session.refresh(credential)
    # Logged without the key or its ciphertext — provider/model only.
    logger.info(
        "llm_credential_stored",
        product_id=product_id,
        provider=body.provider,
        model=body.model,
    )
    return credential


async def delete_credential(session: AsyncSession, product_id: int) -> bool:
    """Delete *product_id*'s credential; return whether one existed.

    Removing it reverts the product to the env admin default (or to generation
    being disabled, when no admin default is configured).
    """
    credential = await get_credential(session, product_id)
    if credential is None:
        return False
    await session.execute(
        delete(ProductLLMCredential).where(ProductLLMCredential.product_id == product_id)
    )
    logger.info("llm_credential_deleted", product_id=product_id)
    return True


def to_read_schema(credential: ProductLLMCredential) -> ProductLLMCredentialRead:
    """Project a credential row onto the read schema — metadata only, never the key.

    The hint is derived by decrypting server-side and masking down to the last
    four characters; an unreadable token (rotated ``SECRET_KEY``) yields a plain
    ellipsis rather than an error, matching the graceful-fallback behaviour of
    ``resolve_llm_config``.
    """
    plaintext = decrypt_secret(credential.encrypted_api_key)
    return ProductLLMCredentialRead(
        product_id=credential.product_id,
        provider=credential.provider,
        model=credential.model,
        has_key=plaintext is not None,
        key_hint=mask_secret(plaintext) if plaintext else "…",
        azure_endpoint=credential.azure_endpoint,
        azure_api_version=credential.azure_api_version,
        created_at=credential.created_at,
        updated_at=credential.updated_at,
    )
