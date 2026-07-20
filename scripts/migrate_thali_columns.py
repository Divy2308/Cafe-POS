import sqlite3, os

paths = [
    os.path.join(os.environ.get('TEMP', ''), 'qbite', 'pos_runtime.db'),
    r'c:\Users\Shrey\OneDrive\Desktop\pos-cafe\instance\pos.db'
]

for db_path in paths:
    if not os.path.exists(db_path):
        print(f'Skipping (not found): {db_path}')
        continue
    print(f'Migrating: {db_path}')
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute('PRAGMA table_info(product)')
    cols = [row[1] for row in cur.fetchall()]
    print(f'Existing columns: {cols}')

    if 'is_thali' not in cols:
        cur.execute('ALTER TABLE product ADD COLUMN is_thali BOOLEAN DEFAULT 0')
        print('  + Added is_thali column')
    else:
        print('  = is_thali already exists')

    if 'components_json' not in cols:
        cur.execute("ALTER TABLE product ADD COLUMN components_json TEXT DEFAULT '[]'")
        print('  + Added components_json column')
    else:
        print('  = components_json already exists')

    conn.commit()
    conn.close()
    print(f'Done: {db_path}\n')
