import json
import re
import logging
from typing import Optional
from sqlalchemy.orm import Session
from agents.llm_factory import get_llm
from agents.atlas import ContextPacket
from agents.base import ActionProposed

logger = logging.getLogger("labmind.critical_worker")

class CriticalValueRouterWorker:
    def __init__(self):
        self.model = get_llm(role="worker", temperature=0.0)

    def analyze(self, context: ContextPacket, db: Session, clinician_token: str) -> Optional[ActionProposed]:
        # Formulate prompt from de-identified context comments
        comments_text = " ".join([h["comments"] for h in context.history if h.get("comments")])

        if not comments_text:
            return None

        system_prompt = """You are the LabMind Critical Value Router Worker Agent.
Identify free-text signals that may warrant human review. These signals are NOT validated critical values and must never initiate clinician notification.

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
            # Free-text/LLM findings are unverified. Never persist a routed alert,
            # make an external call, or imply clinical threshold validation here.
            logger.warning(
                "Unverified critical-like free-text signal for specimen %s; "
                "internal review only (external routing disabled).",
                context.working_state.get("specimen_token"),
            )
            return ActionProposed(
                action_type="REVIEW_UNVERIFIED_CRITICAL_SIGNAL",
                specimen_token=context.working_state.get("specimen_token"),
                payload={
                    "value_summary": result["value_summary"],
                    "clinician_token": clinician_token,
                    "validation_status": "unverified_free_text",
                    "dispatch_allowed": False,
                },
                confidence=result["confidence"],
                reasoning=result.get(
                    "reasoning",
                    "Unverified free-text signal for human review; not a validated critical value.",
                ),
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
                summary = "Potentially critical potassium result flagged for review (value not verified)"
            elif "platelet" in text.lower():
                summary = "Potentially critical platelet count flagged for review (value not verified)"
            elif "malignant" in text.lower():
                summary = "Potential malignancy-related comment flagged for review (not a diagnosis)"

            return {
                "is_critical": True,
                "value_summary": summary,
                "confidence": 0.50,
                "reasoning": f"Regex matched critical term: '{match.group(0)}'."
            }

        return {
            "is_critical": False,
            "value_summary": "",
            "confidence": 0.90,
            "reasoning": "No panic/critical terms matched."
        }
