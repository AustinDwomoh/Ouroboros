from .pg_client import create_connection as _create_connection, USE_PG


def create_connection(db_path: str = "data/leveling.db"):
    return _create_connection(db_path)


def _ph():
    """Return parameter placeholder depending on DB driver."""
    return "%s" if USE_PG else "?"


def get_user_level(guild_id, user_id):
    """Return (xp, level) for a user in a guild from the centralized `levels` table."""
    with create_connection() as conn:
        cursor = conn.cursor()
        placeholder = _ph()
        sql = f"SELECT xp, level FROM levels WHERE guild_id = {placeholder} AND user_id = {placeholder}"
        cursor.execute(sql, (guild_id, user_id))
        return cursor.fetchone()


def insert_or_update_user(guild_id, user_id, xp, level):
    """Insert or update a user's xp/level in the centralized `levels` table."""
    with create_connection() as conn:
        cursor = conn.cursor()
        placeholder = _ph()
        if USE_PG:
            sql = (
                "INSERT INTO levels (guild_id, user_id, xp, level) VALUES (%s,%s,%s,%s) "
                "ON CONFLICT (guild_id, user_id) DO UPDATE SET xp = EXCLUDED.xp, level = EXCLUDED.level"
            )
            cursor.execute(sql, (guild_id, user_id, xp or 0, level or 1))
        else:
            # SQLite upsert; keep syntax compatible for SQLite 3.24+
            sql = f"INSERT INTO levels (guild_id, user_id, xp, level) VALUES ({placeholder},{placeholder},{placeholder},{placeholder}) ON CONFLICT (guild_id, user_id) DO UPDATE SET xp = excluded.xp, level = excluded.level"
            cursor.execute(sql, (guild_id, user_id, xp or 0, level or 1))
        conn.commit()


def fetch_top_users(guild_id, limit=10):
    with create_connection() as conn:
        cursor = conn.cursor()
        placeholder = _ph()
        sql = f"SELECT user_id, level, xp FROM levels WHERE guild_id = {placeholder} ORDER BY level DESC, xp DESC LIMIT {limit}"
        cursor.execute(sql, (guild_id,))
        return cursor.fetchall()


def get_rank(guild_id, user_id):
    user_data = get_user_level(guild_id, user_id)
    if user_data is None:
        return None
    xp = user_data[0]
    with create_connection() as conn:
        cursor = conn.cursor()
        placeholder = _ph()
        sql = f"SELECT COUNT(*) FROM levels WHERE guild_id = {placeholder} AND xp > {placeholder}"
        cursor.execute(sql, (guild_id, xp))
        rank = cursor.fetchone()[0] + 1
        return rank
