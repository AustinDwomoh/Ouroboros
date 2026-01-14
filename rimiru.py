"""
Look am anime lover, I legit have a rimuru wallpaper in my room ok?  Don't judge me.
"""
import json
import asyncpg
import ssl

from settings import PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE
from constants import FetchType
class Rimiru:
    """
    Asynchronous DB access layer for Ouroboros.
    - Async CRUD using asyncpg
    - Async function calls
    - Built-in transaction helper
    - Uses a connection pool internally
    configured via class factory `Rimiru.shion()`

    """
    _instance = None          
    _pool: asyncpg.Pool = None 
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    # ----------------------------------------------------
    # FACTORY: Create async Rimiru instance
    # ----------------------------------------------------
    @classmethod
    async def shion(cls):
        if cls._instance is not None:
            return cls._instance

        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE

        cls._pool = await asyncpg.create_pool(
            host=PGHOST,
            port=PGPORT,
            database=PGDATABASE,
            user=PGUSER,
            password=PGPASSWORD,
            ssl=ssl_ctx,
            min_size=2,
            max_size=10,
        )

        cls._instance = cls(cls._pool)
        return cls._instance

    # ----------------------------------------------------
    # TRANSACTION HELPER
    # ----------------------------------------------------
    async def transaction(self):
        """
        Usage:
            async with db.transaction():
                await db.async_create(...)
                await db.async_update(...)
        """
        return self.pool.transaction()

    # ----------------------------------------------------
    #  CRUD
    # ----------------------------------------------------
    async def select(self, table: str, columns: list = None, filters: dict = None, 
                raw_where: str = None, raw_params: list = None,
                order_by: str = None, limit: int = None):
        """
        Select records with optional filtering
        
        :param table: Table name
        :param columns: List of columns to select (default: all)
        :param filters: Dictionary of column=value filters
        :param raw_where: Raw WHERE clause (use with raw_params for safety)
        :param raw_params: Parameters for raw_where clause
        :param order_by: Column to order by
        :param limit: Maximum number of records to return
        """
        cols = ", ".join(columns) if columns else "*"
        sql = f"SELECT {cols} FROM {table}"
        params = []
        param_count = 1
        
        if filters:
            where_clauses = []
            for key, value in filters.items():
                where_clauses.append(f"{key} = ${param_count}")
                params.append(value)
                param_count += 1
            sql += f" WHERE {' AND '.join(where_clauses)}"
            
        if raw_where:
            if filters:
                sql += f" AND ({raw_where})"
            else:
                sql += f" WHERE {raw_where}"
            if raw_params:
                params.extend(raw_params)
        
        if order_by:
            sql += f" ORDER BY {order_by}"
        
        if limit:
            sql += f" LIMIT {limit}"
        
        sql += ";"
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
            return [dict(r) for r in rows]

    async def selectOne(self, table: str, columns: list = None, filters: dict = None, order_by: str = None):
        """
        Select a single record with optional filtering
        
        :param table: Table name
        :param columns: List of columns to select (default: all)
        :param filters: Dictionary of column=value filters
        :param order_by: Column to order by (e.g., "created_at DESC")
        """
        row = await self.select(table, columns, filters, order_by, limit=1)
        return row[0] if row else None
   
    # -------------------------
    # UPSERT (INSERT or UPDATE)
    # -------------------------
    async def upsert(self, table: str, data: dict, conflict_column: str ):
        """Insert or update a record based on conflict column
            To use this method, provide the following
            its important you know the unique constraint of the table you are upserting to.  The conflict_column parameter should be set to that unique constraint column.
            
                parameters:
                    :param table: Table name
                    :param data: Dictionary of column-value pairs
                    :param conflict_column: Column name to check for conflicts
            """
        try:
            columns = list(data.keys())
            values = [
                json.dumps(v) if isinstance(v, (dict, list)) else v
                for v in data.values()
            ]

            placeholders = ", ".join(f"${i+1}" for i in range(len(values)))
            cols = ", ".join(columns)
            update_cols = ", ".join(f"{k} = EXCLUDED.{k}" for k in columns if k != conflict_column)

            sql = f"""
                INSERT INTO {table} ({cols}) 
                VALUES ({placeholders})
                ON CONFLICT ({conflict_column}) 
                DO UPDATE SET {update_cols}
                RETURNING *;
            """

            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(sql, *values) 
                return dict(row) if row else None
        except Exception as e:
            print(f"Error during upsert into {table}: {e}")
            raise
        # -------------------------
        # DELETE
    # -------------------------
    async def delete(self, table: str, filters: dict):
        """Delete records matching filters"""
        where_clause = " AND ".join(f"{k} = ${i+1}" for i, k in enumerate(filters.keys()))
        sql = f"DELETE FROM {table} WHERE {where_clause} RETURNING *;"
        params = list(filters.values())

        async with self.pool.acquire() as conn:
            return await conn.fetch(sql, *params)
    # ----------------------------------------------------
    # ASYNC FUNCTION CALLS
    # ----------------------------------------------------
    

    
    async def call_function(self, fn: str, params=None, fetch_type=None):
        #TODO: test if the dict lamba works here
        """
        fetch_type can be:
        - FetchType.FETCH: returns list of Record objects
        - FetchType.FETCHVAL: returns single scalar value
        - FetchType.FETCHROW: returns single Record object
        """
        params = params or []
        fetch_type = fetch_type or FetchType.FETCH.value  # Default to FETCH
        
        placeholders = ", ".join(f"${i+1}" for i in range(len(params)))
        sql = f"SELECT * FROM {fn}({placeholders});"

        async with self.pool.acquire() as conn:
            if fetch_type == FetchType.FETCHVAL.value:
                return await conn.fetchval(sql, *params)
            elif fetch_type == FetchType.FETCHROW.value:
                return await conn.fetchrow(sql, *params)
            else:  # FetchType.FETCH
                return await conn.fetch(sql, *params)


 
       