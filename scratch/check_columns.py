from app import app, db
import sqlite3

def check_column(table, column):
    try:
        with db.engine.connect() as conn:
            rows = conn.exec_driver_sql(f'PRAGMA table_info("{table}")').fetchall()
            cols = {row[1] for row in rows}
            return column in cols
    except Exception as e:
        return f"Error: {e}"

tables_to_check = [
    ('order', 'tenant_id'),
    ('order_item', 'tenant_id'),
    ('reservation', 'tenant_id'),
    ('inventory_item', 'tenant_id'),
    ('branch', 'tenant_id'),
    ('user', 'tenant_id'),
    ('category', 'tenant_id'),
    ('product', 'tenant_id'),
    ('floor', 'tenant_id'),
    ('table', 'tenant_id'),
]

with app.app_context():
    for t, c in tables_to_check:
        res = check_column(t, c)
        print(f"Table {t}, Column {c}: {res}")
