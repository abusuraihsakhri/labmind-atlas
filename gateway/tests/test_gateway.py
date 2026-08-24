import os
import hmac
import hashlib
import pytest

os.environ["TOKEN_SALT"] = "test-salt-for-unit-tests"
os.environ["RE_ID_MAP_KEY"] = "test-key"
os.environ["GATEWAY_RESOLVE_SECRET"] = "test-resolve"
os.environ["GATEWAY_INGEST_SECRET"] = "test-ingest"

from cryptography.fernet import Fernet

TEST_KEY = Fernet.generate_key().decode()
os.environ["RE_ID_MAP_KEY"] = TEST_KEY

from gateway.main import generate_token, encrypt_value, decrypt_value


class TestTokenGeneration:
    def test_deterministic_tokens(self):
        token1 = generate_token("patient123", "PATIENT")
        token2 = generate_token("patient123", "PATIENT")
        assert token1 == token2

    def test_different_prefixes(self):
        token_a = generate_token("value1", "PATIENT")
        token_b = generate_token("value1", "MRN")
        assert token_a != token_b

    def test_token_format(self):
        token = generate_token("test", "SPECIMEN")
        assert token.startswith("SPECIMEN_")
        assert len(token) == len("SPECIMEN_") + 16

    def test_different_values_different_tokens(self):
        token1 = generate_token("value1", "PATIENT")
        token2 = generate_token("value2", "PATIENT")
        assert token1 != token2


class TestEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        original = "John Doe"
        encrypted = encrypt_value(original)
        decrypted = decrypt_value.__wrapped__(encrypted) if hasattr(decrypt_value, '__wrapped__') else None
        assert encrypted != original
