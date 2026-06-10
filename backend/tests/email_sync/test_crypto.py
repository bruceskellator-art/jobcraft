"""Tests for TokenCrypto — encrypt/decrypt round-trip and key validation."""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app.email_sync.crypto import TokenCrypto, TokenCryptoError


@pytest.fixture
def fernet_key() -> str:
    return Fernet.generate_key().decode()


@pytest.fixture
def crypto(fernet_key: str) -> TokenCrypto:
    return TokenCrypto(fernet_key)


class TestTokenCryptoRoundTrip:
    def test_round_trips_simple_token(self, crypto: TokenCrypto) -> None:
        # Arrange
        token = {"access_token": "tok_abc123", "expires_in": 3600}

        # Act
        encrypted = crypto.encrypt(token)
        decrypted = crypto.decrypt(encrypted)

        # Assert
        assert decrypted == token

    def test_round_trips_token_with_nested_values(self, crypto: TokenCrypto) -> None:
        # Arrange
        token = {
            "access_token": "at_xyz",
            "refresh_token": "rt_abc",
            "token_type": "Bearer",
            "scope": "gmail.readonly",
            "expires_in": 3600,
        }

        # Act
        blob = crypto.encrypt(token)
        result = crypto.decrypt(blob)

        # Assert
        assert result == token

    def test_encrypt_returns_bytes(self, crypto: TokenCrypto) -> None:
        blob = crypto.encrypt({"tok": "val"})
        assert isinstance(blob, bytes)

    def test_different_encryptions_of_same_token_produce_different_ciphertext(
        self, crypto: TokenCrypto
    ) -> None:
        # Fernet uses a random IV so ciphertexts differ even for equal plaintexts
        token = {"access_token": "same"}
        blob1 = crypto.encrypt(token)
        blob2 = crypto.encrypt(token)
        assert blob1 != blob2  # different IVs
        # Both decrypt to the same value
        assert crypto.decrypt(blob1) == crypto.decrypt(blob2) == token


class TestTokenCryptoWrongKey:
    def test_wrong_key_raises_token_crypto_error(self, fernet_key: str) -> None:
        # Arrange
        crypto_a = TokenCrypto(fernet_key)
        crypto_b = TokenCrypto(Fernet.generate_key().decode())
        blob = crypto_a.encrypt({"access_token": "secret"})

        # Act / Assert
        with pytest.raises(TokenCryptoError):
            crypto_b.decrypt(blob)

    def test_tampered_blob_raises_token_crypto_error(self, crypto: TokenCrypto) -> None:
        blob = crypto.encrypt({"access_token": "secret"})
        tampered = blob[:-4] + b"xxxx"

        with pytest.raises(TokenCryptoError):
            crypto.decrypt(tampered)


class TestTokenCryptoInvalidKey:
    def test_empty_key_raises_token_crypto_error(self) -> None:
        with pytest.raises(TokenCryptoError):
            TokenCrypto("")

    def test_garbage_key_raises_token_crypto_error(self) -> None:
        with pytest.raises(TokenCryptoError):
            TokenCrypto("not-a-valid-fernet-key")
