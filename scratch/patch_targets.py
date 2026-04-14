import sqlite3
import os
import tempfile

DB_DIR = os.path.join(tempfile.gettempdir(), 'pos-cafe')
DB_PATH = os.path.join(DB_DIR, 'pos_runtime.db')

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

def add_column(table, col, definition):
    try:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")
        print(f"Added {col} to {table}")
    except sqlite3.OperationalError as e:
        print(f"Skipped {col} on {table}: {e}")

add_column('branch', 'phone', 'VARCHAR(20) DEFAULT ""')
add_column('branch', 'monthly_target', 'FLOAT DEFAULT 0.0')
add_column('user', 'monthly_target', 'FLOAT DEFAULT 0.0')

conn.commit()
conn.close()
print("Patch complete.")
