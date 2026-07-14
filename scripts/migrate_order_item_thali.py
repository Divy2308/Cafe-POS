import sqlite3, os

db = r'C:\Users\Shrey\AppData\Local\Temp\pos-cafe\pos_runtime.db'
if not os.path.exists(db):
    db = r'C:\Users\Shrey\OneDrive\Desktop\pos-cafe\instance\pos.db'

print('DB path:', db)
if os.path.exists(db):
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    
    cur.execute("PRAGMA table_info(order_item)")
    cols = [row[1] for row in cur.fetchall()]
    
    if 'is_thali' not in cols:
        cur.execute("ALTER TABLE order_item ADD COLUMN is_thali BOOLEAN DEFAULT 0")
        print("Added is_thali column to order_item")
    if 'components_json' not in cols:
        cur.execute("ALTER TABLE order_item ADD COLUMN components_json TEXT DEFAULT '[]'")
        print("Added components_json column to order_item")
        
    conn.commit()
    conn.close()
    print("Migration complete.")
else:
    print("DB not found.")
