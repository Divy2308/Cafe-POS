import sqlite3
import os

db_path = 'C:/Users/Shrey/AppData/Local/Temp/qbite/pos_runtime.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

def add_col(table, col, ctype):
    try:
        cursor.execute(f'ALTER TABLE "{table}" ADD COLUMN {col} {ctype}')
        print(f"Added {col} to {table}")
    except Exception as e:
        print(f"Failed to add {col} to {table}: {e}")

add_col('tenant', 'food_court_id', 'INTEGER')
add_col('user', 'food_court_id', 'INTEGER')
add_col('table', 'food_court_id', 'INTEGER')
add_col('order', 'food_court_id', 'INTEGER')

conn.commit()
conn.close()
