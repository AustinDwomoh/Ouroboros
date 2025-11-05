from datetime import datetime, timedelta, timezone
from settings import ErrorHandler, create_async_pg_conn
from movies.api_calls import get_media_details

error_handler = ErrorHandler()



# --------------------------------------------------------------------------
# 1. CHECK UPCOMING DATES
# --------------------------------------------------------------------------
async def check_upcoming_dates():
    """
    Fetches shows or movies releasing in the next 7 days for all users.
    Combines user_series_progress and user_watchlist for reminder use.
    """
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    next_week = (now + timedelta(days=7)).date().isoformat()
    reminders = []
    conn = await create_async_pg_conn()

    try:
        # Series tracked by users with upcoming episodes
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
            })

        # Watchlist entries with upcoming movie releases
        wl_movies = await conn.fetch("""
            SELECT user_id, title, release_date
            FROM user_watchlist
            WHERE media_type = 'movie'
              AND release_date BETWEEN $1 AND $2
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
async def check_completion():
    """
    Verifies whether users are behind on their tracked series
    by comparing stored season/episode with TMDB's latest data.
    """
    reminders = []
    conn = await create_async_pg_conn()

    try:
        rows = await conn.fetch("""
            SELECT usp.user_id, s.title, usp.season, usp.episode
            FROM user_series_progress usp
            JOIN series s ON usp.series_id = s.id
        """)

        for r in rows:
            user_id = r["user_id"]
            title = r["title"]
            last_season = r["season"]
            last_episode = r["episode"]

            media = await get_media_details("tv", title)
            if not media:
                continue

            latest = media.get("last_episode")
            if not latest:
                continue

            season = latest.get("season", 0)
            episode = latest.get("episode", 0)

            # user is behind if new episode released
            if (season > last_season and episode != 0) or (season == last_season and episode > last_episode):
                reminders.append({
                    "user_id": user_id,
                    "title": title,
                    "unwatched": (season, episode),
                    "watched": (last_season, last_episode),
                    "poster_url": media.get("poster_url"),
                })
    except Exception as e:
        error_handler.handle(e, context="check_completion")
    finally:
        await conn.close()

    return reminders


# --------------------------------------------------------------------------
# 3. REFRESH SERIES DATES FROM TMDB
# --------------------------------------------------------------------------
async def refresh_tmdb_dates():
    """
    Periodically refresh next_episode_date and status
    for all series tracked by users (to keep reminders accurate).
    """
    conn = await create_async_pg_conn()
    updated = []

    try:
        series_ids = await conn.fetch("SELECT DISTINCT series_id FROM user_series_progress")
        for r in series_ids:
            series_id = r["series_id"]
            title = await conn.fetchval("SELECT title FROM series WHERE id=$1", series_id)
            if not title:
                continue

            media = await get_media_details("tv", title)
            if not media:
                continue

            next_date = media.get("next_episode_date")
            status = media.get("status")

            await conn.execute("""
                UPDATE series
                SET next_episode_date = $1, status = $2
                WHERE id = $3
            """, next_date, status, series_id)
            updated.append({"id": series_id, "title": title})
    except Exception as e:
        error_handler.handle(e, context="refresh_tmdb_dates")
    finally:
        await conn.close()

    return updated

