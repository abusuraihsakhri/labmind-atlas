import logging
from sqlalchemy.orm import Session
from agents.atlas import assemble_context
from agents.tat_worker import TATMonitorWorker
from agents.critical_worker import CriticalValueRouterWorker
from agents.base import ActionExecutor, ActionProposed

logger = logging.getLogger("labmind.workflow_manager")

class WorkflowManagerAgent:
    def __init__(self):
        self.tat_worker = TATMonitorWorker()
        self.critical_worker = CriticalValueRouterWorker()

    def process_specimen_update(
        self, 
        specimen_token: str, 
        db: Session, 
        clinician_token: str,
        trust_stage: str = "SUGGEST"
    ) -> list[dict]:
        # 1. Assemble context using ATLAS memory
        context = assemble_context(specimen_token, db)
        if not context.working_state:
            logger.warning("Context empty for token %s. Aborting.", specimen_token)
            return []

        results = []

        # 2. Delegate to TAT Monitor Worker
        tat_proposal = self.tat_worker.analyze(context, db)
        if tat_proposal:
            res = ActionExecutor.execute(
                db=db,
                proposal=tat_proposal,
                agent_name="TAT_Monitor",
                trust_stage=trust_stage
            )
            results.append(res)

        # 3. Delegate to Critical Value Router Worker
        critical_proposal = self.critical_worker.analyze(context, db, clinician_token)
        if critical_proposal:
            res = ActionExecutor.execute(
                db=db,
                proposal=critical_proposal,
                agent_name="Critical_Value_Router",
                trust_stage=trust_stage
            )
            results.append(res)

        return results
