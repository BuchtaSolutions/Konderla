from database import engine, Base
from sqlalchemy import text
import models

def migrate():
    # Ensure tables exist (ChatSession)
    print("Creating tables if not exist...")
    Base.metadata.create_all(bind=engine)
    
    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        try:
            print("Attempting to add session_id column to chat_history...")
            conn.execute(text("ALTER TABLE chat_history ADD COLUMN session_id INTEGER REFERENCES chat_sessions(id)"))
            print("Success: Column session_id added.")
        except Exception as e:
            print(f"Info: {e}")

if __name__ == "__main__":
    migrate()
