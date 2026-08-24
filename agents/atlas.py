import os
import logging
from sqlalchemy import text
from sqlalchemy.orm import Session
from sentence_transformers import SentenceTransformer
from agents.models import SpecimenState, SpecimenEvent, EpisodicMemory, SemanticRule

logger = logging.getLogger("labmind.atlas")

# Initialize SentenceTransformer locally (all-MiniLM-L6-v2 produces 384 dimensions)
embedding_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

class ContextPacket:
    def __init__(self, working_state: dict, history: list[dict], episodic_recalls: list[dict], semantic_rules: list[dict]):
        self.working_state = working_state
        self.history = history
        self.episodic_recalls = episodic_recalls
        self.semantic_rules = semantic_rules

    def to_dict(self) -> dict:
        return {
            "working_state": self.working_state,
            "history": self.history,
            "episodic_recalls": self.episodic_recalls,
            "semantic_rules": self.semantic_rules
        }

def assemble_context(specimen_token: str, db: Session) -> ContextPacket:
    # 1. working_memory (specimen state + active timeline)
    state = db.query(SpecimenState).filter(SpecimenState.specimen_token == specimen_token).first()
    working_state = {}
    if state:
        working_state = {
            "specimen_token": state.specimen_token,
            "current_status": state.current_status,
            "accessioned_at": state.accessioned_at.isoformat(),
            "expected_signout_at": state.expected_signout_at.isoformat(),
            "tat_risk_level": state.tat_risk_level,
            "last_event_at": state.last_event_at.isoformat()
        }

    # Fetch history of de-identified events
    events = db.query(SpecimenEvent).filter(SpecimenEvent.specimen_token == specimen_token).order_by(SpecimenEvent.occurred_at.asc()).all()
    history = []
    for e in events:
        history.append({
            "event_type": e.event_type,
            "status": e.status,
            "occurred_at": e.occurred_at.isoformat(),
            "comments": e.meta_jsonb.get("comments", "") if e.meta_jsonb else ""
        })

    # 2. episodic_recall (similar past cases using pgvector)
    # Generate query embedding from the comments/history summary
    summary_query = " ".join([h["comments"] for h in history if h.get("comments")]) or "Normal specimen processing"
    query_vector = embedding_model.encode(summary_query).tolist()
    
    # Run pgvector distance search
    episodic_recalls = []
    try:
        # Construct raw sql for pgvector distance query (<-> operator)
        query = text("""
            SELECT id, specimen_token, summary_text, outcome, occurred_at,
                   (embedding <-> :embedding_val::vector) as distance
            FROM episodic_memory
            ORDER BY distance ASC
            LIMIT 3
        """)
        
        # pgvector expects string representation like '[0.1, 0.2, ...]'
        vector_str = "[" + ",".join(map(str, query_vector)) + "]"
        result = db.execute(query, {"embedding_val": vector_str})
        
        for row in result:
            # Check for threshold. If distance is close enough (e.g. cosine distance < 0.6)
            if row[5] < 0.8: # Adjust distance threshold as appropriate
                episodic_recalls.append({
                    "summary_text": row[2],
                    "outcome": row[3],
                    "occurred_at": row[4].isoformat() if row[4] else None,
                    "distance": float(row[5])
                })
    except Exception as e:
        logger.warning("pgvector search failed or database empty: %s", e)
        # Fallback to simple matching if table is empty or error
        pass

    # 3. semantic_rules (SOPs, reference ranges matching test codes)
    test_codes = list(set([e.test_code for e in events]))
    semantic_rules = []
    if test_codes:
        rules = db.query(SemanticRule).filter(
            SemanticRule.key.in_(test_codes),
            SemanticRule.valid_to == None
        ).all()
        for r in rules:
            semantic_rules.append({
                "rule_type": r.rule_type,
                "key": r.key,
                "value": r.value_jsonb
            })

    return ContextPacket(working_state, history, episodic_recalls, semantic_rules)
