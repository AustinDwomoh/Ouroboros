import sqlite3

def create_connection():
    conn = sqlite3.connect("data/game_records.db")  # Database file
    return conn

def create_guild_table(guild_id, game_type):
    table_name = f"{game_type}_scores_{guild_id}"
    with create_connection() as conn:
        c = conn.cursor()
        c.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                player_id INTEGER PRIMARY KEY,
                player_score INTEGER
            )
        """
        )
        conn.commit()

def create_leaderboard_table(guild_id):
    table_name = f"leaderboard_{guild_id}"
    with create_connection() as conn:
        c = conn.cursor()
        c.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                player_id INTEGER PRIMARY KEY,
                total_score INTEGER DEFAULT 0
            )
        """
        )
        conn.commit()


def update_score(table_name, player_id, score):
    with create_connection() as conn:
        c = conn.cursor()
        c.execute(
            f"SELECT player_score FROM {table_name} WHERE player_id = :player_id",
            {"player_id": player_id},
        )
        result = c.fetchone()

        if result:
            # Update existing score
            new_score = result[0] + score
            c.execute(
                f"UPDATE {table_name} SET player_score = :new_score WHERE player_id = :player_id",
                {"new_score": new_score, "player_id": player_id},
            )
        else:
            # Insert new player score
            c.execute(
                f"INSERT INTO {table_name} (player_id, player_score) VALUES (:player_id, :player_score)",
                {"player_id": player_id, "player_score": score},
            )


def update_player_score(guild_id, player_id, player_score, game_type):
    table_name = f"{game_type}_scores_{guild_id}" 
    leaderboard_table = f"leaderboard_{guild_id}" 

    create_guild_table(guild_id, game_type)  # Ensure game-specific table exists
    create_leaderboard_table(guild_id)  # Ensure leaderboard table exists
    # Update player score in game-specific table
    update_score(table_name, player_id, player_score)

    # Update total score in the leaderboard
    with create_connection() as conn:
        c = conn.cursor()
        c.execute(
            f"SELECT total_score FROM {leaderboard_table} WHERE player_id = :player_id",
            {"player_id": player_id},
        )
        leaderboard_result = c.fetchone()

        if leaderboard_result:
            # Update existing total score
            new_total_score = leaderboard_result[0] + player_score
            c.execute(
                f"UPDATE {leaderboard_table} SET total_score = :new_total_score WHERE player_id = :player_id",
                {"new_total_score": new_total_score, "player_id": player_id},
            )
        else:
            # Insert new player total score
            c.execute(
                f"INSERT INTO {leaderboard_table} (player_id, total_score) VALUES (:player_id, :total_score)",
                {"player_id": player_id, "total_score": player_score},
            )

        conn.commit()


def save_game_result(guild_id, player_id, player_score, game_type):
    create_guild_table(guild_id, game_type)  # Ensure the table exists
    update_player_score(guild_id, player_id, player_score, game_type)


def get_player_scores(guild_id, game_type):
    """Get player scores for a specific game type."""
    table_name = f"{game_type}_scores_{guild_id}"
    with create_connection() as conn:
        c = conn.cursor()
        c.execute(
            f"SELECT player_id, player_score FROM {table_name} ORDER BY player_score DESC"
        )
        return c.fetchall()


def get_leaderboard(guild_id):
    """Get the overall leaderboard for a guild."""
    leaderboard_table = f"leaderboard_{guild_id}" 
    with create_connection() as conn:
        c = conn.cursor()
        c.execute(
            f"SELECT player_id, total_score FROM {leaderboard_table} ORDER BY total_score DESC"
        )
        return c.fetchall()
