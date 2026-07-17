"""Unit tests for the shared anti-blocking primitives (Item 15).

Arrange-Act-Assert throughout; isolated (no network, no Playwright).
"""

from __future__ import annotations

import pytest

from app.models.enums import ExtractionStatus
from app.scrapers.anti_blocking import (
    USER_AGENTS,
    ProxyRotator,
    build_headers,
    choose_user_agent,
    classify_block,
    normalise_proxy,
)

_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_EDGE_UA = _CHROME_UA + " Edg/124.0.0.0"
_FIREFOX_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0"
_MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.6 Mobile Safari/537.36"
)


# ── ProxyRotator ────────────────────────────────────────────────────────────────


class TestProxyRotator:
    def test_seeded_list_rotates_and_wraps(self):
        # Arrange
        rotator = ProxyRotator(["p1", "p2", "p3"], start=0)

        # Act / Assert — advances then wraps back to the first
        assert rotator.enabled is True
        assert rotator.count == 3
        assert rotator.current() == "p1"
        assert rotator.next_proxy() == "p2"
        assert rotator.next_proxy() == "p3"
        assert rotator.next_proxy() == "p1"

    def test_start_index_offsets_current(self):
        # Arrange / Act
        rotator = ProxyRotator(["p1", "p2", "p3"], start=1)

        # Assert
        assert rotator.current() == "p2"

    def test_empty_list_disables_proxying(self):
        # Arrange / Act
        rotator = ProxyRotator([])

        # Assert
        assert rotator.enabled is False
        assert rotator.count == 0
        assert rotator.current() is None
        assert rotator.next_proxy() is None

    def test_defaults_to_settings_proxy_urls(self, monkeypatch):
        # Arrange — patch the shared settings singleton
        from app.core.config import settings

        monkeypatch.setattr(settings, "PROXY_URLS", ["http://seeded:8080"])

        # Act
        rotator = ProxyRotator(start=0)

        # Assert
        assert rotator.current() == "http://seeded:8080"


# ── normalise_proxy ───────────────────────────────────────────────────────────────


class TestNormaliseProxy:
    def test_credentialed_proxy_splits_into_both_shapes(self):
        # Arrange
        url = "http://user:p%40ss@host.example.com:8080"

        # Act
        cfg = normalise_proxy(url)

        # Assert — httpx keeps the whole URL; playwright separates credentials,
        # and percent-encoded characters are decoded
        assert cfg.httpx == url
        assert cfg.playwright == {
            "server": "http://host.example.com:8080",
            "username": "user",
            "password": "p@ss",
        }

    def test_proxy_without_credentials_or_port(self):
        # Arrange / Act
        cfg = normalise_proxy("http://host.example.com")

        # Assert
        assert cfg.playwright == {"server": "http://host.example.com"}

    def test_malformed_proxy_raises(self):
        # Arrange / Act / Assert
        with pytest.raises(ValueError, match="Malformed proxy URL"):
            normalise_proxy("not-a-url")


# ── build_headers / choose_user_agent ─────────────────────────────────────────────


class TestHeaders:
    def test_chrome_ua_gets_matched_client_hints(self):
        # Arrange / Act
        headers = build_headers(_CHROME_UA)

        # Assert
        assert headers["User-Agent"] == _CHROME_UA
        assert headers["Accept-Language"] == "en-GB,en;q=0.9"
        assert "Google Chrome" in headers["Sec-CH-UA"]
        assert '"124"' in headers["Sec-CH-UA"]
        assert headers["Sec-CH-UA-Mobile"] == "?0"
        assert headers["Sec-CH-UA-Platform"] == '"Windows"'

    def test_edge_ua_reports_edge_brand(self):
        # Arrange / Act
        headers = build_headers(_EDGE_UA)

        # Assert
        assert "Microsoft Edge" in headers["Sec-CH-UA"]

    def test_mobile_ua_sets_mobile_hint_and_platform(self):
        # Arrange / Act
        headers = build_headers(_MOBILE_UA)

        # Assert
        assert headers["Sec-CH-UA-Mobile"] == "?1"
        assert headers["Sec-CH-UA-Platform"] == '"Android"'

    def test_firefox_ua_omits_client_hints(self):
        # Arrange / Act
        headers = build_headers(_FIREFOX_UA)

        # Assert — Firefox does not send Sec-CH-UA client hints
        assert "Sec-CH-UA" not in headers
        assert headers["Accept-Language"] == "en-GB,en;q=0.9"

    def test_choose_user_agent_from_pool(self):
        # Arrange / Act
        ua = choose_user_agent()

        # Assert
        assert ua in USER_AGENTS


# ── classify_block ────────────────────────────────────────────────────────────────


class TestClassifyBlock:
    def test_normal_product_html_is_not_a_block(self):
        # Arrange / Act / Assert
        assert classify_block(200, "<html><body>£19.99 in stock</body></html>") is None

    @pytest.mark.parametrize("status", [429, 503])
    def test_rate_limit_and_unavailable_are_blocked(self, status):
        # Arrange / Act / Assert
        assert classify_block(status, "<html>temporarily unavailable</html>") == (
            ExtractionStatus.BLOCKED
        )

    def test_amazon_robot_check_is_captcha_even_on_200(self):
        # Arrange
        html = "<html><body>Enter the characters you see below</body></html>"

        # Act / Assert
        assert classify_block(200, html) == ExtractionStatus.CAPTCHA

    def test_recaptcha_marker_is_captcha(self):
        # Arrange / Act / Assert
        assert classify_block(200, '<div class="g-recaptcha"></div>') == ExtractionStatus.CAPTCHA

    def test_challenge_markers_win_over_503_status(self):
        # Arrange — a Cloudflare JS challenge served with 503 is a CAPTCHA, not a bare block
        html = "<html><body>Checking your browser before accessing</body></html>"

        # Act / Assert
        assert classify_block(503, html) == ExtractionStatus.CAPTCHA

    def test_access_denied_marker_is_blocked(self):
        # Arrange / Act / Assert
        assert classify_block(200, "<html><body>Access Denied</body></html>") == (
            ExtractionStatus.BLOCKED
        )

    def test_none_html_is_safe(self):
        # Arrange / Act / Assert
        assert classify_block(200, None) is None
