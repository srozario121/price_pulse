"""Unit tests for the at-rest secret encryption helper (Item 16).

Arrange-Act-Assert throughout; isolated (no DB, no network).
"""

from __future__ import annotations

from app.core import crypto
from app.core.crypto import decrypt_secret, encrypt_secret, mask_secret


class TestEncryptDecrypt:
    def test_round_trips_a_secret(self):
        # Arrange
        plaintext = "sk-test-abcdef0123456789"

        # Act
        token = encrypt_secret(plaintext)

        # Assert
        assert decrypt_secret(token) == plaintext

    def test_ciphertext_is_not_the_plaintext(self):
        # Arrange
        plaintext = "sk-test-abcdef0123456789"

        # Act
        token = encrypt_secret(plaintext)

        # Assert — what lands in the DB column must not contain the key
        assert plaintext not in token
        assert token != plaintext

    def test_same_plaintext_encrypts_differently_each_time(self):
        # Arrange / Act — Fernet embeds a random IV per token
        first = encrypt_secret("same-key")
        second = encrypt_secret("same-key")

        # Assert — equal ciphertexts would leak "these two products share a key"
        assert first != second
        assert decrypt_secret(first) == decrypt_secret(second) == "same-key"

    def test_unicode_secret_round_trips(self):
        # Arrange / Act / Assert
        assert decrypt_secret(encrypt_secret("клю́ч-🔑")) == "клю́ч-🔑"


class TestDecryptFailure:
    def test_garbage_token_returns_none_instead_of_raising(self):
        # Act
        result = decrypt_secret("not-a-fernet-token")

        # Assert — a scrape must degrade to the admin default, never 500
        assert result is None

    def test_token_from_a_different_key_returns_none(self, monkeypatch):
        # Arrange — encrypt under one key, then rotate SECRET_KEY
        token = encrypt_secret("sk-original")
        crypto._fernet.cache_clear()
        monkeypatch.setattr(crypto.settings, "SECRET_KEY", "y" * 40)

        # Act
        result = decrypt_secret(token)

        # Assert — a rotated SECRET_KEY invalidates stored credentials quietly
        assert result is None

        # Cleanup — the Fernet is process-wide and lru_cached
        crypto._fernet.cache_clear()

    def test_empty_token_returns_none(self):
        assert decrypt_secret("") is None


class TestMaskSecret:
    def test_shows_only_the_last_four_characters(self):
        # Act
        hint = mask_secret("sk-live-abcdef4c2")

        # Assert
        assert hint == "…f4c2"
        assert "abcdef" not in hint

    def test_short_secret_reveals_nothing(self):
        # Act / Assert — fewer than 4 chars would otherwise expose the whole key
        assert mask_secret("ab") == "…"
        assert mask_secret("") == "…"
