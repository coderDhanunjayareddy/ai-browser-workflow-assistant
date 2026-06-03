import sys
import os
sys.path.insert(0, "c:/Work/AI_Browser_Assist/backend")

from app.core.database import SessionLocal
from app.models.db import WorkflowSession, WorkflowEvent

def main():
    db = SessionLocal()
    try:
        sessions = db.query(WorkflowSession).order_by(WorkflowSession.created_at.desc()).limit(5).all()
        if not sessions:
            print("No sessions found in database!")
            return
            
        for idx, session in enumerate(sessions, 1):
            print(f"=== SESSION {idx} ===")
            print(f"ID: {session.id}")
            print(f"Created At: {session.created_at}")
            print(f"Tab URL: {session.tab_url}")
            print(f"Tab Title: {session.tab_title}")
            print(f"Status: {session.status}")
            
            # Print latest event if any
            event = db.query(WorkflowEvent).filter(WorkflowEvent.session_id == session.id).order_by(WorkflowEvent.created_at.desc()).first()
            if event:
                print(f"Latest Event Type: {event.event_type} | Action: {event.action_type}")
                print(f"Description: {event.description}")
            print("-" * 50)
            
    except Exception as e:
        print("Database query failed:", e)
    finally:
        db.close()

if __name__ == "__main__":
    # Ensure stdout uses utf-8
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    main()
