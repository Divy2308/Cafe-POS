import argparse
import os
import sqlite3
from pathlib import Path

os.environ['SKIP_APP_INIT'] = '1'

from app import app, db  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser(
        description='Migrate POS Cafe data from SQLite to PostgreSQL.'
    )
    parser.add_argument(
        '--sqlite-path',
        default='instance/pos.db',
        help='Path to the source SQLite database file.',
    )
    parser.add_argument(
        '--keep-existing',
        action='store_true',
        help='Do not recreate or clear PostgreSQL tables before importing.',
    )
    return parser.parse_args()


def quote_identifier(name):
    return '"' + name.replace('"', '""') + '"'


def sqlite_table_exists(conn, table_name):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def reset_postgres_sequence(pg_conn, table):
    primary_keys = list(table.primary_key.columns)
    if len(primary_keys) != 1:
        return

    pk_column = primary_keys[0]
    if pk_column.name != 'id':
        return

    table_name = quote_identifier(table.name)
    sql = f"""
    SELECT setval(
        pg_get_serial_sequence('{table_name}', 'id'),
        COALESCE((SELECT MAX(id) FROM {table_name}), 1),
        (SELECT COUNT(*) > 0 FROM {table_name})
    )
    """
    pg_conn.exec_driver_sql(sql)


def main():
    args = parse_args()
    sqlite_path = Path(args.sqlite_path).resolve()

    if not sqlite_path.exists():
        raise SystemExit(f'SQLite database not found: {sqlite_path}')

    with app.app_context():
        if db.engine.dialect.name != 'postgresql':
            raise SystemExit(
                'DATABASE_URL must point to PostgreSQL before running this migration.'
            )

        if args.keep_existing:
            db.create_all()
        else:
            db.drop_all()
            db.create_all()

        sqlite_conn = sqlite3.connect(str(sqlite_path))
        sqlite_conn.row_factory = sqlite3.Row

        try:
            tables = list(db.metadata.sorted_tables)

            with db.engine.begin() as pg_conn:
                for table in tables:
                    if not sqlite_table_exists(sqlite_conn, table.name):
                        continue

                    rows = sqlite_conn.execute(
                        f'SELECT * FROM {quote_identifier(table.name)}'
                    ).fetchall()
                    if not rows:
                        continue

                    pg_conn.execute(table.insert(), [dict(row) for row in rows])

                for table in tables:
                    reset_postgres_sequence(pg_conn, table)
        finally:
            sqlite_conn.close()

    print(f'Migration complete from {sqlite_path}')


if __name__ == '__main__':
    main()
