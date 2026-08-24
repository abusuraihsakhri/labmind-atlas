import time
import os
import random
import uuid
import logging
import requests
from datetime import datetime, timezone

logger = logging.getLogger("labmind.simulator")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S%z",
)

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")
GATEWAY_INGEST_SECRET = os.getenv("GATEWAY_INGEST_SECRET", "")

# Test types and expected turnaround times (TAT) in minutes
TEST_TEMPLATES = {
    "HISTOPATH": {
        "test_code": "HISTO-01",
        "name": "Surgical Pathology Biopsy",
        "nominal_tat": 2880, # 48 hours
        "panic_chance": 0.05,
    },
    "CLIN_CHEM": {
        "test_code": "CHEM-20",
        "name": "Comprehensive Metabolic Panel",
        "nominal_tat": 60, # 1 hour
        "panic_chance": 0.15,
    },
    "HEMA": {
        "test_code": "HEMA-10",
        "name": "Complete Blood Count with Diff",
        "nominal_tat": 45, # 45 mins
        "panic_chance": 0.10,
    }
}

# Synthetic PHI names/info to inject and prove Presidio strips them
PATIENT_NAMES = [
    "John Doe", "Jane Smith", "Alice Johnson", "Robert Miller", 
    "Emily Davis", "David Wilson", "Sarah Martinez", "James Taylor"
]

CLINICIAN_NAMES = [
    "Dr. Gregory House", "Dr. Meredith Grey", "Dr. Stephen Strange", 
    "Dr. Leonard McCoy", "Dr. John Watson"
]

def generate_specimen():
    test_type = random.choice(list(TEST_TEMPLATES.keys()))
    template = TEST_TEMPLATES[test_type]
    specimen_id = str(uuid.uuid4())
    
    # Generate identifiable patient info that MUST be tokenized/stripped
    patient_name = random.choice(PATIENT_NAMES)
    mrn = f"MRN-{random.randint(100000, 999999)}"
    dob = f"{random.randint(1950, 2015)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
    clinician_name = random.choice(CLINICIAN_NAMES)
    
    is_panic = random.random() < template["panic_chance"]
    
    # Create details with PHI in free text to test the tokenizer
    free_text_comment = (
        f"Specimen received from {clinician_name} for patient {patient_name} (DOB: {dob}, MRN: {mrn}). "
        f"Please run urgent panel. Phone contact: +971-50-{random.randint(100, 999)}-{random.randint(1000, 9999)}."
    )
    
    if is_panic:
        if test_type == "CLIN_CHEM":
            free_text_comment += " CRITICAL VALUE: Potassium level measured at 6.8 mmol/L (Panic high)."
        elif test_type == "HEMA":
            free_text_comment += " CRITICAL VALUE: Platelet count critical at 15,000 /uL."
        else:
            free_text_comment += " CRITICAL VALUE: Urgent frozen section showing malignant neoplasm."

    return {
        "specimen_id": specimen_id,
        "test_type": test_type,
        "test_code": template["test_code"],
        "patient_name": patient_name,
        "mrn": mrn,
        "dob": dob,
        "clinician_name": clinician_name,
        "free_text_comment": free_text_comment,
        "nominal_tat": template["nominal_tat"],
        "is_panic": is_panic
    }

def send_event(event_type: str, specimen: dict, status: str):
    payload = {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "raw_payload": {
            "specimen_id": specimen["specimen_id"],
            "test_code": specimen["test_code"],
            "test_type": specimen["test_type"],
            "status": status,
            "patient_name": specimen["patient_name"],
            "mrn": specimen["mrn"],
            "dob": specimen["dob"],
            "clinician_name": specimen["clinician_name"],
            "comments": specimen["free_text_comment"]
        }
    }
    
    try:
        url = f"{GATEWAY_URL}/ingest/event"
        headers = {"X-Auth-Token": GATEWAY_INGEST_SECRET}
        res = requests.post(url, json=payload, headers=headers, timeout=5)
        logger.info("Sent event %s for %s (Status: %s). Code: %d", event_type, specimen['specimen_id'], status, res.status_code)
    except Exception as e:
        logger.error("Error sending event to gateway at %s: %s", url, e)

def send_event_backfill(event_type: str, specimen: dict, status: str, override_time: datetime):
    payload = {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "occurred_at": override_time.isoformat(),
        # Raw data containing PHI. Gateway must intercept and de-identify.
        "raw_payload": {
            "specimen_id": specimen["specimen_id"],
            "test_code": specimen["test_code"],
            "test_type": specimen["test_type"],
            "status": status,
            "patient_name": specimen["patient_name"],
            "mrn": specimen["mrn"],
            "dob": specimen["dob"],
            "clinician_name": specimen["clinician_name"],
            "comments": specimen["free_text_comment"]
        }
    }
    
    try:
        url = f"{GATEWAY_URL}/ingest/event"
        headers = {"X-Auth-Token": GATEWAY_INGEST_SECRET}
        res = requests.post(url, json=payload, headers=headers, timeout=5)
        # minimal logging for speed
    except Exception as e:
        logger.error("Error sending event to gateway at %s: %s", url, e)

def run_backfill(days=14):
    logger.info("Running backfill for past %d days...", days)
    from datetime import timedelta
    start_time = datetime.now(timezone.utc) - timedelta(days=days)
    current_time = start_time
    
    # Generate ~20 specimens per day
    total_specimens = days * 20
    
    for i in range(total_specimens):
        specimen = generate_specimen()
        
        # Advance time by some random hours
        current_time += timedelta(hours=random.uniform(0.5, 1.5))
        
        # Order and Accessioned
        send_event_backfill("ORDER_PLACED", specimen, "ORDERED", current_time)
        current_time += timedelta(minutes=random.randint(10, 60))
        send_event_backfill("SPECIMEN_RECEIVED", specimen, "ACCESSIONED", current_time)
        
        # Processing
        current_time += timedelta(minutes=random.randint(30, 120))
        send_event_backfill("PROCESSING_STARTED", specimen, "PROCESSING", current_time)
        
        # Sign out
        # if nominal TAT is 60 mins, maybe it takes 50-70 mins.
        tat_mins = specimen["nominal_tat"]
        actual_tat = random.randint(int(tat_mins * 0.8), int(tat_mins * 1.5))
        current_time += timedelta(minutes=actual_tat)
        send_event_backfill("REPORT_SIGNED_OUT", specimen, "SIGNED_OUT", current_time)
        
        if i % 10 == 0:
            logger.info("Backfilled %d/%d specimens...", i, total_specimens)
            
    logger.info("Backfill complete. Seeded %d historical specimens.", total_specimens)

def main():
    import sys
    if "--backfill" in sys.argv:
        run_backfill(14)
        return

    logger.info("LIS Simulator running. Target Gateway: %s", GATEWAY_URL)
    active_specimens = []

    while True:
        # 1. Accession a new specimen (15% chance per cycle)
        if random.random() < 0.25 or len(active_specimens) == 0:
            specimen = generate_specimen()
            # Send ORDERED event
            send_event("ORDER_PLACED", specimen, "ORDERED")
            time.sleep(1)
            # Send ACCESSIONED event
            send_event("SPECIMEN_RECEIVED", specimen, "ACCESSIONED")
            active_specimens.append({
                "data": specimen,
                "step": 0, # 0 = accessioned, 1 = processing, 2 = sign-out
                "last_update": time.time()
            })

        # 2. Progress existing specimens
        current_time = time.time()
        for active in list(active_specimens):
            specimen = active["data"]
            elapsed = current_time - active["last_update"]
            
            # Progress to PROCESSING after short delay
            if active["step"] == 0 and elapsed > random.randint(3, 8):
                send_event("PROCESSING_STARTED", specimen, "PROCESSING")
                active["step"] = 1
                active["last_update"] = current_time
            
            # Progress to SIGNED_OUT after short delay
            elif active["step"] == 1 and elapsed > random.randint(5, 15):
                # Simulate occasional TAT breach by delaying event reporting (not real-time delay, but reporting latency)
                is_tat_breach = random.random() < 0.10
                status = "SIGNED_OUT"
                send_event("REPORT_SIGNED_OUT", specimen, status)
                active_specimens.remove(active)

        time.sleep(3)

if __name__ == "__main__":
    main()
