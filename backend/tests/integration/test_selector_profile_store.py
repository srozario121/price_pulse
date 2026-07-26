"""Integration tests for the selector-profile store (Item 16).

Arrange-Act-Assert throughout; Postgres testcontainer, because the store creates
rows with generated ids and relies on the unique-per-host constraint.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.enums import SelectorProfileStatus
from app.models.selector_profile import SelectorProfile
from app.services import selector_profile_service as store
from app.services.llm.schemas import SelectorSuggestion

pytestmark = pytest.mark.integration

_HOST = "shop.example.com"


class TestGetActiveSelector:
    async def test_returns_none_when_the_host_has_no_profile(self, pg_session):
        assert await store.get_active_selector(pg_session, "unknown.example.com") is None

    async def test_returns_none_for_a_profile_with_no_promoted_selector(self, pg_session):
        # Arrange — the placeholder row that holds cooldown state before any heal
        await store.get_or_create_profile(pg_session, _HOST, "generic")

        # Act / Assert
        assert await store.get_active_selector(pg_session, _HOST) is None

    async def test_returns_none_for_an_active_profile_with_no_selector(self, pg_session):
        # Arrange — an inconsistent row (e.g. hand-edited at runtime, which the
        # store is explicitly designed to allow) must not hand scrapers a None
        profile = await store.get_or_create_profile(pg_session, _HOST, "generic")
        profile.status = SelectorProfileStatus.ACTIVE
        profile.price_selector = None
        await pg_session.flush()

        # Act / Assert
        assert await store.get_active_selector(pg_session, _HOST) is None

    async def test_returns_none_for_a_stale_profile_even_with_a_selector(self, pg_session):
        # Arrange — a previously-healed host that just missed again
        profile = await store.get_or_create_profile(pg_session, _HOST, "generic")
        profile.price_selector = ".p"
        profile.status = SelectorProfileStatus.STALE
        await pg_session.flush()

        # Act / Assert — a stale selector must not keep being handed to scrapers
        assert await store.get_active_selector(pg_session, _HOST) is None

    async def test_returns_the_promoted_selector_when_active(self, pg_session):
        # Arrange
        profile = await store.get_or_create_profile(pg_session, _HOST, "generic")
        await store.promote(
            pg_session,
            profile,
            SelectorSuggestion(price_selector="#bb .p", currency_selector=".c", confidence=0.9),
            provider="openai",
            model="gpt-5.2",
        )

        # Act
        learned = await store.get_active_selector(pg_session, _HOST)

        # Assert
        assert learned is not None
        assert learned.price_selector == "#bb .p"
        assert learned.currency_selector == ".c"


class TestGetOrCreateProfile:
    async def test_creates_a_stale_placeholder(self, pg_session):
        # Act
        profile = await store.get_or_create_profile(pg_session, _HOST, "generic")

        # Assert
        assert profile.id is not None
        assert profile.status == SelectorProfileStatus.STALE
        assert profile.version == 0
        assert profile.failed_attempts == 0

    async def test_is_idempotent_for_the_same_host(self, pg_session):
        # Act
        first = await store.get_or_create_profile(pg_session, _HOST, "generic")
        second = await store.get_or_create_profile(pg_session, _HOST, "amazon")

        # Assert — one row per host, whichever product triggered it
        assert first.id == second.id

    async def test_host_is_unique_at_the_database_level(self, pg_session):
        # Arrange
        await store.get_or_create_profile(pg_session, _HOST, "generic")

        # Act / Assert — the constraint, not just the service, keeps hosts single
        pg_session.add(SelectorProfile(host=_HOST, source_type="generic"))
        with pytest.raises(IntegrityError):
            await pg_session.flush()


class TestMarkStale:
    async def test_demotes_an_active_profile(self, pg_session):
        # Arrange
        profile = await store.get_or_create_profile(pg_session, _HOST, "generic")
        profile.status = SelectorProfileStatus.ACTIVE
        await pg_session.flush()

        # Act
        marked, allowed = await store.mark_stale(pg_session, _HOST, "generic")

        # Assert
        assert marked.status == SelectorProfileStatus.STALE
        assert allowed is True

    async def test_leaves_a_failed_profile_parked(self, pg_session, monkeypatch):
        # Arrange — re-marking it stale would hand it a fresh cooldown window and
        # let it drift back into spending attempts
        monkeypatch.setattr(store.settings, "SELECTOR_MAX_REGEN_ATTEMPTS", 3)
        profile = await store.get_or_create_profile(pg_session, _HOST, "generic")
        profile.status = SelectorProfileStatus.FAILED
        profile.failed_attempts = 3
        await pg_session.flush()

        # Act
        marked, allowed = await store.mark_stale(pg_session, _HOST, "generic")

        # Assert
        assert marked.status == SelectorProfileStatus.FAILED
        assert allowed is False


class TestRecordAttemptFailure:
    async def test_increments_the_budget_and_records_the_reason(self, pg_session, monkeypatch):
        # Arrange
        monkeypatch.setattr(store.settings, "SELECTOR_MAX_REGEN_ATTEMPTS", 3)
        profile = await store.get_or_create_profile(pg_session, _HOST, "generic")

        # Act
        await store.record_attempt_failure(pg_session, profile, "provider timeout")

        # Assert
        assert profile.failed_attempts == 1
        assert profile.detail == "provider timeout"
        assert profile.last_attempt_at is not None
        assert profile.status != SelectorProfileStatus.FAILED

    async def test_parks_the_host_once_the_budget_is_spent(self, pg_session, monkeypatch):
        # Arrange
        monkeypatch.setattr(store.settings, "SELECTOR_MAX_REGEN_ATTEMPTS", 2)
        profile = await store.get_or_create_profile(pg_session, _HOST, "generic")

        # Act
        await store.record_attempt_failure(pg_session, profile, "fail 1")
        await store.record_attempt_failure(pg_session, profile, "fail 2")

        # Assert
        assert profile.status == SelectorProfileStatus.FAILED


class TestPromote:
    async def test_bumps_the_version_and_clears_the_failure_state(self, pg_session):
        # Arrange — a host mid-way through its budget
        profile = await store.get_or_create_profile(pg_session, _HOST, "generic")
        await store.record_attempt_failure(pg_session, profile, "earlier failure")

        # Act
        await store.promote(
            pg_session,
            profile,
            SelectorSuggestion(price_selector="#bb .p", confidence=0.77),
            provider="anthropic",
            model="claude-sonnet-4-5",
        )

        # Assert
        assert profile.status == SelectorProfileStatus.ACTIVE
        assert profile.version == 1
        assert profile.failed_attempts == 0
        assert profile.detail is None
        assert profile.confidence == pytest.approx(0.77)
        assert profile.generated_by_provider == "anthropic"
        assert profile.last_validated_at is not None

    async def test_successive_promotions_keep_incrementing_the_version(self, pg_session):
        # Arrange
        profile = await store.get_or_create_profile(pg_session, _HOST, "generic")

        # Act
        for _ in range(3):
            await store.promote(
                pg_session,
                profile,
                SelectorSuggestion(price_selector=".p", confidence=0.5),
                provider="openai",
                model="gpt-5.2",
            )

        # Assert — the version is the audit trail of how often this host drifted
        assert profile.version == 3


class TestReviveForReport:
    async def test_clears_a_spent_budget(self, pg_session, monkeypatch):
        # Arrange — without revival a failed host could never heal again
        monkeypatch.setattr(store.settings, "SELECTOR_MAX_REGEN_ATTEMPTS", 2)
        profile = await store.get_or_create_profile(pg_session, _HOST, "generic")
        profile.status = SelectorProfileStatus.FAILED
        profile.failed_attempts = 2
        await pg_session.flush()

        # Act
        revived, allowed = await store.revive_for_report(pg_session, _HOST, "generic")

        # Assert
        assert revived.failed_attempts == 0
        assert revived.status == SelectorProfileStatus.STALE
        assert allowed is True

    async def test_still_respects_the_cooldown(self, pg_session, monkeypatch):
        # Arrange — a report does not license immediate duplicate work
        monkeypatch.setattr(store.settings, "SELECTOR_REGEN_COOLDOWN_HOURS", 6)
        profile = await store.get_or_create_profile(pg_session, _HOST, "generic")
        profile.last_attempt_at = datetime.now(UTC) - timedelta(hours=1)
        await pg_session.flush()

        # Act
        _, allowed = await store.revive_for_report(pg_session, _HOST, "generic")

        # Assert
        assert allowed is False
