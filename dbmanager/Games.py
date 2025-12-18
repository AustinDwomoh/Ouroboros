from settings import  ErrorHandler
from rimiru import Rimiru
error_handler = ErrorHandler()

# -------------------------------------------------------------
# Update / Save Scores
# -------------------------------------------------------------

async def save_game_result(guild_id: int, player_id: int, player_score: int, game_type: str):
    """
    Record a player's score in centralized `game_scores` and update `leaderboard`.
    If an entry exists, increment it; otherwise insert.
    """
    conn = await Rimiru.shion()
    try:
        
            # increment existing game score
        await conn.call_function("save_game_result", [guild_id, player_id, game_type, player_score or 0])
        await conn.call_function("increment_leaderboard", [guild_id, player_id, player_score or 0])
            
    except Exception as e:
        error_handler.handle(e, context="save_game_result")
   





# -------------------------------------------------------------
# Fetch Scores / Leaderboards
# -------------------------------------------------------------
async def get_player_scores(guild_id: int, game_type: str):
    """Return sorted list of (player_id, score) for a guild and game type."""
    conn = await Rimiru.shion()
    try:
        rows = await conn.call_function("get_player_scores", [guild_id, game_type])
        return [dict(r) for r in rows]
    except Exception as e:
        error_handler.handle(e, context="get_player_scores")
        return []
    finally:
        await conn.close()


async def get_leaderboard(guild_id: int):
    """Return overall leaderboard totals for a guild."""
    conn = await Rimiru.shion()
    try:
        rows = await conn.call_function("get_leaderboard", [guild_id])
        return [dict(r) for r in rows]
    except Exception as e:
        error_handler.handle(e, context="get_leaderboard")
        return []
   
