"""Inspect sequences in the connected Postgres and show owners / ACLs.

Usage: run from project root using the same env (.env) as the migrator.
"""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

PGHOST = os.getenv("PGHOST")
PGPORT = int(os.getenv("PGPORT", "5432"))
PGUSER = os.getenv("PGUSER")
PGPASSWORD = os.getenv("PGPASSWORD")
PGDATABASE = os.getenv("PGDATABASE")

if not (PGHOST and PGUSER and PGPASSWORD and PGDATABASE):
    raise SystemExit("Set PGHOST, PGUSER, PGPASSWORD, PGDATABASE in .env to run this script")


def main():
    dsn = dict(host=PGHOST, port=PGPORT, user=PGUSER, password=PGPASSWORD, dbname=PGDATABASE)
    conn = psycopg2.connect(**dsn)
    cur = conn.cursor()

    cur.execute("""
    SELECT c.oid::regclass::text AS seqname,
           pg_get_userbyid(c.relowner) AS owner,
           c.relacl
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind = 'S' AND n.nspname = 'public'
    ORDER BY seqname
    """)

    rows = cur.fetchall()
    print(f"Connected as: {PGUSER}@{PGHOST}/{PGDATABASE}\nFound {len(rows)} public sequences:\n")
    for seqname, owner, relacl in rows:
        # relacl is NULL if default
        has = None
        try:
            cur.execute("SELECT has_sequence_privilege(%s, 'USAGE')", (seqname,))
            has = cur.fetchone()[0]
        except Exception:
            has = None
        print(f"- {seqname}  owner={owner}  relacl={relacl}  has_usage={has}")

    cur.close()
    conn.close()


if __name__ == '__main__':
    main()
