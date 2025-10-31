from .pg_client import create_connection as _create_connection, USE_PG


def create_connection(db_path: str = "data/game_records.db"):
    return _create_connection(db_path)


def _ph():
    return "%s" if USE_PG else "?"


def update_player_score(guild_id, player_id, player_score, game_type):
    """Record a player's score into the centralized `game_scores` and `leaderboard` tables.

    This replaces the per-guild/per-game tables used by the old SQLite implementation.
    """
    with create_connection() as conn:
        cur = conn.cursor()
        if USE_PG:
            # Upsert into game_scores
            cur.execute(
                "INSERT INTO game_scores (guild_id, game_type, player_id, player_score) VALUES (%s,%s,%s,%s) ON CONFLICT (guild_id, game_type, player_id) DO UPDATE SET player_score = game_scores.player_score + EXCLUDED.player_score",
                (guild_id, game_type, player_id, player_score or 0),
            )
            # Upsert into leaderboard
            cur.execute(
                "INSERT INTO leaderboard (guild_id, player_id, total_score) VALUES (%s,%s,%s) ON CONFLICT (guild_id, player_id) DO UPDATE SET total_score = EXCLUDED.total_score",
                (guild_id, player_id, player_score or 0),
            )
        else:
            # SQLite path: emulate same logic using SELECT/INSERT/UPDATE
            ph = _ph()
            cur.execute(f"SELECT player_score FROM game_scores WHERE guild_id = {ph} AND game_type = {ph} AND player_id = {ph}", (guild_id, game_type, player_id))
            r = cur.fetchone()
            if r:
                new_score = (r[0] or 0) + (player_score or 0)
                cur.execute(f"UPDATE game_scores SET player_score = ? WHERE guild_id = ? AND game_type = ? AND player_id = ?", (new_score, guild_id, game_type, player_id))
            else:
                cur.execute(f"INSERT INTO game_scores (guild_id, game_type, player_id, player_score) VALUES ({ph},{ph},{ph},{ph})", (guild_id, game_type, player_id, player_score or 0))

            cur.execute(f"SELECT total_score FROM leaderboard WHERE guild_id = {ph} AND player_id = {ph}", (guild_id, player_id))
            r2 = cur.fetchone()
            if r2:
                new_total = (r2[0] or 0) + (player_score or 0)
                cur.execute(f"UPDATE leaderboard SET total_score = ? WHERE guild_id = ? AND player_id = ?", (new_total, guild_id, player_id))
            else:
                cur.execute(f"INSERT INTO leaderboard (guild_id, player_id, total_score) VALUES ({ph},{ph},{ph})", (guild_id, player_id, player_score or 0))

        conn.commit()


def save_game_result(guild_id, player_id, player_score, game_type):
    update_player_score(guild_id, player_id, player_score, game_type)


def get_player_scores(guild_id, game_type):
    with create_connection() as conn:
        cur = conn.cursor()
        if USE_PG:
            cur.execute("SELECT player_id, player_score FROM game_scores WHERE guild_id = %s AND game_type = %s ORDER BY player_score DESC", (guild_id, game_type))
            return cur.fetchall()
        else:
            cur.execute("SELECT player_id, player_score FROM game_scores WHERE guild_id = ? AND game_type = ? ORDER BY player_score DESC", (guild_id, game_type))
            return cur.fetchall()


def get_leaderboard(guild_id):
    with create_connection() as conn:
        cur = conn.cursor()
        if USE_PG:
            cur.execute("SELECT player_id, total_score FROM leaderboard WHERE guild_id = %s ORDER BY total_score DESC", (guild_id,))
            return cur.fetchall()
        else:
            cur.execute("SELECT player_id, total_score FROM leaderboard WHERE guild_id = ? ORDER BY total_score DESC", (guild_id,))
            return cur.fetchall()
