
from settings import create_async_pg_conn, ErrorHandler, ensure_user

error_handler = ErrorHandler()

async def add_or_update_movie(user_id: int, title: str, date=None):
    """Insert/update user movie record."""
    await ensure_user(user_id)
    conn = await create_async_pg_conn()
    try:
        movie_id = await conn.fetchval("SELECT id FROM movies WHERE title ILIKE $1", title)
        if not movie_id:
            movie_id = await conn.fetchval(
                "INSERT INTO movies (title, release_date) VALUES ($1, $2) RETURNING id", title, date
            )

        await conn.execute("""
            INSERT INTO user_movies_watched (user_id, movie_id, watched_date)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id, movie_id)
            DO UPDATE SET watched_date = EXCLUDED.watched_date
        """, user_id, movie_id, date)
    except Exception as e:
        error_handler.handle(e, context=f"add_or_update_movie({title})")
    finally:
        await conn.close()

async def add_or_update_series(user_id, title, season=None, episode=None, date=None):
    """Add or update a user's series progress in Postgres normalized tables."""
    await update_user_ids(user_id)
    first_value = await get_media_details("tv", title)
    next_release_date = first_value.get("next_episode_date") if first_value else None
    status = first_value.get("status", "watching") if first_value else "watching"
    conn = await create_connection()
    try:
        row = await conn.fetchrow("SELECT id FROM series WHERE title ILIKE $1", title)
        if row:
            series_id = row["id"]
        else:
            series_id = await conn.fetchval("INSERT INTO series (title, status, next_episode_date) VALUES ($1,$2,$3) RETURNING id", title, status, next_release_date)

        await conn.execute(
            "INSERT INTO user_series_progress (user_id, series_id, season, episode, status, last_updated) VALUES ($1,$2,$3,$4,$5,$6) ON CONFLICT (user_id, series_id) DO UPDATE SET season = EXCLUDED.season, episode = EXCLUDED.episode, status = EXCLUDED.status, last_updated = EXCLUDED.last_updated",
            int(user_id), series_id, season, episode, status, date,
        )
    finally:
        await conn.close()


async def fetch_user_titles(user_id: int):
    """Return all titles linked to a user."""
    conn = await create_async_pg_conn()
    try:
        rows = await conn.fetch("""
            SELECT DISTINCT title FROM (
                SELECT m.title FROM user_movies_watched umw
                JOIN movies m ON umw.movie_id = m.id
                WHERE umw.user_id=$1
                UNION
                SELECT s.title FROM user_series_progress usp
                JOIN series s ON usp.series_id = s.id
                WHERE usp.user_id=$1
                UNION
                SELECT title FROM user_watchlist WHERE user_id=$1
            ) t ORDER BY title ASC
        """, user_id)
        return [r['title'] for r in rows]
    finally:
        await conn.close()

async def get_watch_list(user_id, media_type):
    conn = await create_async_pg_conn()
    try:
        results = []
        if media_type.lower() == "movie":
            rows = await conn.fetch("SELECT uw.*, m.title FROM user_watchlist uw JOIN movies m ON uw.media_id = m.id WHERE uw.user_id = $1 AND uw.media_type = 'movie'", int(user_id))
        else:
            rows = await conn.fetch("SELECT uw.*, s.title FROM user_watchlist uw JOIN series s ON uw.media_id = s.id WHERE uw.user_id = $1 AND uw.media_type = 'series'", int(user_id))

        for r in rows:
            db_data = dict(r)
            title = db_data.get("title")
            api_data = None
            try:
                api_data = await get_media_details("tv" if media_type.lower() == "series" else "movie", title)
            except Exception:
                api_data = None
            results.append({"db_data": db_data, "api_data": api_data})
        return results
    finally:
        await conn.close()


#thinking of taking it out
async def delete_user_database(user_id):
    """Deletes the user's movie and series records from the centralized Postgres schema."""
    conn = await create_async_pg_conn()
    try:
        await conn.execute("DELETE FROM user_movies_watched WHERE user_id = $1", int(user_id))
        await conn.execute("DELETE FROM user_series_progress WHERE user_id = $1", int(user_id))
        await conn.execute("DELETE FROM user_watchlist WHERE user_id = $1", int(user_id))
        await conn.execute("DELETE FROM user_media WHERE user_id = $1", int(user_id))
    finally:
        await conn.close()
    return "Your movie and series record has been deleted."
