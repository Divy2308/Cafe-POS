import sqlite3, os, tempfile
DB_PATH = os.path.join(tempfile.gettempdir(), 'pos-cafe', 'pos_runtime.db')
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
queries = [
    'CREATE TABLE IF NOT EXISTS customer (id INTEGER PRIMARY KEY, name VARCHAR(100) DEFAULT "", phone VARCHAR(20), email VARCHAR(120), tenant_id INTEGER REFERENCES tenant(id), created_at DATETIME)',
    'ALTER TABLE "order" ADD COLUMN customer_id INTEGER REFERENCES customer(id)',
    'ALTER TABLE "order" ADD COLUMN customer_phone VARCHAR(20) DEFAULT ""',
    'ALTER TABLE "order" ADD COLUMN subtotal FLOAT DEFAULT 0',
    'ALTER TABLE "order" ADD COLUMN tax_amount FLOAT DEFAULT 0'
]
for q in queries:
    try:
        c.execute(q)
        print("Success:", q)
    except Exception as e:
        print("Skipped:", e)
conn.commit()
conn.close()
