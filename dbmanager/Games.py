from settings import create_async_pg_conn, ErrorHandler, ensure_user
error_handler = ErrorHandler()

# -------------------------------------------------------------
# Update / Save Scores
# -------------------------------------------------------------
async def save_game_result(guild_id: int, player_id: int, player_score: int, game_type: str):
    """
    Record a player's score in centralized `game_scores` and update `leaderboard`.
    If an entry exists, increment it; otherwise insert.
    """
    conn = await create_async_pg_conn()
    await ensure_user(player_id)
    try:
        async with conn.transaction():
            # increment existing game score
            await conn.execute("""
                INSERT INTO game_scores (guild_id, game_type, player_id, player_score)
                VALUES ($1,$2,$3,$4)
                ON CONFLICT (guild_id, game_type, player_id)
                DO UPDATE SET player_score = game_scores.player_score + EXCLUDED.player_score,
                              updated_at = now();
            """, guild_id, game_type, player_id, player_score or 0)

            # increment leaderboard total
            await conn.execute("""
                INSERT INTO leaderboard (guild_id, player_id, total_score)
                VALUES ($1,$2,$3)
                ON CONFLICT (guild_id, player_id)
                DO UPDATE SET total_score = leaderboard.total_score + EXCLUDED.total_score,
                              updated_at = now();
            """, guild_id, player_id, player_score or 0)
    except Exception as e:
        error_handler.handle(e, context="save_game_result")
    finally:
        await conn.close()





# -------------------------------------------------------------
# Fetch Scores / Leaderboards
# -------------------------------------------------------------
async def get_player_scores(guild_id: int, game_type: str):
    """Return sorted list of (player_id, score) for a guild and game type."""
    conn = await create_async_pg_conn()
    try:
        rows = await conn.fetch("""
            SELECT player_id, player_score
            FROM game_scores
            WHERE guild_id = $1 AND game_type = $2
            ORDER BY player_score DESC
        """, guild_id, game_type)
        return [dict(r) for r in rows]
    except Exception as e:
        error_handler.handle(e, context="get_player_scores")
        return []
    finally:
        await conn.close()


async def get_leaderboard(guild_id: int):
    """Return overall leaderboard totals for a guild."""
    conn = await create_async_pg_conn()
    try:
        rows = await conn.fetch("""
            SELECT player_id, total_score
            FROM leaderboard
            WHERE guild_id = $1
            ORDER BY total_score DESC
        """, guild_id)
        return [dict(r) for r in rows]
    except Exception as e:
        error_handler.handle(e, context="get_leaderboard")
        return []
    finally:
        await conn.close()
