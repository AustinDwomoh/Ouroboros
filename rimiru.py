"""
Look am anime lover, I legit have a rimuru wallpaper in my room ok?  Don't judge me.
"""
import asyncpg
import ssl
from settings import PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE

class Rimiru:
    """
    Asynchronous DB access layer for Ouroboros.
    - Async CRUD using asyncpg
    - Async function calls
    - Built-in transaction helper
    - Uses a connection pool internally
    configured via class factory `Rimiru.shion()`

    """

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    # ----------------------------------------------------
    # FACTORY: Create async Rimiru instance
    # ----------------------------------------------------
    @classmethod
    async def shion(cls):
        """
        Factory method to create an async Rimiru instance with a connection pool.
        """
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE

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
        return cls(pool)

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
    async def create(self, table:str, data:dict) -> asyncpg.Record:
        """
        Create a new record in the specified table.
    
        :param table: Name of the table
        :type table: str
        :param data: Data to insert as a dictionary. Keys are column names. values are the corresponding values.
        :type data: dict
        :return: The created record
        :rtype: Record
        """
        cols = ", ".join(data.keys())
        placeholders = ", ".join(f"${i+1}" for i in range(len(data)))
        sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders}) RETURNING *;"

        async with self.pool.acquire() as conn:
            return await conn.fetchrow(sql, *data.values())

    async def read(self, table:str, conditions:dict=None):
        """
        Read records from the specified table with optional conditions.
    
        :param table: Name of the table
        :type table: str
        :param conditions: Conditions as a dictionary. Keys are column names, values are the corresponding values to filter by. Defaults to None.
        :type conditions: dict, optional
        """
        if conditions:
            where = " AND ".join(
                f"{k} = ${i+1}" for i, k in enumerate(conditions.keys())
            )
            sql = f"SELECT * FROM {table} WHERE {where};"
            params = list(conditions.values())
        else:
            sql = f"SELECT * FROM {table};"
            params = []

        async with self.pool.acquire() as conn:
            return await conn.fetch(sql, *params)

    async def update(self, table:str, data:dict, conditions:dict):
        """
        Update records in the specified table based on conditions.
        :param table: Name of the table
        :param data: Data to update as a dictionary. Keys are column names, values are the corresponding values.
        :param conditions: Conditions as a dictionary. Keys are column names, values are the corresponding values to filter by
        """
        set_clause = ", ".join(f"{k} = ${i+1}" for i, k in enumerate(data.keys()))

        where_clause = " AND ".join(
            f"{k} = ${len(data) + i + 1}" for i, k in enumerate(conditions.keys())
        )

        sql = (
            f"UPDATE {table} SET {set_clause} "
            f"WHERE {where_clause} RETURNING *;"
        )

        params = list(data.values()) + list(conditions.values())

        async with self.pool.acquire() as conn:
            return await conn.fetch(sql, *params)

    async def delete(self, table:str, conditions:dict):
        """
        Delete records from the specified table based on conditions.
        
        :param self: Description
        :param table: Name of the table
        :param conditions: Conditions as a dictionary. Keys are column names, values are the corresponding values to filter by.
        """
        where_clause = " AND ".join(
            f"{k} = ${i+1}" for i, k in enumerate(conditions.keys())
        )
        sql = f"DELETE FROM {table} WHERE {where_clause} RETURNING *;"

        params = list(conditions.values())

        async with self.pool.acquire() as conn:
            return await conn.fetch(sql, *params)

    # ----------------------------------------------------
    # ASYNC FUNCTION CALLS
    # ----------------------------------------------------
    async def call_function(self, fn:str, params=None):
        params = params or []
        placeholders = ", ".join(f"${i+1}" for i in range(len(params)))
        sql = f"SELECT * FROM {fn}({placeholders});"

        async with self.pool.acquire() as conn:
            return await conn.fetch(sql, *params)

 
       