from settings import create_async_pg_conn, ErrorHandler, ensure_user
from movies.api_calls import get_media_details

error_handler = ErrorHandler()

# ============================================================
# Add or Update MOVIE
# ============================================================
async def add_or_update_movie(user_id: int, title: str, date=None):
    """Insert or update a movie watch record for a user."""
    await ensure_user(user_id)
    conn = await create_async_pg_conn()
    try:
        # 1. Look up or insert movie
        row = await conn.fetchrow("SELECT id FROM movies WHERE title ILIKE $1", title)
        if row:
            movie_id = row["id"]
        else:
            api_data = {}
            try:
                api_data = await get_media_details("movie", title)
            except Exception:
                pass

            movie_id = await conn.fetchval("""
                INSERT INTO movies (title, media_id, overview, genres, release_date, poster_url, status, homepage)
                VALUES ($1, COALESCE($2, md5(random()::text)), $3, $4, $5, $6, $7, $8)
                RETURNING id
            """,
            title,
            api_data.get("id"),
            api_data.get("overview"),
            api_data.get("genres"),
            api_data.get("release_date"),
            api_data.get("poster_url"),
            api_data.get("status", "released"),
            api_data.get("homepage"))

        # 2. Upsert user_movies_watched
        await conn.execute("""
            INSERT INTO user_movies_watched (user_id, movie_id, watched_date)
            VALUES ($1, $2, COALESCE($3, now()))
            ON CONFLICT (user_id, movie_id)
            DO UPDATE SET watched_date = EXCLUDED.watched_date
        """, user_id, movie_id, date)

        # 3. Maintain registry
        await conn.execute("""
            INSERT INTO user_media (user_id, media_type, media_id)
            VALUES ($1, 'movie', $2)
            ON CONFLICT (user_id, media_type, media_id) DO NOTHING
        """, user_id, movie_id)

    except Exception as e:
        error_handler.handle(e, context=f"add_or_update_movie({title})")
    finally:
        await conn.close()

# ============================================================
# Add or Update SERIES
# ============================================================

async def add_or_update_series(user_id: int, title: str, season=None, episode=None, date=None):
    """Insert or update user progress for a series."""
    await ensure_user(user_id)
    conn = await create_async_pg_conn()
    try:
        # Lookup or insert series
        row = await conn.fetchrow("SELECT id FROM series WHERE title ILIKE $1", title)
        if row:
            series_id = row["id"]
        else:
            api_data = {}
            try:
                api_data = await get_media_details("tv", title)
            except Exception:
                pass

            series_id = await conn.fetchval("""
                INSERT INTO series (title, media_id, overview, genres, status,
                                    release_date, next_episode_date, poster_url, homepage)
                VALUES ($1, COALESCE($2, md5(random()::text)), $3, $4, $5, $6, $7, $8, $9)
                RETURNING id
            """,
            title,
            api_data.get("id"),
            api_data.get("overview"),
            api_data.get("genres"),
            api_data.get("status", "watching"),
            api_data.get("first_air_date"),
            api_data.get("next_episode_date"),
            api_data.get("poster_url"),
            api_data.get("homepage"))

        # Upsert user_series_progress
        await conn.execute("""
            INSERT INTO user_series_progress (user_id, series_id, season, episode, status, last_updated)
            VALUES ($1, $2, $3, $4, 'watching', COALESCE($5, now()))
            ON CONFLICT (user_id, series_id)
            DO UPDATE SET season = EXCLUDED.season,
                          episode = EXCLUDED.episode,
                          status = EXCLUDED.status,
                          last_updated = EXCLUDED.last_updated
        """, user_id, series_id, season, episode, date)

        # Maintain registry
        await conn.execute("""
            INSERT INTO user_media (user_id, media_type, media_id)
            VALUES ($1, 'series', $2)
            ON CONFLICT (user_id, media_type, media_id) DO NOTHING
        """, user_id, series_id)

    except Exception as e:
        error_handler.handle(e, context=f"add_or_update_series({title})")
    finally:
        await conn.close()


# ============================================================
# Fetch User Titles
# ============================================================
async def fetch_user_titles(user_id: int):
    """Fetch all titles tied to a user from movies, series, or watchlist."""
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
                SELECT CASE
                    WHEN uw.media_type='movie' THEN m.title
                    ELSE s.title
                END AS title
                FROM user_watchlist uw
                LEFT JOIN movies m ON (uw.media_type='movie' AND uw.media_id=m.id)
                LEFT JOIN series s ON (uw.media_type='series' AND uw.media_id=s.id)
                WHERE uw.user_id=$1
            ) q
            ORDER BY title ASC
        """, user_id)
        return [r['title'] for r in rows]
    finally:
        await conn.close()

# ============================================================
# Fetch Watchlist with API Enrichment
# ============================================================
async def get_watch_list(user_id: int, media_type: str):
    """Return enriched watchlist entries with DB + API data."""
    conn = await create_async_pg_conn()
    try:
        rows = await conn.fetch("""
            SELECT uw.*, 
                   CASE 
                       WHEN uw.media_type='movie' THEN m.title
                       ELSE s.title 
                   END AS title
            FROM user_watchlist uw
            LEFT JOIN movies m ON (uw.media_type='movie' AND uw.media_id=m.id)
            LEFT JOIN series s ON (uw.media_type='series' AND uw.media_id=s.id)
            WHERE uw.user_id=$1 AND uw.media_type=$2
        """, user_id, media_type.lower())

        results = []
        for r in rows:
            db_data = dict(r)
            title = db_data.get("title")
            try:
                api_data = await get_media_details(media_type, title)
            except Exception:
                api_data = None
            results.append({"db_data": db_data, "api_data": api_data})
        return results
    finally:
        await conn.close()


# ============================================================
# Delete All User Media Data
# ============================================================
async def delete_user_database(user_id: int):
    """Delete all of a user's records across movies, series, and watchlist."""
    conn = await create_async_pg_conn()
    try:
        await conn.execute("DELETE FROM user_movies_watched WHERE user_id=$1", user_id)
        await conn.execute("DELETE FROM user_series_progress WHERE user_id=$1", user_id)
        await conn.execute("DELETE FROM user_watchlist WHERE user_id=$1", user_id)
        await conn.execute("DELETE FROM user_media WHERE user_id=$1", user_id)
    finally:
        await conn.close()
    return f"🗑 All media records for user {user_id} deleted."
