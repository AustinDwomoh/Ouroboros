"""
Look am anime lover, I legit have a rimuru wallpaper in my room ok?  Don't judge me.
"""
import json
import ssl
import re
import asyncpg

from contextlib import asynccontextmanager
from settings import PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE
from constants import FetchType


class Rimiru:
    """
    Asynchronous DB access layer for Ouroboros.

    Features:
    - Async CRUD using asyncpg
    - Async PostgreSQL function calls
    - Transaction support
    - Connection pooling
    - Singleton instance via Rimiru.shion()
    """

    _instance = None
    _pool: asyncpg.Pool | None = None

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    # ----------------------------------------------------
    # FACTORY
    # ----------------------------------------------------
    @classmethod
    async def shion(cls):
        if cls._instance is not None:
            return cls._instance

        ssl_ctx = ssl.create_default_context()

        pool = await asyncpg.create_pool(
            host=PGHOST,
            port=PGPORT,
            database=PGDATABASE,
            user=PGUSER,
            password=PGPASSWORD,
            ssl=ssl_ctx,
            min_size=2,
            max_size=10,
        )

        cls._pool = pool
        cls._instance = cls(pool)
        return cls._instance

    # ----------------------------------------------------
    # CLOSE POOL
    # ----------------------------------------------------
    @classmethod
    async def close(cls):
        if cls._pool is not None:
            await cls._pool.close()
            cls._pool = None
            cls._instance = None

    # ----------------------------------------------------
    # TRANSACTION
    # ----------------------------------------------------
    @asynccontextmanager
    async def transaction(self):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                yield conn

    # ----------------------------------------------------
    # SELECT
    # ----------------------------------------------------
    async def select(
        self,
        table: str,
        columns: list[str] | None = None,
        filters: dict | None = None,
        raw_where: str | None = None,
        raw_params: list | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:

        cols = ", ".join(columns) if columns else "*"
        sql = f"SELECT {cols} FROM {table}"
        params = []
        where_clauses = []

        for key, value in (filters or {}).items():
            params.append(value)
            where_clauses.append(f"{key} = ${len(params)}")

        if raw_where:
            offset = len(params)

            raw_where = re.sub(
                r"\$(\d+)",
                lambda match: f"${int(match.group(1)) + offset}",
                raw_where,
            )

            where_clauses.append(f"({raw_where})")
            params.extend(raw_params or [])

        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)

        if order_by:
            sql += f" ORDER BY {order_by}"

        if limit is not None:
            if limit < 0:
                raise ValueError("limit cannot be negative")
            sql += f" LIMIT {int(limit)}"

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
            return [dict(row) for row in rows]

    # ----------------------------------------------------
    # SELECT ONE
    # ----------------------------------------------------
    async def selectOne(
        self,
        table: str,
        columns: list[str] | None = None,
        filters: dict | None = None,
        order_by: str | None = None,
    ) -> dict | None:

        rows = await self.select(
            table=table,
            columns=columns,
            filters=filters,
            order_by=order_by,
            limit=1,
        )

        return rows[0] if rows else None

    # ----------------------------------------------------
    # UPSERT
    # ----------------------------------------------------
    async def upsert(
        self,
        table: str,
        data: dict,
        conflict_column: str,
    ) -> dict | None:

        if not data:
            raise ValueError("data cannot be empty")

        if conflict_column not in data:
            raise ValueError(
                f"{conflict_column!r} must exist in data"
            )

        columns = list(data.keys())

        values = [
            json.dumps(value)
            if isinstance(value, (dict, list))
            else value
            for value in data.values()
        ]

        placeholders = ", ".join(
            f"${i}" for i in range(1, len(values) + 1)
        )

        cols = ", ".join(columns)

        update_columns = [
            column
            for column in columns
            if column != conflict_column
        ]

        if update_columns:
            update_clause = ", ".join(
                f"{column} = EXCLUDED.{column}"
                for column in update_columns
            )
            conflict_action = f"DO UPDATE SET {update_clause}"
        else:
            conflict_action = "DO NOTHING"

        sql = f"""
            INSERT INTO {table} ({cols})
            VALUES ({placeholders})
            ON CONFLICT ({conflict_column})
            {conflict_action}
            RETURNING *;
        """

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, *values)
            return dict(row) if row else None

    # ----------------------------------------------------
    # DELETE
    # ----------------------------------------------------
    async def delete(
        self,
        table: str,
        filters: dict,
    ) -> list[dict]:

        if not filters:
            raise ValueError(
                "delete() requires filters to prevent "
                "accidental deletion of every row"
            )

        where_clause = " AND ".join(
            f"{key} = ${i}"
            for i, key in enumerate(filters.keys(), start=1)
        )

        sql = (
            f"DELETE FROM {table} "
            f"WHERE {where_clause} RETURNING *;"
        )

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, *filters.values())
            return [dict(row) for row in rows]

    # ----------------------------------------------------
    # POSTGRESQL FUNCTION CALLS
    # ----------------------------------------------------
    async def call_function(
        self,
        fn: str,
        params=None,
        fetch_type=None,
    ):
        """
        fetch_type:
        - FetchType.FETCH: returns a list of Record objects
        - FetchType.FETCHVAL: returns one scalar value
        - FetchType.FETCHROW: returns one Record object
        """

        params = params or []

        if isinstance(fetch_type, FetchType):
            fetch_type = fetch_type.value

        fetch_type = fetch_type or FetchType.FETCH.value

        placeholders = ", ".join(
            f"${i}" for i in range(1, len(params) + 1)
        )

        sql = f"SELECT * FROM {fn}({placeholders});"

        async with self.pool.acquire() as conn:
            if fetch_type == FetchType.FETCHVAL.value:
                return await conn.fetchval(sql, *params)

            if fetch_type == FetchType.FETCHROW.value:
                return await conn.fetchrow(sql, *params)

            return await conn.fetch(sql, *params)

    # ----------------------------------------------------
    # RESOLVE USER
    # ----------------------------------------------------
    async def resolve_user(
        self,
        discord_id: int,
        username: str,
    ) -> int:

        sql = """
            INSERT INTO users (discord_id, username)
            VALUES ($1, $2)
            ON CONFLICT (discord_id)
            DO UPDATE SET
                username = EXCLUDED.username,
                updated_at = now()
            RETURNING id;
        """

        async with self.pool.acquire() as conn:
            user_id = await conn.fetchval(
                sql,
                discord_id,
                username,
            )

        return user_id

    # ----------------------------------------------------
    # RESOLVE GOOGLE USER
    # ----------------------------------------------------
    async def resolve_google_user(
        self,
        google_sub: str,
        email: str | None,
        username: str,
    ) -> dict:
        """
        Find or create the user for a verified Google identity.
        Only email is refreshed on conflict so a chosen username is kept.
        """

        sql = """
            INSERT INTO users (google_sub, email, username)
            VALUES ($1, $2, $3)
            ON CONFLICT (google_sub) WHERE google_sub IS NOT NULL
            DO UPDATE SET
                email = EXCLUDED.email,
                updated_at = now()
            RETURNING id, username;
        """

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                sql,
                google_sub,
                email,
                username,
            )

        return dict(row)

       