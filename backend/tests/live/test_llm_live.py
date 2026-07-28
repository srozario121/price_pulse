"""Live-provider smoke tests for LLM selector generation (Item 16).

**These call a real LLM provider and spend real money.** They are marked
``live_api`` and therefore excluded from the default run (``-m 'not live_api'``
in ``pyproject.toml``) and from CI. Run them deliberately:

    make test-llm-live

They exist because every other selector test substitutes a Pydantic AI
``FunctionModel`` with ``ALLOW_MODEL_REQUESTS = False`` — deliberately, so no
unit or integration test can reach a provider. That leaves a whole class of
failure invisible: a wrong model name, a revoked or misscoped key, a gateway
that rejects the request, a provider that stops honouring ``output_type``. None
of those are catchable without one real call, and all of them break selector
healing silently in production, because the regeneration task swallows provider
errors by design.

Scope is deliberately one call on a small payload: enough to prove the
credential and the whole generate→validate path, cheap enough to run often.
The full self-healing loop against the live stack is
``docs/behaviour/selector_healing.feature`` (``make test-e2e-llm``).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.product import Product
from app.services.llm.client import build_model, resolve_llm_config
from app.services.selector_generation import (
    generate_selector,
    trim_html,
    validate_selector,
)

pytestmark = [pytest.mark.live_api, pytest.mark.asyncio]

# A product page whose price sits in an element NO built-in selector would find:
# the class names are deliberately unlike anything in amazon.py's hardcoded list
# or a conventional `.price`. If the model returns something that extracts
# 129.50 here, it genuinely read the markup rather than guessing a common class.
#
# The decoys matter as much as the target: a struck-through was-price, a
# subscription price, and a review count that parses as a plausible number are
# all present, so a selector that merely finds *a* number is not good enough.
_LIVE_HTML = """
<!doctype html>
<html><head><title>Acme Widget Pro — Acme Store</title></head>
<body>
  <div id="pdp">
    <h1 class="x7k2-title">Acme Widget Pro</h1>
    <span class="x7k2-was" aria-label="was">£249.99</span>
    <div class="x7k2-buybox">
      <span class="x7k2-amount-now">£129.50</span>
      <span class="x7k2-vat">inc. VAT</span>
    </div>
    <div class="x7k2-sub">Subscribe &amp; save: £119.00 / month</div>
    <span class="x7k2-reviews">1,204 reviews</span>
  </div>
</body></html>
"""

_EXPECTED_PRICE = Decimal("129.50")


@pytest.fixture(autouse=True)
def require_a_configured_key():
    """Skip (never fail) when no credential is configured.

    A developer without a key must be able to run ``make test-llm-live`` and get
    a clear skip rather than a failure that looks like a broken build.
    """
    if not settings.LLM_API_KEY:
        pytest.skip("No LLM_API_KEY configured — set one in .env to exercise the live provider")


@pytest.fixture()
async def product(db_session) -> Product:
    """A product with no BYO credential, so resolution uses the admin default."""
    item = Product(
        id=1,
        name="Acme Widget Pro",
        url="https://shop.example.com/p/widget-pro",
        source_type="generic",
        css_selector=".price",
    )
    db_session.add(item)
    await db_session.flush()
    return item


class TestLiveCredential:
    async def test_the_configured_credential_resolves(self, db_session, product):
        # Act
        config = await resolve_llm_config(db_session, product)

        # Assert — proves the key reached Settings and the admin-default path
        assert config is not None
        assert config.source == "admin_default"
        assert config.provider == settings.LLM_PROVIDER
        assert config.model == settings.LLM_MODEL

    async def test_the_client_targets_the_expected_endpoint(self, db_session, product):
        # Arrange
        config = await resolve_llm_config(db_session, product)

        # Act
        model = build_model(config)

        # Assert — catches a gateway typo before it costs a request
        expected = settings.LLM_BASE_URL or "https://api.openai.com/v1"
        if config.provider == "openai":
            assert str(model.client.base_url).rstrip("/") == expected.rstrip("/")
        print(f"\n  provider={config.provider} model={config.model} endpoint={expected}")


class TestLiveGeneration:
    async def test_real_provider_returns_a_selector_that_validates(self, db_session, product):
        """The whole point: a real call produces a selector that actually works.

        Asserted through :func:`validate_selector` — the same promotion gate the
        regeneration task uses — rather than by string-matching an expected
        selector, because there are several correct answers for this markup
        (``.x7k2-amount-now``, ``#pdp .x7k2-amount-now``, …) and pinning one
        would make the test fail on a perfectly good result.
        """
        # Act — one real provider call
        result = await generate_selector(db_session, product, _LIVE_HTML)

        # Assert
        assert result is not None, "generation returned None despite a configured key"
        suggestion, config = result
        print(
            f"\n  provider={config.provider} model={config.model}"
            f"\n  price_selector={suggestion.price_selector!r}"
            f"\n  currency_selector={suggestion.currency_selector!r}"
            f"\n  confidence={suggestion.confidence}"
        )

        extracted = validate_selector(_LIVE_HTML, suggestion.price_selector)
        assert extracted is not None, (
            f"selector {suggestion.price_selector!r} extracted no plausible price — "
            "it would have been rejected by the promotion gate"
        )
        # The buy-box price, not the was-price, the subscription price, or the
        # review count. This is the assertion that would catch a model or prompt
        # regression that a mere "extracts a number" check would wave through.
        assert extracted == _EXPECTED_PRICE, (
            f"selector {suggestion.price_selector!r} extracted {extracted}, "
            f"expected the buy-box price {_EXPECTED_PRICE}"
        )

    async def test_trimmed_payload_keeps_the_price_markup(self):
        # Arrange / Act — no provider call; guards the input to the one above
        trimmed = trim_html(_LIVE_HTML)

        # Assert
        assert "x7k2-amount-now" in trimmed
        assert "129.50" in trimmed
        assert len(trimmed.encode()) <= settings.SELECTOR_HTML_MAX_BYTES


class TestLiveCredentialIsolation:
    async def test_a_byo_credential_takes_precedence_over_the_admin_key(self, db_session, product):
        """A BYO row must win — otherwise a user's product silently bills the deployer.

        Uses a deliberately invalid BYO key and asserts only the *resolution*, so
        no second provider call is made.
        """
        # Arrange
        from app.core.crypto import encrypt_secret
        from app.models.product_llm_credential import ProductLLMCredential

        db_session.add(
            ProductLLMCredential(
                id=1,
                product_id=product.id,
                provider="openai",
                model="gpt-5.2",
                encrypted_api_key=encrypt_secret("sk-not-a-real-key"),
            )
        )
        await db_session.flush()

        # Act
        config = await resolve_llm_config(db_session, product)

        # Assert
        assert config.source == "product_byo"
        assert config.api_key != settings.LLM_API_KEY
        # And the deployer's gateway is not applied to someone else's key
        assert config.base_url is None

        # Cleanup so the admin-default tests are unaffected if order changes
        stored = await db_session.scalar(
            select(ProductLLMCredential).where(ProductLLMCredential.product_id == product.id)
        )
        await db_session.delete(stored)
        await db_session.flush()
