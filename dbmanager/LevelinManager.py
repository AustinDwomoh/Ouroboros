from settings import  ErrorHandler
from rimiru import Rimiru
from constants import FetchType
error_handler = ErrorHandler()

# -------------------------------------------------------------
# BASIC LEVEL OPERATIONS
# -------------------------------------------------------------
async def get_user_level(guild_id: int, user_id: int)-> tuple[int, int] | None:
    """Return (xp, level) for a user in a guild from the centralized `levels` table."""
    conn = await Rimiru.shion() 
    try:
        row = await conn.select(table="levels", columns=["xp", "level"], filters={"guild_id": guild_id, "user_id": user_id})
        print(row)
        if row:
            return row.get('xp'), row.get('level')
    except Exception as e:
        error_handler.handle(e, context="get_user_level")
        return None

async def insert_or_update_user(guild_id: int, user_id: int, xp: int, level: int) -> None:
    """Insert or update XP and level for a user in a guild."""
    conn = await Rimiru.shion()
    try:
        await conn.upsert(table="levels", data={"guild_id": guild_id, "user_id": user_id, "xp": xp, "level": level}, conflict_column="user_id,guild_id")
    except Exception as e:
        error_handler.handle(e, context="insert_or_update_user")


# -------------------------------------------------------------
# LEADERBOARD / RANKING
# -------------------------------------------------------------
async def fetch_top_users(guild_id: int, limit: int = 10) -> list[tuple[int, int, int]]:
    """Return top N users in a guild by level and XP."""
    conn = await Rimiru.shion()
    try:
        rows = await conn.select(
            table="levels",
            columns=["user_id", "level", "xp"],
            filters={"guild_id": guild_id},
            order_by=f"level DESC, xp DESC",
            limit=limit
        )
        return rows
    except Exception as e:
        error_handler.handle(e, context="fetch_top_users")
        return []
    
async def get_rank(guild_id: int, user_id: int) -> int | None:
    """Return a user's rank in the guild (1 = highest XP)."""
    conn = await Rimiru.shion()
    try:
        rank = await conn.call_function("get_user_lvl_rank",[guild_id, user_id],fetch_type=FetchType.FETCHVAL.value)
        print(rank)
        return rank
    except Exception as e:
        error_handler.handle(e, context="get_rank")
        return None