import os
from dotenv import load_dotenv

load_dotenv()

# Project is Postgres-only now. Fail fast if credentials are missing.
PGHOST = os.getenv("PGHOST")
PGPORT = int(os.getenv("PGPORT", "5432"))
PGUSER = os.getenv("PGUSER")
PGPASSWORD = os.getenv("PGPASSWORD")
PGDATABASE = os.getenv("PGDATABASE")

try:
    import psycopg2
except Exception:
    raise RuntimeError("psycopg2 is required for Postgres-only mode. Install psycopg2-binary.")


def create_connection(db_path=None):
    """Return a psycopg2 connection to Postgres. Requires PG env vars set.

    db_path argument is ignored in Postgres-only mode (kept for compatibility).
    """
    if not (PGHOST and PGUSER and PGPASSWORD and PGDATABASE):
        raise RuntimeError("Postgres credentials missing. Set PGHOST, PGUSER, PGPASSWORD and PGDATABASE in .env")
    conn = psycopg2.connect(host=PGHOST, port=PGPORT or 5432, user=PGUSER, password=PGPASSWORD, dbname=PGDATABASE)
    return conn
