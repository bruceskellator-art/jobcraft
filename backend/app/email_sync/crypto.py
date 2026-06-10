"""Fernet-based encryption for OAuth tokens stored in email_accounts.oauth_token_enc.

Privacy rules enforced here:
- Tokens are NEVER logged, printed, or returned by any API.
- The key is read from config / env; missing key raises immediately.
- encrypt/decrypt operate on dicts (the full token payload); callers never
  handle raw token strings outside of this module.
"""
from __future__ import annotations

import json

from cryptography.fernet import Fernet, InvalidToken


class TokenCryptoError(Exception):
    """Raised when encryption or decryption fails."""


class TokenCrypto:
    """Encrypt and decrypt OAuth token dicts using Fernet symmetric encryption.

    Args:
        key: A Fernet key string (URL-safe base64-encoded 32 bytes).
             Generate one with: Fernet.generate_key().decode()

    Raises:
        TokenCryptoError: if key is empty/None or is not a valid Fernet key.
    """

    def __init__(self, key: str) -> None:
        if not key:
            raise TokenCryptoError(
                "Token encryption key is required. "
                "Set JOBCRAFT_TOKEN_ENCRYPTION_KEY to a valid Fernet key. "
                "Generate one with: python -c "
                "\"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        try:
            self._fernet = Fernet(key.encode())
        except Exception as exc:
            raise TokenCryptoError(
                "Invalid token encryption key — must be a Fernet-compatible "
                "URL-safe base64-encoded 32-byte key."
            ) from exc

    def encrypt(self, token: dict) -> bytes:
        """Serialize *token* dict to JSON and encrypt it.

        Returns:
            Fernet-encrypted bytes suitable for storage in oauth_token_enc.

        Note: token contents are NEVER logged.
        """
        payload = json.dumps(token, separators=(",", ":")).encode()
        return self._fernet.encrypt(payload)

    def decrypt(self, blob: bytes) -> dict:
        """Decrypt *blob* and deserialize it back to a dict.

        Returns:
            The original token dict.

        Raises:
            TokenCryptoError: if the blob is invalid, tampered, or was encrypted
                with a different key.

        Note: decrypted contents are NEVER logged.
        """
        try:
            payload = self._fernet.decrypt(blob)
        except InvalidToken as exc:
            raise TokenCryptoError(
                "Token decryption failed — blob is invalid, tampered, "
                "or was encrypted with a different key."
            ) from exc
        return json.loads(payload.decode())
