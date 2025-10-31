import os
from dotenv import load_dotenv

load_dotenv()

try:
    import asyncpg
except Exception:
    raise RuntimeError("asyncpg is required for Postgres-only async DB access. Install asyncpg.")


async def create_connection(db_path: str = None):
    host = os.getenv("PGHOST")
    port = int(os.getenv("PGPORT", "5432"))
    user = os.getenv("PGUSER")
    password = os.getenv("PGPASSWORD")
    database = os.getenv("PGDATABASE")
    if not (host and user and password and database):
        raise RuntimeError("Postgres credentials missing. Set PGHOST, PGUSER, PGPASSWORD and PGDATABASE in .env")
    return await asyncpg.connect(host=host, port=port, user=user, password=password, database=database)
