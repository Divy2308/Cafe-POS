import os
from app import app, db, FoodCourt
from sqlalchemy import text

def migrate_db():
    with app.app_context():
        print("Migrating FoodCourt table...")
        
        try:
            db.session.execute(text("ALTER TABLE food_court ADD COLUMN is_active BOOLEAN DEFAULT FALSE"))
            print("Added is_active column.")
        except Exception as e:
            print(f"Skipping is_active: column may already exist. ({e})")
            db.session.rollback()
            
        try:
            db.session.execute(text("ALTER TABLE food_court ADD COLUMN approval_status VARCHAR(20) DEFAULT 'pending'"))
            print("Added approval_status column.")
        except Exception as e:
            print(f"Skipping approval_status: column may already exist. ({e})")
            db.session.rollback()
            
        try:
            # Set existing food courts to approved since they were created before approval flow
            db.session.execute(text("UPDATE food_court SET is_active = TRUE, approval_status = 'approved'"))
            print("Updated existing food courts to approved.")
        except Exception as e:
            print(f"Failed to update existing records. ({e})")
            db.session.rollback()
            
        db.session.commit()
        print("Migration complete!")

if __name__ == '__main__':
    migrate_db()
