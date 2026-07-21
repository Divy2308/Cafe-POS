import os
from app import app, db
from sqlalchemy import text

def migrate_db():
    with app.app_context():
        print("Migrating Floor and Table...")
        try:
            db.session.execute(text("ALTER TABLE floor ADD COLUMN food_court_id INTEGER REFERENCES food_court(id)"))
            db.session.commit()
            print("Added food_court_id to floor")
        except Exception as e:
            db.session.rollback()
            print(f"Skipping floor: {e}")
            
        try:
            db.session.execute(text("ALTER TABLE \"table\" ADD COLUMN food_court_id INTEGER REFERENCES food_court(id)"))
            db.session.commit()
            print("Added food_court_id to table")
        except Exception as e:
            db.session.rollback()
            print(f"Skipping table: {e}")

if __name__ == '__main__':
    migrate_db()
