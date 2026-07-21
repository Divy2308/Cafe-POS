import sqlite3, os

db = r'C:\Users\Shrey\AppData\Local\Temp\qbite\pos_runtime.db'
print('DB path:', db)
print('DB exists:', os.path.exists(db))
if os.path.exists(db):
    print('DB size:', os.path.getsize(db), 'bytes')

conn = sqlite3.connect(db)
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tenant'")
found = cur.fetchone()
print('tenant table found:', found)

if found:
    cur.execute("PRAGMA table_info(tenant)")
    cols = [row[1] for row in cur.fetchall()]
    print('Columns:', cols)
    if 'max_staff' not in cols:
        cur.execute("ALTER TABLE tenant ADD COLUMN max_staff INTEGER DEFAULT 0")
        conn.commit()
        print("SUCCESS: max_staff column added!")
    else:
        print("max_staff already exists - no action needed")
else:
    print("tenant table not found in this DB")

conn.close()
