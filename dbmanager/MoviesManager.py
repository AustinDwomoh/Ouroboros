from settings import *
import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from .async_pg_client import create_connection as create_async_connection
from settings import ErrorHandler


def is_similar(a, b, threshold=0.7):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= threshold


async def create_connection(db_path="data/mediarecords.db"):
    """Return an async DB connection (asyncpg). db_path is ignored in Postgres-only mode."""
    return await create_async_connection(db_path)


async def create_user_tables(user_id=None):
    """No-op for Postgres: migrations should create the centralized tables.

    This function simply verifies a working connection.
    """
    conn = await create_connection()
    try:
        await conn.execute("SELECT 1")
    finally:
        await conn.close()


async def update_user_ids(user_id):
    """Ensure user exists in centralized user_payments/user_media references.

    This inserts into user_payments (used as a registry) if missing.
    """
    try:
        conn = await create_connection()
        try:
            exists = await conn.fetchval("SELECT 1 FROM user_payments WHERE user_id = $1", int(user_id))
            if not exists:
                await conn.execute("INSERT INTO user_payments (user_id) VALUES ($1)", int(user_id))
        finally:
            await conn.close()
    except Exception as e:
        ErrorHandler().handle(e, context=f"update_user_ids failed for {user_id}")


async def delete_user_database(user_id):
    """Deletes the user's movie and series records from the centralized Postgres schema."""
    conn = await create_connection()
    try:
        await conn.execute("DELETE FROM user_movies_watched WHERE user_id = $1", int(user_id))
        await conn.execute("DELETE FROM user_series_progress WHERE user_id = $1", int(user_id))
        await conn.execute("DELETE FROM user_watchlist WHERE user_id = $1", int(user_id))
        await conn.execute("DELETE FROM user_media WHERE user_id = $1", int(user_id))
    finally:
        await conn.close()
    return "Your movie and series record has been deleted."


async def add_or_update_movie(user_id, title, date=None):
    """Add or update a watched movie for a user in Postgres normalized tables."""
    await update_user_ids(user_id)
    conn = await create_connection()
    try:
        # ensure movie exists
        row = await conn.fetchrow("SELECT id FROM movies WHERE title ILIKE $1", title)
        if row:
            movie_id = row["id"]
        else:
            movie_id = await conn.fetchval("INSERT INTO movies (title, release_date) VALUES ($1,$2) RETURNING id", title, date)

        await conn.execute(
            "INSERT INTO user_movies_watched (user_id, movie_id, watched_date) VALUES ($1,$2,$3) ON CONFLICT (user_id, movie_id) DO UPDATE SET watched_date = EXCLUDED.watched_date",
            int(user_id), movie_id, date,
        )
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


async def fetch_titles(user_id):
    """Return a deduplicated list of titles associated with a user (watched + watchlist + series progress)."""
    conn = await create_connection()
    try:
        rows = await conn.fetch(
            """
            SELECT DISTINCT title FROM (
                SELECT m.title AS title
                FROM user_movies_watched umw
                JOIN movies m ON umw.movie_id = m.id
                WHERE umw.user_id = $1
                UNION
                SELECT s.title AS title
                FROM user_series_progress usp
                JOIN series s ON usp.series_id = s.id
                WHERE usp.user_id = $1
                UNION
                SELECT title FROM user_watchlist uw WHERE uw.user_id = $1
            ) t
            ORDER BY title ASC
            """,
            int(user_id),
        )
        return [r["title"] for r in rows]
    finally:
        await conn.close()


async def view_watch_list(user_id, media_type):
    conn = await create_connection()
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


# ============================================================================ #
#                         MOVIE AND SERIES API SERVICES                        #
# ============================================================================ #


async def get_media_details(media, media_name):
    id = await search_media_id(media, media_name)

    media_data = {}
    if id:
        async with aiohttp.ClientSession() as session:
            url = f"{MOVIE_BASE_URL}/{media}/{id}?api_key={MOVIE_API_KEY}&append_to_response=watch/providers"
            async with session.get(url) as response:
                data = await response.json()
                if data.get("status_code") != 34:
                    if media == "tv":
                        media_data = {
                            "title": data.get("name"),
                            "original_title": data.get("original_name"),
                            "overview": data.get("overview"),
                            "genres": [genre["name"] for genre in data.get("genres", [])],
                            "release_date": data.get("first_air_date"),
                            "last_air_date": data.get("last_air_date"),
                            "next_episode_date": (
                                data.get("next_episode_to_air", {}).get("air_date") if data.get("next_episode_to_air") else None
                            ),
                            "next_episode_number": (
                                data.get("next_episode_to_air", {}).get("episode_number") if data.get("next_episode_to_air") else None
                            ),
                            "next_season_number": (
                                data.get("next_episode_to_air", {}).get("season_number") if data.get("next_episode_to_air") else None
                            ),
                            "seasons": [
                                {"season_number": season.get("season_number"), "episode_count": season.get("episode_count")} for season in data.get("seasons", [])
                            ],
                            "last_episode": (
                                {
                                    "episode": data.get("last_episode_to_air", {}).get("episode_number"),
                                    "season": data.get("last_episode_to_air", {}).get("season_number"),
                                    "air_date": data.get("last_episode_to_air", {}).get("air_date"),
                                }
                                if data.get("last_episode_to_air")
                                else None
                            ),
                            "poster_url": (
                                f"https://image.tmdb.org/t/p/w500{data.get('poster_path')}" if data.get("poster_path") else None
                            ),
                            "homepage": data.get("homepage"),
                            "status": data.get("status"),
                        }
                    else:
                        media_data = {
                            "title": data.get("title"),
                            "overview": data.get("overview"),
                            "genres": [genre["name"] for genre in data.get("genres", [])],
                            "release_date": data.get("release_date"),
                            "poster_url": (
                                f"https://image.tmdb.org/t/p/w500{data.get('poster_path')}" if data.get("poster_path") else None
                            ),
                            "homepage": data.get("homepage"),
                            "status": data.get("status"),
                            "in_collection": (
                                [
                                    {
                                        "id": data.get("belongs_to_collection", {}).get("id"),
                                        "name": data.get("belongs_to_collection", {}).get("name"),
                                        "poster_path": (
                                            f"https://image.tmdb.org/t/p/w500{data.get('belongs_to_collection', {}).get('poster_path')}"
                                            if data.get("belongs_to_collection", {}).get("poster_path")
                                            else None
                                        ),
                                        "backdrop_path": (
                                            f"https://image.tmdb.org/t/p/w500{data.get('belongs_to_collection', {}).get('backdrop_path')}"
                                            if data.get("belongs_to_collection", {}).get("backdrop_path")
                                            else None
                                        ),
                                    }
                                ]
                                if data.get("belongs_to_collection")
                                else []
                            ),
                        }
    return media_data


async def search_media_id(media, media_name):
    formatted_name = media_name.replace(" ", "+")
    url = f"{MOVIE_BASE_URL}/search/{media}?query={formatted_name}&api_key={MOVIE_API_KEY}"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()

    results = data.get("results", [])
    id = None
    for result in results:
        title = result.get("name") or result.get("title")
        if title and is_similar(title, media_name):
            id = result.get("id")
            break
    return id


async def search_hianime(keyword):
    """Scrape Hianime search results for a given keyword."""
    search_url = f"{H_BASE_URL}/search?keyword={keyword}"
    async with aiohttp.ClientSession() as session:
        async with session.get(search_url) as response:
            if response.status != 200:
                return {"error": "Failed to fetch data"}

            html = await response.text()
    # Parse HTML
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for item in soup.select(
        ".film_list-wrap .flw-item"
    ):  # Selecting each search result
        title_tag = item.select_one(".dynamic-name")
        link_tag = item.select_one("a")
        img_tag = item.select_one("img")

        if title_tag and link_tag and img_tag:
            results.append(
                {
                    "title": title_tag.text.strip(),
                    "link": H_BASE_URL + link_tag["href"],
                    "thumbnail": (
                        img_tag["data-src"] if img_tag.has_attr("data-src") else img_tag["src"]
                    ),
                }
            )
    return results


async def check_upcoming_dates():
    """Returns reminders combining user_series_progress + user_watchlist entries for the next 7 days."""
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    upcoming_date = (now + timedelta(days=7)).date().isoformat()
    reminders = []
    conn = await create_connection()
    try:
        # series with next_episode_date in series table and user is tracking
        series_rows = await conn.fetch(
            """
            SELECT usp.user_id, s.title, usp.season, usp.episode, usp.status, s.next_episode_date
            FROM user_series_progress usp
            JOIN series s ON usp.series_id = s.id
            WHERE s.next_episode_date IS NOT NULL AND s.next_episode_date BETWEEN $1 AND $2
            ORDER BY s.next_episode_date ASC
            """,
            today,
            upcoming_date,
        )
        for r in series_rows:
            reminders.append(
                {
                    "user_id": r["user_id"],
                    "name": r["title"],
                    "season": r["season"],
                    "episode": r["episode"],
                    "status": r["status"],
                    "next_release_date": r["next_episode_date"],
                }
            )

        # watchlist series
        wl_series = await conn.fetch(
            "SELECT user_id, title, next_release_date FROM user_watchlist WHERE media_type = 'series' AND next_release_date BETWEEN $1 AND $2",
            today,
            upcoming_date,
        )
        for r in wl_series:
            reminders.append({"user_id": r["user_id"], "name": r["title"], "next_release_date": r["next_release_date"]})

        # watchlist movies
        wl_movies = await conn.fetch(
            "SELECT user_id, title, release_date FROM user_watchlist WHERE media_type = 'movie' AND release_date BETWEEN $1 AND $2",
            today,
            upcoming_date,
        )
        for r in wl_movies:
            reminders.append({"user_id": r["user_id"], "name": r["title"], "release_date": r["release_date"], "movie": True})
    finally:
        await conn.close()
    return reminders


async def check_completion():
    """Checks whether a series has been completed using centralized tables and TMDB data."""
    reminders = []
    conn = await create_connection()
    try:
        rows = await conn.fetch("SELECT usp.user_id, s.title, usp.season, usp.episode FROM user_series_progress usp JOIN series s ON usp.series_id = s.id")
        for r in rows:
            user_id = r["user_id"]
            title = r["title"]
            last_season = r["season"]
            last_episode = r["episode"]
            first_value = await get_media_details("tv", title)
            if first_value and first_value.get("last_episode"):
                last_released = first_value["last_episode"]
                season = last_released.get("season", 0)
                episode = last_released.get("episode", 0)
                if (season > last_season and episode != 0) or (season == last_season and episode > last_episode):
                    reminders.append({
                        "user_id": user_id,
                        "name": title,
                        "unwatched": (season, episode),
                        "watched": (last_season, last_episode),
                        "poster_url": first_value.get("poster_url"),
                    })
    finally:
        await conn.close()
    return reminders


async def refresh_tmdb_dates():
    conn = await create_connection()
    try:
        rows = await conn.fetch("SELECT DISTINCT usp.series_id FROM user_series_progress usp")
        series_ids = {r["series_id"] for r in rows}
        for series_id in series_ids:
            title = await conn.fetchval("SELECT title FROM series WHERE id = $1", series_id)
            if not title:
                continue
            first_value = await get_media_details("tv", title)
            next_date = first_value.get("next_episode_date") if first_value else None
            status = first_value.get("status") if first_value else None
            await conn.execute("UPDATE series SET next_episode_date = $1, status = $2 WHERE id = $3", next_date, status, series_id)
    finally:
        await conn.close()



            async def check_completion():
                """Checks whether a series has been completed using centralized tables and TMDB data."""
                reminders = []
                conn = await create_connection()
                try:
                    rows = await conn.fetch("SELECT usp.user_id, s.title, usp.season, usp.episode FROM user_series_progress usp JOIN series s ON usp.series_id = s.id")
                    for r in rows:
                        user_id = r["user_id"]
                        title = r["title"]
                        last_season = r["season"]
                        last_episode = r["episode"]
                        first_value = await get_media_details("tv", title)
                        if first_value and first_value.get("last_episode"):
                            last_released = first_value["last_episode"]
                            season = last_released.get("season", 0)
                            episode = last_released.get("episode", 0)
                            if (season > last_season and episode != 0) or (season == last_season and episode > last_episode):
                                reminders.append({
                                    "user_id": user_id,
                                    "name": title,
                                    "unwatched": (season, episode),
                                    "watched": (last_season, last_episode),
                                    "poster_url": first_value.get("poster_url"),
                                })
                finally:
                    await conn.close()
                return reminders


            async def refresh_tmdb_dates():
                conn = await create_connection()
                try:
                    rows = await conn.fetch("SELECT DISTINCT usp.user_id, s.title, usp.series_id FROM user_series_progress usp JOIN series s ON usp.series_id = s.id")
                    for r in rows:
                        series_id = r["series_id"]
                        title = r["title"]
                        first_value = await get_media_details("tv", title)
                        next_date = first_value.get("next_episode_date")
                        status = first_value.get("status")
                        await conn.execute("UPDATE series SET next_episode_date = $1, status = $2 WHERE id = $3", next_date, status, series_id)
                finally:
                    await conn.close()

    return list(titles)


async def view_watch_list(user_id, media_type):
    conn = await create_connection()
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


# ============================================================================ #
#                         MOVIE AND SERIES API SERVICES                        #
# ============================================================================ #

    

async def get_media_details(media, media_name):
    id = await search_media_id(media, media_name)

    media_data = {}
    if id:
        async with aiohttp.ClientSession() as session:
            url = f"{MOVIE_BASE_URL}/{media}/{id}?api_key={MOVIE_API_KEY}&append_to_response=watch/providers"
            async with session.get(url) as response:
                data = await response.json()
                if data.get("status_code") != 34:
                    if media == "tv":
                        media_data= {
                            "title": data["name"],
                            "original_title":data['original_name'],
                            "overview": data["overview"],
                            "genres": [genre["name"] for genre in data["genres"]],
                            "release_date": data["first_air_date"],
                            "last_air_date": data["last_air_date"],
                            "next_episode_date": (
                                    data["next_episode_to_air"]["air_date"]
                                    if data.get("next_episode_to_air")
                                    else None
                                ),
                            "next_episode_number": (
                                data["next_episode_to_air"]["episode_number"]
                                if data.get("next_episode_to_air")
                                else None
                            ),
                            "next_season_number": (
                                data["next_episode_to_air"]["season_number"]
                                if data.get("next_episode_to_air")
                                else None
                            ), 
                            "seasons": [
                                {
                                    "season_number": season["season_number"],
                                    "episode_count": season["episode_count"]
                                }
                                for season in data["seasons"]],
                            "last_episode": (
                                {
                                    "episode": data["last_episode_to_air"].get("episode_number"),
                                    "season": data["last_episode_to_air"].get("season_number"),
                                    "air_date": data["last_episode_to_air"].get("air_date"),
                                }
                                if data.get("last_episode_to_air") else None
                            ),
                            "poster_url": (
                                f"https://image.tmdb.org/t/p/w500{data['poster_path']}"
                                if data.get("poster_path")
                                else None
                            ),
                            "homepage": data["homepage"],
                            "status": data["status"],
                            
                        }
                        
                    else:
                        media_data = {
                            "title": data["title"],
                            "overview": data["overview"],
                            "genres": [genre["name"] for genre in data["genres"]],
                            "release_date": data["release_date"],
                            "poster_url": (
                                f"https://image.tmdb.org/t/p/w500{data['poster_path']}"
                                if data.get("poster_path")
                                else None
                            ),
                            "homepage": data["homepage"],
                            "status": data["status"],
                            "in_collection": (
                                [
                                    {
                                        "id": data["belongs_to_collection"]["id"],
                                        "name": data["belongs_to_collection"]["name"],
                                        "poster_path": (
                                            f"https://image.tmdb.org/t/p/w500{data["belongs_to_collection"]['poster_path']}"
                                            if data["belongs_to_collection"].get(
                                                "poster_path"
                                            )
                                            else None
                                        ),
                                        "backdrop_path": (
                                            f"https://image.tmdb.org/t/p/w500{data["belongs_to_collection"]['backdrop_path']}"
                                            if data["belongs_to_collection"].get(
                                                "backdrop_path"
                                            )
                                            else None
                                        ),
                                    }
                                ]
                                if data.get("belongs_to_collection")
                                else []
                            ),
                        }
    return media_data

async def search_media_id(media, media_name):
    formatted_name = media_name.replace(" ", "+")
    url = f"{MOVIE_BASE_URL}/search/{media}?query={formatted_name}&api_key={MOVIE_API_KEY}"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()

    results = data.get("results", [])
    id = None 
    for result in results:
        title = result.get("name") or result.get("title")
        if title and is_similar(title, media_name):
            id = result.get('id')
            break
    return id

async def search_hianime(keyword):
    """Scrape Hianime search results for a given keyword."""
    search_url = f"{H_BASE_URL}/search?keyword={keyword}"
    async with aiohttp.ClientSession() as session:
        async with session.get(search_url) as response:
            if response.status != 200:
                return {"error": "Failed to fetch data"}

            html = await response.text()
    # Parse HTML
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for item in soup.select(
        ".film_list-wrap .flw-item"
    ):  # Selecting each search result
        title_tag = item.select_one(".dynamic-name")
        link_tag = item.select_one("a")
        img_tag = item.select_one("img")

        if title_tag and link_tag and img_tag:
            results.append(
                {
                    "title": title_tag.text.strip(),
                    "link": H_BASE_URL + link_tag["href"],
                    "thumbnail": (
                        img_tag["data-src"]
                        if img_tag.has_attr("data-src")
                        else img_tag["src"]
                    ),
                }
            )
    return results

async def fetch_reminders(cursor, table_name, columns):
    try:
        await cursor.execute(f"SELECT {columns} FROM {table_name}")
        return await cursor.fetchall()
    except aiosqlite.OperationalError:
        return []

async def check_upcoming_dates():
    """
    This method looks through the tables and checks their dates which are formed when they are added
    """
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    upcoming_date = (now + timedelta(days=7)).date().isoformat()
    reminders = []
    conn = await create_connection()
    errorHandler = ErrorHandler()  # Moved outside of the loop for efficiency
    try:
        async with conn.cursor() as cursor:
            await create_user_tables()
            await cursor.execute("SELECT DISTINCT user_id FROM user_media")
            user_ids = [row[0] for row in await cursor.fetchall()]
            for user_id in user_ids:
                table_name = f'"{user_id}_Series"'

                try:
                    await cursor.execute(
                        f"""
                        SELECT title, season, episode,status, next_release_date
                        FROM {table_name}  
                        WHERE next_release_date IS NOT NULL 
                            AND status != 'E
                            nded'
                            AND next_release_date BETWEEN ? AND ? 
                        ORDER BY next_release_date ASC
                        """,
                        (today, upcoming_date),
                    )


                    user_reminders = await cursor.fetchall()
                    for title, season, episode,status, next_release_date in user_reminders:
                        reminders.append(
                            {
                                "user_id": user_id,
                                "name": title,
                                "season": season,
                                "status":status,
                                "episode": episode,
                                "next_release_date": next_release_date,
                            }
                        )
                        
                
                   
                    table_name = f'"{user_id}_watch_list_Series"' 
                    rows = await fetch_reminders(cursor, table_name, "*")
                    for item in rows:
                        reminders.append({
                            "user_id": user_id,
                            "name": item[1],
                            "next_release_date": item[6],
                        })
                    
                    table_name = f'"{user_id}_watch_list_Movies"' 
                    rows = await fetch_reminders(cursor, table_name, "*")
                    for item in rows:
                        reminders.append({
                            "user_id": user_id,
                            "name": item[1],
                            "release_date":item[4],
                            "movie":True,
                        })

                except aiosqlite.OperationalError as e:
                    errorHandler.handle(e, context=f"Error processing user {user_id} in check_upcoming_dates")
    finally:
        await conn.close()
    return reminders

async def check_completion():
    """Checks whether a series has been completed once its in the db
    """
    reminders = []
    conn = await create_connection()
    errorHandler = ErrorHandler()  
    try:
        async with conn.cursor() as cursor:
            await create_user_tables()
            await cursor.execute("SELECT DISTINCT user_id FROM user_media")
            user_ids = [row[0] for row in await cursor.fetchall()]
            for user_id in user_ids:
                table_name = f'"{user_id}_Series"'
                
                await cursor.execute(
                    f"SELECT title, season, episode FROM {table_name}"
                )
                shows = await cursor.fetchall()
              

                for title, last_season, last_episode in shows:
                    first_value = await get_media_details('tv', title)
                    if first_value  and first_value["last_episode"] :
                        last_released = first_value['last_episode']
                        season = last_released.get("season", 0)
                        episode = last_released.get("episode", 0)

                        if (season > last_season and episode !=0) or (season == last_season and episode > last_episode):
                            reminders.append({
                                "user_id": user_id,
                                "name": title,
                                "unwatched": (season, episode),
                                "watched": (last_season, last_episode),
                                "poster_url": first_value.get("poster_url")
                            })
                   
        """ with open("reminders.json", "w", encoding="utf-8") as f:
            json.dump(show, f, indent=4) """
               
    except Exception as e:
        errorHandler.handle(e, context="Error in check_completion")
        await conn.commit()
    finally:
        await conn.close()
    return reminders

async def refresh_tmdb_dates():
    conn = await create_connection()
    errorHandler = ErrorHandler()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT DISTINCT user_id FROM user_media")
            user_ids = [row[0] for row in await cursor.fetchall()]
            for user_id in user_ids:
                table_name = f'"{user_id}_Series"'
                await cursor.execute(f"SELECT title FROM {table_name}")
                titles = [row[0] for row in await cursor.fetchall()]
                for title in titles:
                    first_value = await get_media_details("tv", title)
                    next_date = first_value.get("next_episode_date")
                    status = first_value.get("status")
                    await cursor.execute(
                            f"""
                            UPDATE {table_name}
                            SET next_release_date = ?, status = ?
                            WHERE title = ? 
                            """,
                            (next_date, status, title),
                        )
                    await conn.commit()

    except Exception as e:
        errorHandler.handle(e, context="Error in refresh_tmdb_dates")
        await conn.commit()
    finally:
        await conn.close()
