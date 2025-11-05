from settings import create_async_pg_conn, ErrorHandler, ensure_user

error_handler = ErrorHandler()

# -------------------------------------------------------------
# BASIC LEVEL OPERATIONS
# -------------------------------------------------------------
async def get_user_level(guild_id: int, user_id: int):
    """Return (xp, level) for a user in a guild from the centralized `levels` table."""
    conn = await create_async_pg_conn()
    await ensure_user(user_id) #not strictly necessary here but good to have
    try:
        row = await conn.fetchrow(
            "SELECT xp, level FROM levels WHERE guild_id=$1 AND user_id=$2",
            guild_id, user_id
        )
        return dict(row) if row else None
    except Exception as e:
        error_handler.handle(e, context="get_user_level")
        return None
    finally:
        await conn.close()


async def insert_or_update_user(guild_id: int, user_id: int, xp: int, level: int):
    """Insert or update XP and level for a user in a guild."""
    conn = await create_async_pg_conn()
    await ensure_user(user_id)
    try:
        await conn.execute("""
            INSERT INTO levels (guild_id, user_id, xp, level)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id, user_id)
            DO UPDATE SET xp = EXCLUDED.xp, level = EXCLUDED.level,
                          updated_at = now();
        """, guild_id, user_id, xp or 0, level or 1)
    except Exception as e:
        error_handler.handle(e, context="insert_or_update_user")
    finally:
        await conn.close()


# -------------------------------------------------------------
# LEADERBOARD / RANKING
# -------------------------------------------------------------
async def fetch_top_users(guild_id: int, limit: int = 10):
    """Return top N users in a guild by level and XP."""
    conn = await create_async_pg_conn()

    try:
        rows = await conn.fetch("""
            SELECT user_id, level, xp
            FROM levels
            WHERE guild_id = $1
            ORDER BY level DESC, xp DESC
            LIMIT $2
        """, guild_id, limit)
        return [dict(r) for r in rows]
    except Exception as e:
        error_handler.handle(e, context="fetch_top_users")
        return []
    finally:
        await conn.close()


async def get_rank(guild_id: int, user_id: int):
    """Return a user's rank in the guild (1 = highest XP)."""
    conn = await create_async_pg_conn()
    try:
        await ensure_user(user_id)
        xp_row = await conn.fetchval(
            "SELECT xp FROM levels WHERE guild_id=$1 AND user_id=$2",
            guild_id, user_id
        )
        if xp_row is None:
            return None
        rank = await conn.fetchval(
            "SELECT COUNT(*) + 1 FROM levels WHERE guild_id=$1 AND xp > $2",
            guild_id, xp_row
        )
        return rank
    except Exception as e:
        error_handler.handle(e, context="get_rank")
        return None
    finally:
        await conn.close()
