import os
from dotenv import load_dotenv
load_dotenv()
from sqlalchemy import create_engine, text

def migrate_db():
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        print("DATABASE_URL not set")
        return
    if db_url.startswith('postgres://'):
        db_url = 'postgresql://' + db_url[11:]
        
    engine = create_engine(db_url)
    with engine.begin() as conn:
        print("Migrating Floor and Table...")
        try:
            conn.execute(text("ALTER TABLE floor ADD COLUMN food_court_id INTEGER REFERENCES food_court(id)"))
            print("Added food_court_id to floor")
        except Exception as e:
            print(f"Skipping floor: {e}")
            
        try:
            conn.execute(text("ALTER TABLE \"table\" ADD COLUMN food_court_id INTEGER REFERENCES food_court(id)"))
            print("Added food_court_id to table")
        except Exception as e:
            print(f"Skipping table: {e}")

if __name__ == '__main__':
    migrate_db()
