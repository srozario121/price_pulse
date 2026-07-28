"""Credential resolution and Pydantic AI model construction (Item 16).

Two things live here, and nothing else knows about LLM providers:

``resolve_llm_config``
    Decides *which* credential a generation run uses — per-product bring-your-own
    first, then the env admin default, then ``None`` (generation disabled).

``build_model``
    Turns a resolved config into the Pydantic AI ``Model`` for its provider.
    OpenAI, Anthropic, Azure OpenAI and OpenRouter are all reachable through the
    one code path, so onboarding a provider is a config change, not new wiring.

A single long-lived ``Agent`` (``selector_agent``) carries the instructions and
the ``SelectorSuggestion`` output type; the model is supplied **per run**
(``agent.run(..., model=...)``) so one agent serves every credential without
being rebuilt.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog
from pydantic_ai import Agent
from pydantic_ai.models import Model
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import (
    LLM_PROVIDERS,
    azure_config_error,
    base_url_config_error,
    is_azure_v1_endpoint,
    settings,
)
from app.core.crypto import decrypt_secret
from app.models.product import Product
from app.models.product_llm_credential import ProductLLMCredential
from app.services.llm.schemas import SelectorSuggestion

logger = structlog.get_logger(__name__)

_INSTRUCTIONS = """
You are given the trimmed HTML of a retail product page. Return a CSS selector
that matches the element whose text content is the product's current, actually
purchasable price.

Rules:
- Prefer the buy-box / current price over a struck-through list price, an "RRP",
  a subscription variant, or a price for a different size/colour option.
- Prefer a stable, structural selector (id or a semantic class) over one built
  from long auto-generated class hashes, which change on the next deploy.
- The selector must match the price element on THIS page. Do not invent ids or
  classes that do not appear in the HTML.
- Set currency_selector only when the currency symbol or code lives in a
  different element from the price; otherwise leave it null.
- Report your honest confidence in the range 0.0 to 1.0.
"""

# Model is deliberately omitted — every run passes its own, resolved from the
# product's BYO credential or the env admin default.
selector_agent = Agent(
    output_type=SelectorSuggestion,
    instructions=_INSTRUCTIONS,
    name="selector_generator",
)


@dataclass(frozen=True)
class LLMConfig:
    """A fully-resolved LLM credential ready to build a model from."""

    provider: str
    model: str
    api_key: str
    azure_endpoint: str | None = None
    azure_api_version: str | None = None
    # Custom API endpoint (gateway / proxy / self-hosted OpenAI-compatible
    # server). None ⇒ the provider's own default.
    base_url: str | None = None
    # Where the credential came from — logged so an operator can tell whose key
    # (and whose bill) a generation used. Never carries the key itself.
    source: str = "admin_default"


class LLMConfigError(ValueError):
    """A resolved credential cannot produce a usable model (bad/incomplete config)."""


def _admin_default_config() -> LLMConfig | None:
    """Return the env-configured admin-default credential, or ``None`` if unset.

    An empty ``LLM_API_KEY`` is the documented "generation disabled" switch, not
    an error — a deployment that never wants LLM calls simply leaves it blank.
    """
    if not settings.LLM_API_KEY:
        return None
    return LLMConfig(
        provider=settings.LLM_PROVIDER,
        model=settings.LLM_MODEL,
        api_key=settings.LLM_API_KEY,
        azure_endpoint=settings.AZURE_OPENAI_ENDPOINT or None,
        azure_api_version=settings.AZURE_OPENAI_API_VERSION or None,
        base_url=settings.LLM_BASE_URL or None,
        source="admin_default",
    )


async def resolve_llm_config(session: AsyncSession, product: Product) -> LLMConfig | None:
    """Resolve the credential for *product*: BYO → admin default → ``None``.

    ``None`` means generation is disabled for this product; callers must treat it
    as a no-op and fall back to existing extraction behaviour, never as an error.
    A BYO row whose key cannot be decrypted (e.g. ``SECRET_KEY`` was rotated)
    falls through to the admin default rather than failing the run.
    """
    credential = await session.scalar(
        select(ProductLLMCredential).where(ProductLLMCredential.product_id == product.id)
    )
    if credential is not None:
        api_key = decrypt_secret(credential.encrypted_api_key)
        if api_key:
            return LLMConfig(
                provider=credential.provider,
                model=credential.model,
                api_key=api_key,
                azure_endpoint=credential.azure_endpoint,
                azure_api_version=credential.azure_api_version,
                # Deliberately NOT inheriting settings.LLM_BASE_URL: that gateway
                # is the deployer's, and this key is the user's. Sending someone
                # else's credential to infrastructure they did not choose is a
                # leak, so a BYO credential always reaches the provider's own
                # endpoint (or its own azure_endpoint).
                base_url=None,
                source="product_byo",
            )
        logger.warning(
            "llm_credential_unreadable_falling_back",
            product_id=product.id,
            provider=credential.provider,
        )
    return _admin_default_config()


def build_model(config: LLMConfig) -> Model:
    """Build the Pydantic AI ``Model`` for *config*'s provider.

    Raises ``LLMConfigError`` for an unsupported provider, or for Azure without
    both an endpoint and an API version — a clear configuration error rather than
    a partially-configured client that fails on the wire.
    """
    if config.provider not in LLM_PROVIDERS:
        raise LLMConfigError(
            f"Unsupported LLM provider {config.provider!r}; expected one of {LLM_PROVIDERS}"
        )
    # Raises for a provider that cannot honour a custom endpoint, so a base URL
    # is never silently dropped while traffic keeps hitting the public API.
    endpoint = _base_url_kwargs(config)

    if config.provider == "openai":
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        return OpenAIChatModel(
            config.model, provider=OpenAIProvider(api_key=config.api_key, **endpoint)
        )

    if config.provider == "anthropic":
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider

        return AnthropicModel(
            config.model, provider=AnthropicProvider(api_key=config.api_key, **endpoint)
        )

    if config.provider == "openrouter":
        from pydantic_ai.models.openrouter import OpenRouterModel
        from pydantic_ai.providers.openrouter import OpenRouterProvider

        # OpenRouter names models "<upstream-provider>/<model>"; a bare name makes
        # the SDK fail while splitting it. Reject it here with a message that says
        # what to fix, rather than an unpack error from deep in the provider.
        if "/" not in config.model.removeprefix("~"):
            raise LLMConfigError(
                f"OpenRouter model names must be '<provider>/<model>' "
                f"(e.g. 'anthropic/claude-sonnet-4.6'), got {config.model!r}"
            )
        return OpenRouterModel(config.model, provider=OpenRouterProvider(api_key=config.api_key))

    # azure — an OpenAI-compatible deployment, so it rides OpenAIChatModel with
    # the Azure provider.
    from pydantic_ai.models.openai import OpenAIChatModel

    return OpenAIChatModel(config.model, provider=_azure_provider(config))


def _base_url_kwargs(config: LLMConfig) -> dict[str, str]:
    """Return the ``base_url`` kwarg for *config*'s provider, or an empty dict.

    Empty means "use the provider's own default endpoint". Raises when a base URL
    is set for a provider that cannot accept one — dropping it silently would
    leave traffic on the public API while the operator believed it was routed
    through their gateway.
    """
    error = base_url_config_error(config.provider, config.base_url)
    if error:
        raise LLMConfigError(error)
    return {"base_url": config.base_url} if config.base_url else {}


def _azure_provider(config: LLMConfig) -> object:
    """Build the Azure provider, validating the endpoint/api-version combination.

    The last of the three boundaries that apply ``azure_config_error`` — this one
    catches a credential that predates the rule (or was written directly to the
    DB), so an incoherent pair can never reach the SDK.
    """
    from pydantic_ai.providers.azure import AzureProvider

    error = azure_config_error(config.azure_endpoint, config.azure_api_version)
    if error:
        raise LLMConfigError(error)
    if is_azure_v1_endpoint(str(config.azure_endpoint)):
        # The v1 API rejects api_version outright, so it must not be passed.
        return AzureProvider(azure_endpoint=config.azure_endpoint, api_key=config.api_key)
    return AzureProvider(
        azure_endpoint=config.azure_endpoint,
        api_version=config.azure_api_version,
        api_key=config.api_key,
    )
