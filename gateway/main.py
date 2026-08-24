import os
import json
import sqlite3
import hashlib
import hmac
import logging
from fastapi import FastAPI, HTTPException, BackgroundTasks, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timezone
import redis
from cryptography.fernet import Fernet
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger("labmind.gateway")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S%z",
)

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="LabMind On-Premises Gateway")
app.state.limiter = limiter

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
RE_ID_MAP_KEY = os.getenv("RE_ID_MAP_KEY")
GATEWAY_RESOLVE_SECRET = os.getenv("GATEWAY_RESOLVE_SECRET")
GATEWAY_INGEST_SECRET = os.getenv("GATEWAY_INGEST_SECRET")
TOKEN_SALT = os.getenv("TOKEN_SALT")

if not RE_ID_MAP_KEY:
    raise RuntimeError(
        "SECURITY EXCEPTION: RE_ID_MAP_KEY environment variable is not set. "
        "A secure AES key is required for patient mapping."
    )

if not GATEWAY_RESOLVE_SECRET:
    raise RuntimeError(
        "SECURITY EXCEPTION: GATEWAY_RESOLVE_SECRET environment variable is not set. "
        "A secure token is required for re-identification resolution."
    )

if not GATEWAY_INGEST_SECRET:
    raise RuntimeError(
        "SECURITY EXCEPTION: GATEWAY_INGEST_SECRET environment variable is not set. "
        "A secure token is required for event ingestion."
    )

if not TOKEN_SALT:
    raise RuntimeError(
        "SECURITY EXCEPTION: TOKEN_SALT environment variable is not set. "
        "A secure salt is required for token generation."
    )

# Initialize cryptography
fernet = Fernet(RE_ID_MAP_KEY.encode() if isinstance(RE_ID_MAP_KEY, str) else RE_ID_MAP_KEY)

from presidio_analyzer.nlp_engine import NlpEngineProvider
nlp_configuration = {
    "nlp_engine_name": "spacy",
    "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}]
}
nlp_engine_instance = NlpEngineProvider(nlp_configuration=nlp_configuration).create_engine()
analyzer = AnalyzerEngine(nlp_engine=nlp_engine_instance, supported_languages=["en"])
anonymizer = AnonymizerEngine()

# Setup Local SQLite for Encrypted Token Mapping
DB_PATH = "re_identification_map.db"

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=20.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS token_map (
            token VARCHAR(255) PRIMARY KEY,
            encrypted_value TEXT NOT NULL,
            entity_type VARCHAR(50) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

# Redis Client
redis_client = redis.Redis.from_url(REDIS_URL)

class IngestEventPayload(BaseModel):
    event_id: str
    event_type: str
    occurred_at: str
    raw_payload: dict

    class Config:
        json_schema_extra = {
            "example": {
                "event_id": "uuid",
                "event_type": "ORDER_PLACED",
                "occurred_at": "2026-08-24T12:00:00Z",
                "raw_payload": {}
            }
        }

# Cryptographic functions
def encrypt_value(value: str) -> str:
    return fernet.encrypt(value.encode()).decode()

def decrypt_value(token_or_encrypted: str) -> str:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT encrypted_value FROM token_map WHERE token = ?", (token_or_encrypted,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return fernet.decrypt(row[0].encode()).decode()
    raise ValueError("Token not found in local gateway database.")

# Helper to generate a deterministic token/alias using HMAC/Hash + Salt
def generate_token(value: str, prefix: str) -> str:
    hash_obj = hmac.new(TOKEN_SALT.encode(), value.encode(), hashlib.sha256)
    token = f"{prefix}_{hash_obj.hexdigest()[:16]}"
    
    # Store real identifier mapping securely
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        encrypted = encrypt_value(value)
        cursor.execute(
            "INSERT OR IGNORE INTO token_map (token, encrypted_value, entity_type) VALUES (?, ?, ?)",
            (token, encrypted, prefix)
        )
        conn.commit()
    except Exception as e:
        logger.error("Error storing token mapping: %s", type(e).__name__)
    finally:
        conn.close()
        
    return token

def de_identify_text(text: str) -> str:
    if not text:
        return ""
    # Analyze text with Presidio
    results = analyzer.analyze(text=text, language="en")
    
    # We want to replace standard identifiers like PERSON, PHONE_NUMBER, EMAIL_ADDRESS, DATE_TIME, etc.
    # We will replace them with standard placeholders
    anonymized_result = anonymizer.anonymize(
        text=text,
        analyzer_results=results
    )
    return anonymized_result.text

@app.post("/ingest/event")
@limiter.limit("100/minute")
def ingest_event(request: Request, payload: IngestEventPayload, background_tasks: BackgroundTasks, x_auth_token: str = Header(..., alias="X-Auth-Token")):
    if not hmac.compare_digest(x_auth_token, GATEWAY_INGEST_SECRET):
        logger.warning("Unauthorized ingestion attempt")
        raise HTTPException(status_code=401, detail="Unauthorized ingestion request.")
    try:
        raw = payload.raw_payload
        
        # 1. 🔒 De-identification boundary
        # Extract sensitive fields, tokenize them, and ensure they DO NOT cross the boundary
        raw_patient_name = raw.get("patient_name", "Unknown")
        raw_mrn = raw.get("mrn", "Unknown")
        raw_clinician = raw.get("clinician_name", "Unknown")
        
        specimen_token = generate_token(raw.get("specimen_id", "Unknown"), "SPECIMEN")
        patient_token = generate_token(raw_patient_name, "PATIENT")
        mrn_token = generate_token(raw_mrn, "MRN")
        clinician_token = generate_token(raw_clinician, "CLINICIAN")
        
        # De-identify comments using Presidio
        de_identified_comments = de_identify_text(raw.get("comments", ""))
        
        # 2. Build the final de-identified payload
        de_identified_payload = {
            "event_id": payload.event_id,
            "event_type": payload.event_type,
            "occurred_at": payload.occurred_at,
            "received_at": datetime.now(timezone.utc).isoformat(),
            "specimen_token": specimen_token,
            "patient_token": patient_token,
            "mrn_token": mrn_token,
            "clinician_token": clinician_token,
            "test_code": raw.get("test_code", ""),
            "test_type": raw.get("test_type", ""),
            "status": raw.get("status", ""),
            "de_identified_comments": de_identified_comments
        }
        
        # 3. Publish to Redis Stream
        # Send event to "specimen_events_stream"
        redis_client.xadd(
            "specimen_events_stream",
            {"event": json.dumps(de_identified_payload)}
        )
        
        return {
            "status": "success",
            "message": "Event processed and de-identified successfully",
            "specimen_token": specimen_token
        }
        
    except Exception as e:
        logger.error("Ingestion error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal ingestion error")

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "gateway"}

# Internal administrative endpoint to resolve clinician tokens for local alerting
@app.get("/resolve/{token}")
@limiter.limit("30/minute")
def resolve_token(request: Request, token: str, x_auth_token: str = Header(..., alias="X-Auth-Token")):
    if not hmac.compare_digest(x_auth_token, GATEWAY_RESOLVE_SECRET):
        logger.warning("Unauthorized token resolution attempt for token: %s", token[:16])
        raise HTTPException(status_code=401, detail="Unauthorized token resolution request.")
    try:
        resolved = decrypt_value(token)
        return {"token": token, "resolved": resolved}
    except Exception as e:
        raise HTTPException(status_code=404, detail="Token not found")
