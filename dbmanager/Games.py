from typing import Optional
from constants import FetchType, gameType
from settings import  ErrorHandler
from rimiru import Rimiru
error_handler = ErrorHandler()
# ============================================================================ #
#                                     NOTES                                    #
# ============================================================================ #
# This module provides asynchronous database operations for managing game scores
# and leaderboards using the Rimiru DB access layer.
#the functions include saving game results, fetching player scores, leaderboards, and player ranks.
# It uses stored procedures/functions in the database for efficient data handling
# All functions handle exceptions and log errors using ErrorHandler.
#Tested and working as intended.
# ============================================================================ #

# -------------------------------------------------------------
# Update / Save Scores
# -------------------------------------------------------------

async def save_game_result(guild_id: int, player_id: int, player_score: int, game_type: gameType):
    """
    Record a player's score in centralized `game_scores` and update `leaderboard`.
    If an entry exists, increment it; otherwise insert.
    """
    conn = await Rimiru.shion()
    try:
        game_type = game_type.value
        await conn.call_function("save_game_result", params=[guild_id, player_id, game_type, player_score or 0])
    except Exception as e:
        error_handler.handle(e, context="save_game_result")
   

# -------------------------------------------------------------
# Fetch Scores / Leaderboards
# -------------------------------------------------------------
async def get_player_scores(guild_id: int, game_type: gameType = None,user_id: int = None):
    """
    Returns player scores for a specific game type in a guild.
    if game_type is none it returns all the game types for the user in that guild
    
    :param guild_id: The guild ID
    :type guild_id: int
    :param game_type:  The game type to filter scores. If None, returns all game types for the user in that guild.
    :type game_type: str
    """
    conn = await Rimiru.shion()
    try:
        rows = []
        if game_type:
            rows = await conn.call_function("get_player_game_scores", params=[guild_id, game_type.value,user_id])
        else:
            rows = await conn.call_function("get_player_scores", params=[user_id,guild_id])
        return [dict(r) for r in rows]
    except Exception as e:
        error_handler.handle(e, context="get_player_scores")
        return []


async def get_leaderboard(guild_id: int,game_type: gameType = None):
    """
    Returns the overall leaderboard for a guild. If game type is specified, returns leaderboard for that game type.
    
    :param guild_id: The guild ID
    :type guild_id: int
    :param game_type: The game type to filter leaderboard. If None, returns overall leaderboard for the guild.
    :type game_type: str
    """
    conn = await Rimiru.shion()
    try:
        rows = []
        if game_type:
            rows = await conn.call_function("get_game_leaderboard", params=[guild_id, game_type.value])
        else:
            rows = await conn.call_function("get_leaderboard", params=[guild_id])
        return [dict(r) for r in rows]
    except Exception as e:
        error_handler.handle(e, context="get_leaderboard")
        return []
   


async def get_rank(guild_id: int, player_id: int,game_type: gameType = None) -> Optional[int]:
    """
    Returns the rank of a player in the overall leaderboard for a guild.
    
    :param guild_id: The guild ID
    :type guild_id: int
    :param player_id: The player ID
    :type player_id: int
    :return: The rank of the player or None if not found
    :rtype: Optional[int]
    """
    conn = await Rimiru.shion()
    try:
        fetch = FetchType.FETCHVAL.value
        if game_type:
            rank = await conn.call_function("get_player_rank", params=[guild_id, player_id, game_type.value], fetch_type=fetch)
        else:
            rank = await conn.call_function("get_player_rank", params=[guild_id, player_id], fetch_type=fetch)
        return rank if rank else None
    except Exception as e:
        error_handler.handle(e, context="get_rank")
        return None