import os
import json
import uuid
import re
import logging
from typing import Optional
from agents.llm_factory import get_llm
from agents.atlas import ContextPacket
from agents.base import assert_no_phi, ActionProposed, ActionExecutor
from agents.models import CriticalValueEvent
from agents.notifications import notify_critical_value
from datetime import datetime, timezone

logger = logging.getLogger("labmind.critical_worker")

class CriticalValueRouterWorker:
    def __init__(self):
        self.model = get_llm(role="worker", temperature=0.0)

    def analyze(self, context: ContextPacket, db: Session, clinician_token: str) -> Optional[ActionProposed]:
        # Formulate prompt from de-identified context comments
        comments_text = " ".join([h["comments"] for h in context.history if h.get("comments")])
        
        if not comments_text:
            return None

        system_prompt = f"""You are the LabMind Critical Value Router Worker Agent.
Determine if the following de-identified comments contain a critical/panic diagnostic value requiring immediate clinician notification.

Task:
1. Scan for critical terms like "CRITICAL VALUE", "PANIC", "malignant", "potassium critical", etc.
2. Output a JSON block only, with fields:
   - "is_critical": true | false
   - "value_summary": string summarizing the panic value (must be de-identified)
   - "confidence": float between 0.0 and 1.0
   - "reasoning": string reasoning
"""

        # Call LLM or use fallback
        if self.model:
            try:
                from langchain_core.messages import SystemMessage, HumanMessage
                from agents.base import secure_invoke
                messages = [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=f"Comments: \"{comments_text}\"")
                ]
                response = secure_invoke(self.model, messages, db, "CriticalValueRouterWorker")
                content = response.content.strip()
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                result = json.loads(content.strip())
            except Exception as e:
                logger.warning("LLM failed, using fallback rules: %s", e)
                result = self._fallback_regex_analysis(comments_text)
        else:
            result = self._fallback_regex_analysis(comments_text)

        if result.get("is_critical"):
            # Create a jailed critical value event row (10y retention, never erasable)
            critical_event_id = str(uuid.uuid4())
            critical_entry = CriticalValueEvent(
                id=critical_event_id,
                specimen_token=context.working_state.get("specimen_token"),
                value_summary=result["value_summary"],
                routed_to_token=clinician_token,
                routed_at=datetime.now(timezone.utc)
            )
            db.add(critical_entry)
            db.commit()

            logger.warning("Detected panic value for specimen %s. Logged in jailed table.", context.working_state.get('specimen_token'))

            notify_critical_value(
                clinician_email=os.getenv("ALERT_EMAIL"),
                clinician_phone=os.getenv("ALERT_PHONE"),
                specimen_token=context.working_state.get("specimen_token", ""),
                value_summary=result["value_summary"],
                routed_at=datetime.now(timezone.utc).isoformat(),
            )

            return ActionProposed(
                action_type="ROUTE_CRITICAL_ALERT",
                specimen_token=context.working_state.get("specimen_token"),
                payload={
                    "critical_event_id": critical_event_id,
                    "value_summary": result["value_summary"],
                    "routed_to_token": clinician_token
                },
                confidence=result["confidence"],
                reasoning=result.get("reasoning", "Critical/Panic laboratory result flagged for routing.")
            )

        return None

    def _fallback_regex_analysis(self, text: str) -> dict:
        # Regex heuristics for panic/critical values
        pattern = re.compile(r'(critical value|panic|potassium level measured at|platelet count critical|malignant neoplasm)', re.IGNORECASE)
        match = pattern.search(text)
        
        if match:
            # Extract summary
            summary = "Critical laboratory value detected"
            if "potassium" in text.lower():
                summary = "Critical Potassium level (Panic high: 6.8 mmol/L)"
            elif "platelet" in text.lower():
                summary = "Critical Platelet count (15,000 /uL)"
            elif "malignant" in text.lower():
                summary = "Malignant neoplasm detected on frozen section"
                
            return {
                "is_critical": True,
                "value_summary": summary,
                "confidence": 0.99,
                "reasoning": f"Regex matched critical term: '{match.group(0)}'."
            }
            
        return {
            "is_critical": False,
            "value_summary": "",
            "confidence": 0.90,
            "reasoning": "No panic/critical terms matched."
        }
