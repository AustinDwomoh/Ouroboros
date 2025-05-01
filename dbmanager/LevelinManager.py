import sqlite3
from settings import ErrorHandler

def create_connection(db_path="data/leveling.db"):
    return sqlite3.connect(db_path)


def create_guild_table(guild_id):
    table_name = "levels_" + ErrorHandler.sanitize_table_name(guild_id)
    with create_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            user_id INTEGER NOT NULL,
            xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            PRIMARY KEY (user_id)
        )
        """
        )
        conn.commit()


def get_user_level(guild_id, user_id):
    table_name = "levels_" + ErrorHandler.sanitize_table_name(guild_id)
    create_guild_table(guild_id)
    with create_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT xp, level FROM {table_name} WHERE user_id = ?", (user_id,)
        )
        return cursor.fetchone()


def insert_or_update_user(guild_id, user_id, xp, level):
    table_name = "levels_" + ErrorHandler.sanitize_table_name(guild_id)
    user_id = ErrorHandler.sanitize_table_name(user_id)
    create_guild_table(guild_id)
    with create_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"INSERT INTO {table_name} (user_id, xp, level) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET xp = ?, level = ?",
            (user_id, xp, level, xp, level),
        )
        conn.commit()


def fetch_top_users(guild_id, limit=10):
    table_name = "levels_" + ErrorHandler.sanitize_table_name(guild_id)
    create_guild_table(guild_id)
    with create_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT user_id, level, xp FROM {table_name} ORDER BY level DESC, xp DESC LIMIT ?",
            (limit,),
        )
        return cursor.fetchall()


def get_rank(guild_id, user_id):
    create_guild_table(guild_id)
    user_data = get_user_level(guild_id, user_id)
    if user_data is None:
        return None  # User not found

    xp = user_data[0]
    with create_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM levels_{guild_id} WHERE xp > ?", (xp,))
        rank = cursor.fetchone()[0] + 1  # +1 because rank is 1-indexed
        return rank
