import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("AUDIT_SECRET_KEY", "test-audit-secret-key")
os.environ.setdefault("TIER2_AUTH_SECRET", "test-tier2-secret")
os.environ.setdefault("TIER3_AUTH_SECRET", "test-tier3-secret")
os.environ.setdefault("SERVICE_AUTH_SECRET", "test-service-secret")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("TOKEN_SALT", "test-token-salt")
os.environ.setdefault("RE_ID_MAP_KEY", "test-re-id-key")
os.environ.setdefault("GATEWAY_RESOLVE_SECRET", "test-resolve-secret")
os.environ.setdefault("GATEWAY_INGEST_SECRET", "test-ingest-secret")
