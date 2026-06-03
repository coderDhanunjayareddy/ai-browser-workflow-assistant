import sys
sys.path.insert(0, "c:/Work/AI_Browser_Assist/backend")

from app.core.database import SessionLocal
from app.models.db import WorkflowSession, WorkflowEvent

def main():
    db = SessionLocal()
    try:
        # Get the latest session
        session = db.query(WorkflowSession).order_by(WorkflowSession.created_at.desc()).first()
        if not session:
            print("No sessions found in database!")
            return
            
        print("=== LATEST SESSION ===")
        print(f"ID: {session.id}")
        print(f"Created At: {session.created_at}")
        print(f"Tab URL: {session.tab_url}")
        print(f"Tab Title: {session.tab_title}")
        print(f"Status: {session.status}")
        
        # Get events for this session
        events = db.query(WorkflowEvent).filter(WorkflowEvent.session_id == session.id).order_by(WorkflowEvent.created_at.asc()).all()
        print(f"\n=== EVENTS FOR SESSION ({len(events)}) ===")
        for i, e in enumerate(events, 1):
            print(f"{i}. Event Type: {e.event_type} | Created At: {e.created_at}")
            print(f"   Action Type: {e.action_type} | Description: {e.description}")
            if e.execution_result:
                print(f"   Execution Result: {e.execution_result}")
            if e.ai_reasoning:
                print(f"   AI Reasoning: {e.ai_reasoning[:150]}...")
            print("-" * 40)
            
    except Exception as e:
        print("Database query failed:", e)
    finally:
        db.close()

if __name__ == "__main__":
    main()
