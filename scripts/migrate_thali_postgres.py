import psycopg2
import os
import sys

DATABASE_URL = "postgresql://postgres.kplbnwvfffnahaoaesap:Shreybhut21%40@aws-1-ap-south-1.pooler.supabase.com:5432/postgres"

print("Connecting to PostgreSQL...")
conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = False
cur = conn.cursor()

# Check existing columns
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'product'
""")
cols = [row[0] for row in cur.fetchall()]
print(f"Existing columns: {cols}")

changed = False

if 'is_thali' not in cols:
    cur.execute("ALTER TABLE product ADD COLUMN is_thali BOOLEAN DEFAULT FALSE")
    print("  + Added is_thali column")
    changed = True
else:
    print("  = is_thali already exists")

if 'components_json' not in cols:
    cur.execute("ALTER TABLE product ADD COLUMN components_json TEXT DEFAULT '[]'")
    print("  + Added components_json column")
    changed = True
else:
    print("  = components_json already exists")

if changed:
    conn.commit()
    print("Migration committed successfully!")
else:
    conn.rollback()
    print("No changes needed.")

cur.close()
conn.close()
