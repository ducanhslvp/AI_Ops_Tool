import base64
import json
from abc import ABC, abstractmethod
from hashlib import sha256
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings


class SecretManager(ABC):
    @abstractmethod
    def encrypt(self, payload: dict) -> str:
        raise RuntimeError("Abstract secret provider method")

    @abstractmethod
    def decrypt(self, encrypted_payload: str) -> dict:
        raise RuntimeError("Abstract secret provider method")


class LocalAesSecretManager(SecretManager):
    """Local encrypted secret provider behind a replaceable Vault-like interface."""

    def __init__(self) -> None:
        settings = get_settings()
        raw_key = settings.secret_encryption_key or settings.jwt_secret_key
        self._cipher = AESGCM(sha256(raw_key.encode("utf-8")).digest())

    def encrypt(self, payload: dict) -> str:
        serialized = json.dumps(payload, sort_keys=True).encode("utf-8")
        nonce = os.urandom(12)
        ciphertext = self._cipher.encrypt(nonce, serialized, b"aiops-secret-v2")
        return "v2:" + base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")

    def decrypt(self, encrypted_payload: str) -> dict:
        if not encrypted_payload.startswith("v2:"):
            raise ValueError("Unsupported encrypted secret version; rotate this credential")
        raw = base64.urlsafe_b64decode(encrypted_payload[3:].encode("ascii"))
        if len(raw) < 29:
            raise ValueError("Invalid encrypted secret payload")
        decrypted = self._cipher.decrypt(raw[:12], raw[12:], b"aiops-secret-v2")
        return json.loads(decrypted.decode("utf-8"))
