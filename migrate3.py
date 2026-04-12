import sqlite3, os, tempfile

DB_PATH = os.path.join(tempfile.gettempdir(), 'pos-cafe', 'pos_runtime.db')
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

queries = [
    'ALTER TABLE cafe_settings ADD COLUMN logo_b64 TEXT DEFAULT ""',
    'ALTER TABLE cafe_settings ADD COLUMN address TEXT DEFAULT ""',
    'ALTER TABLE cafe_settings ADD COLUMN phone VARCHAR(20) DEFAULT ""',
    'ALTER TABLE cafe_settings ADD COLUMN email VARCHAR(120) DEFAULT ""',
    'ALTER TABLE cafe_settings ADD COLUMN tax_rate FLOAT DEFAULT 5.0',
    'ALTER TABLE cafe_settings ADD COLUMN open_time VARCHAR(5) DEFAULT "09:00"',
    'ALTER TABLE cafe_settings ADD COLUMN close_time VARCHAR(5) DEFAULT "22:00"'
]

for q in queries:
    try:
        c.execute(q)
        print("Success:", q)
    except Exception as e:
        print("Skipped:", e)

conn.commit()
conn.close()
print("Migration 3 finished.")
