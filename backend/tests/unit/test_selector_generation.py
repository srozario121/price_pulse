"""Unit tests for HTML trimming, selector validation and LLM generation (Item 16).

Arrange-Act-Assert throughout. No provider is ever contacted: the agent is
overridden with Pydantic AI's ``FunctionModel``/``TestModel`` and
``models.ALLOW_MODEL_REQUESTS`` is disabled for the whole module, so a wiring
mistake that would reach a real API fails the test instead of billing an account.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic_ai import ModelResponse, TextPart, models
from pydantic_ai.models.function import FunctionModel

from app.models.product import Product
from app.services import selector_generation
from app.services.llm import client as llm_client
from app.services.llm.client import selector_agent
from app.services.llm.schemas import SelectorSuggestion
from app.services.selector_generation import (
    SelectorGenerationError,
    generate_selector,
    trim_html,
    validate_selector,
)

# A wiring bug must never reach a provider from a unit test.
models.ALLOW_MODEL_REQUESTS = False

_PRODUCT_HTML = """
<html><head><title>Widget</title><style>.a{color:red}</style>
<script>var tracking = {price: 999};</script></head>
<body><!-- build 42 -->
  <h1>Widget Pro</h1>
  <span class="was-price">£249.99</span>
  <div id="buybox"><span class="price-now">£129.50</span></div>
  <span class="review-count">1,204 reviews</span>
  <svg><path d="M0 0"/></svg>
</body></html>
"""


def _suggestion_model(payload: str) -> FunctionModel:
    """A FunctionModel that always replies with *payload* as the structured output."""

    def respond(messages, info):  # noqa: ANN001, ARG001
        return ModelResponse(parts=[TextPart(content=payload)])

    return FunctionModel(respond)


# ── trim_html ──────────────────────────────────────────────────────────────────


class TestTrimHtml:
    def test_strips_scripts_styles_svg_and_comments(self):
        # Act
        trimmed = trim_html(_PRODUCT_HTML, max_bytes=100_000)

        # Assert — none of the stripped content survives...
        assert "<script" not in trimmed
        assert "tracking" not in trimmed
        assert "<style" not in trimmed
        assert "<svg" not in trimmed
        assert "build 42" not in trimmed
        # ...while the markup the selector must target does
        assert 'class="price-now"' in trimmed
        assert "£129.50" in trimmed

    def test_caps_the_payload_at_max_bytes(self):
        # Arrange — a page far larger than the cap
        html = "<div>" + ("x" * 50_000) + "</div>"

        # Act
        trimmed = trim_html(html, max_bytes=1_000)

        # Assert
        assert len(trimmed.encode("utf-8")) <= 1_000

    def test_truncation_does_not_split_a_multibyte_character(self):
        # Arrange — every character is 3 bytes, so the cap lands mid-character
        html = "<div>" + ("€" * 500) + "</div>"

        # Act
        trimmed = trim_html(html, max_bytes=100)

        # Assert — decoding succeeded (no replacement chars, no exception)
        assert "�" not in trimmed
        assert len(trimmed.encode("utf-8")) <= 100

    def test_defaults_to_the_configured_cap(self, monkeypatch):
        # Arrange
        monkeypatch.setattr(selector_generation.settings, "SELECTOR_HTML_MAX_BYTES", 50)

        # Act
        trimmed = trim_html("<div>" + "y" * 500 + "</div>")

        # Assert
        assert len(trimmed.encode("utf-8")) <= 50

    def test_empty_html_is_handled(self):
        assert trim_html("", max_bytes=100) == ""


# ── validate_selector ──────────────────────────────────────────────────────────


class TestValidateSelector:
    def test_returns_the_price_a_good_selector_extracts(self):
        # Act
        price = validate_selector(_PRODUCT_HTML, "#buybox .price-now")

        # Assert
        assert price == Decimal("129.50")

    def test_locale_formatted_price_is_normalised(self):
        # Arrange — de-DE grouping: dot thousands, comma decimal
        html = '<div class="p">1.234,56 €</div>'

        # Act / Assert — reuses the shared normaliser, like the built-in selectors
        assert validate_selector(html, ".p") == Decimal("1234.56")

    def test_selector_matching_nothing_fails(self):
        assert validate_selector(_PRODUCT_HTML, ".does-not-exist") is None

    def test_selector_matching_non_numeric_text_fails(self):
        assert validate_selector(_PRODUCT_HTML, "h1") is None

    def test_malformed_selector_returns_none_instead_of_raising(self):
        # Act / Assert — a garbage suggestion must not crash the worker
        assert validate_selector(_PRODUCT_HTML, "<<<not css>>>") is None

    def test_implausible_price_is_rejected(self):
        # Arrange — a selector aimed at an order total, not a price
        html = '<div class="p">0</div><div class="q">99999999</div>'

        # Act / Assert — outside the plausible retail range, so not promotable
        assert validate_selector(html, ".p") is None
        assert validate_selector(html, ".q") is None

    def test_first_matching_element_with_a_plausible_price_wins(self):
        # Arrange — the selector matches a junk node before a real price
        html = '<div class="p">out of stock</div><div class="p">£42.00</div>'

        # Act / Assert — scanning past unparseable matches avoids a false reject
        assert validate_selector(html, ".p") == Decimal("42.00")


# ── generate_selector ──────────────────────────────────────────────────────────


@pytest.fixture()
async def product(db_session):
    """A persisted product; explicit id because SQLite will not autoincrement BigInteger."""
    item = Product(
        id=1, name="Widget Pro", url="https://shop.example.com/p/1", source_type="generic"
    )
    db_session.add(item)
    await db_session.flush()
    return item


@pytest.fixture()
def admin_llm(monkeypatch):
    """Configure a usable admin-default credential."""
    monkeypatch.setattr(llm_client.settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(llm_client.settings, "LLM_MODEL", "gpt-5.2")
    monkeypatch.setattr(llm_client.settings, "LLM_API_KEY", "sk-admin")


class TestGenerateSelector:
    async def test_returns_the_validated_suggestion_and_its_config(
        self, db_session, product, admin_llm
    ):
        # Arrange
        payload = '{"price_selector": "#buybox .price-now", "confidence": 0.9}'

        # Act
        with selector_agent.override(model=_suggestion_model(payload)):
            result = await generate_selector(db_session, product, _PRODUCT_HTML)

        # Assert
        assert result is not None
        suggestion, config = result
        assert isinstance(suggestion, SelectorSuggestion)
        assert suggestion.price_selector == "#buybox .price-now"
        assert suggestion.confidence == 0.9
        assert config.provider == "openai"
        assert config.source == "admin_default"

    async def test_returns_none_when_no_credential_resolves(self, db_session, product, monkeypatch):
        # Arrange — generation disabled (no BYO key, no admin default)
        monkeypatch.setattr(llm_client.settings, "LLM_API_KEY", "")

        # Act
        result = await generate_selector(db_session, product, _PRODUCT_HTML)

        # Assert — a no-op, not an error
        assert result is None

    async def test_provider_error_becomes_a_generation_error(self, db_session, product, admin_llm):
        # Arrange — the provider raises mid-run (timeout, 500, auth failure, …)
        def explode(messages, info):  # noqa: ANN001, ARG001
            raise RuntimeError("provider exploded")

        # Act / Assert — surfaced as a countable attempt, never an unhandled crash
        with selector_agent.override(model=FunctionModel(explode)):
            with pytest.raises(SelectorGenerationError, match="generation failed"):
                await generate_selector(db_session, product, _PRODUCT_HTML)

    async def test_unparseable_model_output_becomes_a_generation_error(
        self, db_session, product, admin_llm
    ):
        # Arrange — a reply that cannot satisfy the SelectorSuggestion schema
        payload = '{"confidence": "not-a-number"}'

        # Act / Assert
        with selector_agent.override(model=_suggestion_model(payload)):
            with pytest.raises(SelectorGenerationError):
                await generate_selector(db_session, product, _PRODUCT_HTML)

    async def test_bad_llm_config_becomes_a_generation_error(
        self, db_session, product, monkeypatch
    ):
        # Arrange — a key is set, but the provider is unusable
        monkeypatch.setattr(llm_client.settings, "LLM_API_KEY", "sk-admin")
        monkeypatch.setattr(llm_client.settings, "LLM_PROVIDER", "hal9000")

        # Act / Assert — a config error is a counted attempt, not a crash
        with pytest.raises(SelectorGenerationError, match="configuration error"):
            await generate_selector(db_session, product, _PRODUCT_HTML)

    async def test_high_confidence_does_not_bypass_the_validation_gate(
        self, db_session, product, admin_llm
    ):
        # Arrange — the model is maximally confident about a selector that matches
        # nothing on the page
        payload = '{"price_selector": ".ghost-price", "confidence": 1.0}'

        # Act
        with selector_agent.override(model=_suggestion_model(payload)):
            result = await generate_selector(db_session, product, _PRODUCT_HTML)

        # Assert — generation returns it, but validation is what decides
        # promotion, so confidence alone can never put a bad selector live
        assert result is not None
        suggestion, _ = result
        assert suggestion.confidence == 1.0
        assert validate_selector(_PRODUCT_HTML, suggestion.price_selector) is None

    def test_validation_is_a_plausibility_gate_not_a_correctness_proof(self):
        # Arrange — a review count parses as a plausible number
        # Act / Assert — documents a known limit of the gate: it proves the
        # selector extracts *a* plausible price, not that it extracts the *right*
        # one. Targeting the correct element is the model's job (steered by the
        # agent instructions); the gate only stops selectors that extract nothing.
        assert validate_selector(_PRODUCT_HTML, ".review-count") == Decimal("1204")


# ── SelectorSuggestion schema ──────────────────────────────────────────────────


class TestSelectorSuggestionSchema:
    def test_blank_price_selector_is_rejected(self):
        with pytest.raises(ValueError, match="must not be empty"):
            SelectorSuggestion(price_selector="   ", confidence=0.9)

    def test_confidence_is_bounded_to_zero_one(self):
        with pytest.raises(ValueError):
            SelectorSuggestion(price_selector=".p", confidence=1.5)

    def test_blank_currency_selector_normalises_to_none(self):
        suggestion = SelectorSuggestion(price_selector=".p", currency_selector="  ", confidence=0.5)
        assert suggestion.currency_selector is None

    def test_omitted_currency_selector_stays_none(self):
        # The common case: the currency sits in the same element as the price
        assert SelectorSuggestion(price_selector=".p", confidence=0.5).currency_selector is None

    def test_explicit_null_currency_selector_is_accepted(self):
        # Providers routinely emit an explicit null for an optional field
        suggestion = SelectorSuggestion(price_selector=".p", currency_selector=None, confidence=0.5)
        assert suggestion.currency_selector is None

    def test_currency_selector_is_kept_when_provided(self):
        suggestion = SelectorSuggestion(price_selector=".p", currency_selector=".c", confidence=0.5)
        assert suggestion.currency_selector == ".c"

    def test_selectors_are_stripped(self):
        suggestion = SelectorSuggestion(price_selector="  .p  ", confidence=0.5)
        assert suggestion.price_selector == ".p"
