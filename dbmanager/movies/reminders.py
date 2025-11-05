from datetime import datetime, timedelta, timezone
from settings import ErrorHandler, create_async_pg_conn
from movies.api_calls import get_media_details

error_handler = ErrorHandler()


# --------------------------------------------------------------------------
# 1. CHECK UPCOMING DATES
# --------------------------------------------------------------------------
async def check_upcoming_dates():
    """
    Fetch shows or movies releasing in the next 7 days for all users.
    Combines user_series_progress and user_watchlist via joined movie/series tables.
    """
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    next_week = (now + timedelta(days=7)).date().isoformat()
    reminders = []
    conn = await create_async_pg_conn()

    try:
        # Upcoming episodes for tracked series
        rows = await conn.fetch("""
            SELECT usp.user_id, s.title, usp.status, s.next_episode_date
            FROM user_series_progress usp
            JOIN series s ON usp.series_id = s.id
            WHERE s.next_episode_date IS NOT NULL
              AND s.next_episode_date BETWEEN $1 AND $2
            ORDER BY s.next_episode_date ASC
        """, today, next_week)

        for r in rows:
            reminders.append({
                "user_id": r["user_id"],
                "title": r["title"],
                "status": r["status"],
                "next_episode_date": r["next_episode_date"],
                "media_type": "series"
            })

        # Upcoming movie releases in user watchlists
        wl_movies = await conn.fetch("""
            SELECT uw.user_id, m.title, m.release_date
            FROM user_watchlist uw
            JOIN movies m ON uw.media_type = 'movie' AND uw.media_id = m.id
            WHERE m.release_date IS NOT NULL
              AND m.release_date BETWEEN $1 AND $2
        """, today, next_week)

        for r in wl_movies:
            reminders.append({
                "user_id": r["user_id"],
                "title": r["title"],
                "release_date": r["release_date"],
                "media_type": "movie"
            })

    except Exception as e:
        error_handler.handle(e, context="check_upcoming_dates")
    finally:
        await conn.close()

    return reminders


# --------------------------------------------------------------------------
# 2. CHECK SERIES COMPLETION STATUS
# --------------------------------------------------------------------------
async def check_all_unfinished():
    """
    End-of-month job:
    Return all users with unfinished shows for reminder batching.
    Uses only internal DB data.
    """
    conn = await create_async_pg_conn()
    try:
        rows = await conn.fetch("""
            SELECT usp.user_id, s.title, usp.status
            FROM user_series_progress usp
            JOIN series s ON usp.series_id = s.id
            WHERE usp.status != 'completed'
              OR (s.status = 'ended' AND usp.status != 'completed')
            ORDER BY usp.user_id, s.title
        """)

        reminders = {}
        for r in rows:
            uid = r["user_id"]
            if uid not in reminders:
                reminders[uid] = []
            reminders[uid].append({
                "title": r["title"],
                "status": r["status"]
            })

        return reminders
    except Exception as e:
        error_handler.handle(e, context="check_all_unfinished")
        return {}
    finally:
        await conn.close()

async def check_user_unfinished(user_id: int):
    """
    Return list of series a specific user has not completed.
    Uses internal DB data only — no TMDB calls.
    """
    conn = await create_async_pg_conn()
    try:
        rows = await conn.fetch("""
            SELECT s.title, usp.status, usp.season, usp.episode,
                   s.next_episode_date, s.status AS show_status
            FROM user_series_progress usp
            JOIN series s ON usp.series_id = s.id
            WHERE usp.user_id = $1
              AND (usp.status != 'completed'
                   OR (s.status = 'ended' AND usp.status != 'completed'))
            ORDER BY s.title ASC
        """, user_id)

        return [
            {
                "title": r["title"],
                "user_status": r["status"],
                "show_status": r["show_status"],
                "season": r["season"],
                "episode": r["episode"],
                "next_episode_date": r["next_episode_date"],
            }
            for r in rows
        ]
    except Exception as e:
        error_handler.handle(e, context=f"check_user_unfinished({user_id})")
        return []
    finally:
        await conn.close()
# --------------------------------------------------------------------------
# 3. REFRESH SERIES DATES FROM TMDB
# --------------------------------------------------------------------------

from settings import create_async_pg_conn, ErrorHandler
from movies.api_calls import get_media_details

error_handler = ErrorHandler()

async def refresh_tmdb_dates():
    """
    Refresh TMDB-linked data for all movies and series in the global catalog.
    - Updates release_date and status for unreleased movies.
    - Updates next_episode_date, status, and last_air_date for ongoing series.
    - Skips entries missing a valid title or media_id.
    """
    conn = await create_async_pg_conn()
    updated = {"movies": [], "series": []}

    try:
        # ------------------------------------------------------------
        # 1️⃣ Update MOVIES (e.g. upcoming releases)
        # ------------------------------------------------------------
        movie_rows = await conn.fetch("""
            SELECT id, title, media_id, release_date, status
            FROM movies
            WHERE status IS DISTINCT FROM 'released'
               OR release_date >= now()::date
        """)

        for r in movie_rows:
            title = r["title"]
            media = await get_media_details("movie", title)
            if not media:
                continue

            release_date = media.get("release_date")
            status = media.get("status")

            await conn.execute("""
                UPDATE movies
                SET release_date = COALESCE($1, release_date),
                    status = COALESCE($2, status),
                    updated_at = now()
                WHERE id = $3
            """, release_date, status, r["id"])

            updated["movies"].append({
                "id": r["id"],
                "title": title,
                "release_date": release_date,
                "status": status
            })

        # ------------------------------------------------------------
        # 2️⃣ Update SERIES (next episodes, air dates, statuses)
        # ------------------------------------------------------------
        series_rows = await conn.fetch("""
            SELECT id, title, media_id, next_episode_date, status
            FROM series
        """)

        for r in series_rows:
            title = r["title"]
            media = await get_media_details("tv", title)
            if not media:
                continue

            next_date = media.get("next_episode_date")
            last_air = media.get("last_air_date")
            status = media.get("status")

            await conn.execute("""
                UPDATE series
                SET next_episode_date = COALESCE($1, next_episode_date),
                    last_air_date = COALESCE($2, last_air_date),
                    status = COALESCE($3, status),
                    updated_at = now()
                WHERE id = $4
            """, next_date, last_air, status, r["id"])

            updated["series"].append({
                "id": r["id"],
                "title": title,
                "next_episode_date": next_date,
                "status": status
            })

    except Exception as e:
        error_handler.handle(e, context="refresh_tmdb_dates(global)")
    finally:
        await conn.close()

    return updated

refresh_tmdb_dates()