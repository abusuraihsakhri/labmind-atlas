import os
import json
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from agents.database import SessionLocal
from agents.models import Action, EpisodicMemory

logger = logging.getLogger("labmind.learning_loop")

def run_learning_loop():
    logger.info("Starting ATLAS Learning Loop...")
    db: Session = SessionLocal()
    try:
        # Calculate stats for the last 7 days
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        
        # 1. Harvest recent actions
        actions = db.query(Action).filter(Action.proposed_at >= week_ago).all()
        
        if not actions:
            logger.info("No actions found in the last 7 days.")
            return
            
        total_proposed = len(actions)
        approved = len([a for a in actions if a.status == "approved"])
        dismissed = len([a for a in actions if a.status == "dismissed"])
        
        precision = approved / total_proposed if total_proposed > 0 else 0.0
        
        logger.info("ATLAS Weekly Stats:")
        logger.info("- Total Actions Proposed: %d", total_proposed)
        logger.info("- Approved by Operator: %d", approved)
        logger.info("- Dismissed by Operator: %d", dismissed)
        logger.info("- Agent Precision: %.2f%%", precision * 100)
        
        # 2. Group by Agent
        from collections import defaultdict
        agent_stats = defaultdict(lambda: {"approved": 0, "total": 0})
        for a in actions:
            agent_stats[a.agent_name]["total"] += 1
            if a.status == "approved":
                agent_stats[a.agent_name]["approved"] += 1
                
        logger.info("Breakdown by Agent:")
        for agent, stats in agent_stats.items():
            agent_prec = stats["approved"] / stats["total"] if stats["total"] > 0 else 0
            logger.info("  * %s: %d proposed, %.2f%% precision", agent, stats['total'], agent_prec * 100)
            
        # Write to a weekly report file (stub for actual reporting email/dashboard)
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "period_start": week_ago.isoformat(),
            "total_proposed": total_proposed,
            "approved": approved,
            "dismissed": dismissed,
            "overall_precision": precision,
            "agent_breakdown": dict(agent_stats)
        }
        
        with open("atlas_weekly_report.json", "w") as f:
            json.dump(report, f, indent=2)
            
        logger.info("Learning loop complete. Weekly report saved to atlas_weekly_report.json")
        
    finally:
        db.close()

if __name__ == "__main__":
    run_learning_loop()
