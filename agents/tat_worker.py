import os
import json
import logging
from typing import Optional
from agents.llm_factory import get_llm
from agents.atlas import ContextPacket
from agents.base import assert_no_phi, ActionProposed, ActionExecutor
from agents.models import SpecimenState

logger = logging.getLogger("labmind.tat_worker")

class TATMonitorWorker:
    def __init__(self):
        self.model = get_llm(role="worker", temperature=0.0)

    def analyze(self, context: ContextPacket, db: Session) -> Optional[ActionProposed]:
        # Formulate prompt from de-identified context
        comments_summary = "\n".join([
            f"- Event {h['event_type']} ({h['status']}) occurred at {h['occurred_at']}. Comments: {h['comments']}"
            for h in context.history
        ])
        
        # Pull threshold values from rules if available
        rules_text = ""
        for rule in context.semantic_rules:
            rules_text += f"- Rule type {rule['rule_type']}: {json.dumps(rule['value'])}\n"

        system_prompt = f"""You are the LabMind TAT Monitor Worker Agent.
Analyze the following de-identified specimen state and timeline to evaluate Turnaround Time (TAT) risk.

Specimen Token: {context.working_state.get('specimen_token')}
Current Status: {context.working_state.get('current_status')}
Accessioned At: {context.working_state.get('accessioned_at')}
Expected Sign-out: {context.working_state.get('expected_signout_at')}
TAT Risk Rules:
{rules_text or 'No specific rules configured.'}

Task:
1. Determine if this specimen is likely to exceed (or has already exceeded) its expected sign-out time.
2. Output a JSON block only, with fields:
   - "risk_level": "green" | "yellow" | "red"
   - "confidence": float between 0.0 and 1.0
   - "reasoning": human-readable string explaining the risk assessment
   - "propose_alert": true | false
"""

        # Call LLM or use fallback
        if self.model:
            try:
                from langchain_core.messages import SystemMessage, HumanMessage
                from agents.base import secure_invoke
                messages = [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=f"Timeline of Events:\n{comments_summary}")
                ]
                response = secure_invoke(self.model, messages, db, "TATMonitorWorker")
                content = response.content.strip()
                # Parse JSON block
                # Basic JSON cleaning in case LLM wraps it in markdown codeblocks
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                result = json.loads(content.strip())
            except Exception as e:
                logger.warning("LLM invocation failed, using fallback rules: %s", e)
                result = self._fallback_rule_analysis(context)
        else:
            # Fallback mock/rule analysis for local development without Anthropic API Key
            result = self._fallback_rule_analysis(context)

        # Save risk level state to specimen_state table
        state = db.query(SpecimenState).filter(
            SpecimenState.specimen_token == context.working_state.get("specimen_token")
        ).first()
        if state:
            state.tat_risk_level = result["risk_level"]
            db.commit()

        if result.get("propose_alert"):
            return ActionProposed(
                action_type="TAT_DELAY_ALERT",
                specimen_token=context.working_state.get("specimen_token"),
                payload={
                    "risk_level": result["risk_level"],
                    "expected_signout": context.working_state.get("expected_signout_at")
                },
                confidence=result["confidence"],
                reasoning=result["reasoning"]
            )
        return None

    def _fallback_rule_analysis(self, context: ContextPacket) -> dict:
        # Simple heuristic fallback
        # If specimen is stuck in ACCESSIONED or PROCESSING for a prolonged period, increase risk.
        from datetime import datetime, timezone
        
        expected_str = context.working_state.get("expected_signout_at")
        if not expected_str:
            return {"risk_level": "green", "confidence": 1.0, "reasoning": "No expected sign-out time", "propose_alert": False}
            
        expected_dt = datetime.fromisoformat(expected_str)
        now = datetime.now(timezone.utc)
        
        time_left = (expected_dt - now).total_seconds() / 60.0
        
        status = context.working_state.get("current_status", "")
        
        if time_left < 0 and status != "SIGNED_OUT":
            return {
                "risk_level": "red",
                "confidence": 0.95,
                "reasoning": f"Specimen Turnaround Time has breached expected target by {abs(time_left):.1f} minutes. Status is '{status}'.",
                "propose_alert": True
            }
        elif time_left < 15 and status != "SIGNED_OUT": # less than 15 mins left
            return {
                "risk_level": "yellow",
                "confidence": 0.85,
                "reasoning": f"Turnaround Time target is in 15 minutes. Current status is '{status}'.",
                "propose_alert": True
            }
        
        return {
            "risk_level": "green",
            "confidence": 0.90,
            "reasoning": "Processing is proceeding within nominal expectations.",
            "propose_alert": False
        }
