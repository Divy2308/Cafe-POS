import os
import tempfile
import sqlite3
from app import db, app

with app.app_context():
    db.create_all()

DB_PATH = os.path.join(tempfile.gettempdir(), 'pos-cafe', 'pos_runtime.db')
print('DB:', DB_PATH)
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

queries = [
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
