"""Unit tests for host normalisation and the regeneration guards (Item 16).

Arrange-Act-Assert throughout. ``regeneration_allowed`` is a pure function, so
the cooldown and attempt-budget boundaries are exercised without a database.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models.enums import SelectorProfileStatus
from app.models.selector_profile import SelectorProfile
from app.services import selector_profile_service
from app.services.selector_profile_service import host_for_url, regeneration_allowed

_NOW = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)


def _profile(**kwargs) -> SelectorProfile:
    defaults = {
        "host": "shop.example.com",
        "source_type": "generic",
        "status": SelectorProfileStatus.STALE,
        "version": 0,
        "failed_attempts": 0,
        "last_attempt_at": None,
    }
    defaults.update(kwargs)
    return SelectorProfile(**defaults)


class TestHostForUrl:
    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("https://www.currys.co.uk/products/x", "currys.co.uk"),
            ("https://currys.co.uk/products/x", "currys.co.uk"),
            ("https://WWW.Amazon.CO.UK/dp/B01", "amazon.co.uk"),
            ("http://shop.example.com:8080/p/1", "shop.example.com"),
            ("not-a-url", ""),
        ],
    )
    def test_normalises_to_a_stable_profile_key(self, url, expected):
        assert host_for_url(url) == expected

    def test_regional_storefronts_stay_distinct(self):
        # Arrange / Act / Assert — amazon.co.uk and amazon.com ship different
        # markup, so they must heal independently
        assert host_for_url("https://amazon.co.uk/dp/B01") != host_for_url(
            "https://amazon.com/dp/B01"
        )

    def test_www_and_bare_host_share_one_profile(self):
        # Otherwise one retailer would pay for two generations
        assert host_for_url("https://www.currys.co.uk/x") == host_for_url("https://currys.co.uk/y")


class TestRegenerationAllowed:
    def test_fresh_profile_with_no_attempts_is_allowed(self):
        assert regeneration_allowed(_profile(), _NOW) is True

    def test_failed_status_is_never_allowed(self):
        # Arrange — budget spent; only a user report revives it
        profile = _profile(status=SelectorProfileStatus.FAILED)

        # Act / Assert
        assert regeneration_allowed(profile, _NOW) is False

    def test_exhausted_attempt_budget_is_not_allowed(self, monkeypatch):
        # Arrange
        monkeypatch.setattr(selector_profile_service.settings, "SELECTOR_MAX_REGEN_ATTEMPTS", 3)
        profile = _profile(failed_attempts=3)

        # Act / Assert
        assert regeneration_allowed(profile, _NOW) is False

    def test_attempt_inside_the_cooldown_window_is_not_allowed(self, monkeypatch):
        # Arrange — last attempt 1 hour ago, cooldown is 6 hours
        monkeypatch.setattr(selector_profile_service.settings, "SELECTOR_REGEN_COOLDOWN_HOURS", 6)
        profile = _profile(last_attempt_at=_NOW - timedelta(hours=1))

        # Act / Assert
        assert regeneration_allowed(profile, _NOW) is False

    def test_attempt_exactly_at_the_cooldown_boundary_is_allowed(self, monkeypatch):
        # Arrange — the window is inclusive at its edge
        monkeypatch.setattr(selector_profile_service.settings, "SELECTOR_REGEN_COOLDOWN_HOURS", 6)
        profile = _profile(last_attempt_at=_NOW - timedelta(hours=6))

        # Act / Assert
        assert regeneration_allowed(profile, _NOW) is True

    def test_attempt_past_the_cooldown_window_is_allowed(self, monkeypatch):
        monkeypatch.setattr(selector_profile_service.settings, "SELECTOR_REGEN_COOLDOWN_HOURS", 6)
        profile = _profile(last_attempt_at=_NOW - timedelta(hours=7))
        assert regeneration_allowed(profile, _NOW) is True

    def test_naive_timestamp_is_treated_as_utc(self, monkeypatch):
        # Arrange — SQLite round-trips DateTime(timezone=True) as naive; a naive
        # value must not raise on comparison
        monkeypatch.setattr(selector_profile_service.settings, "SELECTOR_REGEN_COOLDOWN_HOURS", 6)
        profile = _profile(last_attempt_at=(_NOW - timedelta(hours=1)).replace(tzinfo=None))

        # Act / Assert
        assert regeneration_allowed(profile, _NOW) is False
