from settings import *
import aiohttp, aiosqlite
from bs4 import BeautifulSoup
from datetime import datetime, timedelta,timezone
from difflib import SequenceMatcher

def is_similar(a, b, threshold=0.7):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= threshold


async def create_connection(db_path="data/mediarecords.db"):
    """Creates and returns a database connection."""
    # Database file
    return await aiosqlite.connect(db_path)


async def create_user_tables(user_id=None):
    """Creates tables for a user based on their user ID."""
    table_name_movies = f'"{user_id}_Movies"'
    table_name_series = f'"{user_id}_Series"'
    table_name_watch_list_movies = f'"{user_id}_watch_list_Movies"'
    table_name_watch_list_series = f'"{user_id}_watch_list_Series"'

    conn = await create_connection()
    try:
        async with conn.cursor() as cursor:
            # Create movies table
            if user_id:
                await cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {table_name_movies} (
                        id INTEGER PRIMARY KEY,
                        title TEXT,
                        date TEXT
                    )
                """
                )

                await cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {table_name_series} (
                        id INTEGER PRIMARY KEY,
                        title TEXT,
                        season INTEGER,
                        episode INTEGER,
                        date TEXT,
                        status TEXT,
                        next_release_date TEXT
                    )
                """
                )
                #added later on 
                await cursor.execute(f"PRAGMA table_info({table_name_series})")

                await cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {table_name_watch_list_movies} (
                        id INTEGER PRIMARY KEY,
                        title TEXT,
                        extra TEXT,
                        status TEXT,
                        release_date TEXT,
                        added_date TEXT,
                        next_release_date TEXT
                    )
                """
                )
                
                await cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {table_name_watch_list_series} (
                        id INTEGER PRIMARY KEY,
                        title TEXT,
                        extra TEXT,
                        status TEXT,
                        release_date TEXT,
                        added_date TEXT,
                        next_release_date TEXT
                    )
                """
                )
            await cursor.execute(
                f"""
            CREATE TABLE IF NOT EXISTS user_media (  
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER  NOT NULL
            )"""
            )

            await conn.commit()
    finally:
        await conn.close()


async def delete_user_database(user_id):
    """Deletes the user's movie and series tables."""
    # Define table names for the user
    table_name_movies = f'"{user_id}_Movies"'
    table_name_series = f'"{user_id}_Series"'

    conn = await create_connection()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(f"DROP TABLE IF EXISTS {table_name_movies}")
            await cursor.execute(f"DROP TABLE IF EXISTS {table_name_series}")
            await cursor.execute(
                f"DELETE FROM user_media WHERE user_id LIKE ?", (user_id,)
            )
            await conn.commit()
    finally:
        await conn.close()
    return "Your movie and series record has been deleted."


async def add_or_update_movie(user_id, title, date=None):
    """
    Adds a new movie or updates an existing one for the user.

    :param user_id: Unique identifier for the user.
    :param title: Title of the movie (mandatory).
    :param date: Additional date (optional).
    """
    table_name = f'"{user_id}_Movies"'
    await create_user_tables(user_id)
    await update_user_ids(user_id)
    conn = await create_connection()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                f"SELECT * FROM {table_name} WHERE title LIKE ?", ("%" + title + "%",)
            )
            existing = await cursor.fetchone()
            if existing:
                # Update existing movie
                await cursor.execute(
                    f"""
                    UPDATE {table_name}
                    SET date = COALESCE(?, date)
                    WHERE title = ?
                """,
                    (date, title),
                )
            else:
                # Insert new movie
                await cursor.execute(
                    f"""
                    INSERT INTO {table_name} (title, date)
                    VALUES (?,?)
                """,
                    (title, date),
                )
            await conn.commit()
    finally:
        await conn.close()


async def add_or_update_series(user_id, title, season=None, episode=None, date=None):
    """
    Adds a new series or updates an existing one for the user.

    :param user_id: Unique identifier for the user.
    :param title: Title of the series (mandatory).
    :param season: Current season of the series (optional).
    :param episode: Current episode of the series (optional).
    :param date: Additional date (optional).
    """
    table_name = f'"{user_id}_Series"'
    await create_user_tables(user_id)
    await update_user_ids(user_id)
    conn = await create_connection()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                f"SELECT * FROM {table_name} WHERE title LIKE ?", ("%" + title + "%",)
            )
            existing = await cursor.fetchone()
            first_value = await get_media_details("tv", title)
            next_release_date = first_value.get("next_episode_date")
            
            status = first_value.get("status","watching")
            if existing:
                # Update existing series
                await cursor.execute(
                    f"""
                    UPDATE {table_name}
                    SET season = COALESCE(?, season),
                        episode = COALESCE(?, episode),
                        date = COALESCE(?, date),
                        status = COAlESCE(?, status),
                        next_release_date = COALESCE(?, next_release_date)
                    WHERE title = ?
                """,
                    (season, episode, date,status,next_release_date,title),
                )
                
            else:
                # Insert new series
                await cursor.execute(
                    f"""
                    INSERT INTO {table_name} (title, season, episode, date,status,next_release_date)
                    VALUES (?, ?, ?, ?,?,?)
                """,
                    (title, season, episode, date,status, next_release_date),
                )
            await conn.commit()
            return next_release_date
    finally: 
        await conn.close()


async def delete_media(user_id, title, media_type):
    """
    Adds a new movie or updates an existing one for the user.

    :param user_id: Unique identifier for the user.
    :param title: Title of the movie (mandatory).
    """
    if media_type.lower() == "movie":
        table_name = f'"{user_id}_Movies"'
    elif media_type.lower() == "series":
        table_name = f'"{user_id}_Series"'

    await create_user_tables(user_id)
    conn = await create_connection()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                f"DELETE FROM {table_name} WHERE title LIKE ?", ("%" + title + "%",)
            )
            await conn.commit()
    finally:
        await conn.close()


async def search_media(user_id, title, media_type):
    """
    Searches for a specific movie or series using a partial title match
    and returns the matching rows with all their data.

    :param user_id: Unique identifier for the user.
    :param title: Title or partial title to search for.
    :param media_type: Either "movie" or "series" to specify the type of media.
    :return: List of dictionaries, each representing a matching record.
    """
    # Determine the table to query based on media_type
    await create_user_tables(user_id)
    if media_type == "movie":
        table_name = f'"{user_id}_Movies"'
    elif media_type == "series":
        table_name = f'"{user_id}_Series"'
        media_type = 'tv'

    # Construct the query to fetch all columns
    query = f"SELECT * FROM {table_name} WHERE title LIKE ?"

    # Execute the query and fetch the results
    conn = await create_connection()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(query, (f"%{title}%",))
            column_names = [description[0] for description in cursor.description]
            row = await cursor.fetchone()
            if row is None:
                return None
            results = dict(zip(column_names, row))
            data = await get_media_details(media_type,title)
            combined = {
                "db_data": results,
                "api_data": data
            }                
        return combined
    except aiosqlite.OperationalError as e:
        if "no such table" in str(e):
            # Handle missing table error
            return {
                "error": f"You have no records. Please Add media with the add commands."
            }
        else:
            pass
    except Exception as e:
        # Handle any other unexpected exceptions
        return {"error": str(e)}
    finally:
        await conn.close()


async def view_media(user_id, media_type):
    """Retrieves all movies from the user's database."""
    if media_type.lower() == "movie":
        table_name = f'"{user_id}_Movies"'
    elif media_type.lower() == "series":
        table_name = f'"{user_id}_Series"'
        media_type = 'tv'
    await create_user_tables(user_id)
    conn = await create_connection()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(f"SELECT * FROM {table_name}")
            rows = await cursor.fetchall()

            # Get column names dynamically
            column_names = [column[0] for column in cursor.description]

            results = []
            for row in rows:
                db_data = dict(zip(column_names, row))
                title = db_data.get("title")
                if not title:
                    continue 
                try:
                    api_data = await get_media_details(media_type, title)
                except Exception as e:
                    print(f"[WARN] Failed to fetch API for '{title}': {e}")
                    api_data = None

                # Combine DB + API data
                combined = {
                    "db_data": db_data,
                    "api_data": api_data
                }
                results.append(combined)

            return results
    finally:
        await conn.close()


async def update_user_ids(user_id):
    conn = await create_connection()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT * FROM user_media WHERE user_id = ?", (user_id,)
            )
            existing = await cursor.fetchone()
            if not existing:
                await cursor.execute(
                    f""" INSERT INTO user_media (user_id) VALUES (?) """, (user_id,)
                )
        await conn.commit()
    finally:
        await conn.close()


async def add_or_update_watch_list(user_id, title, date, extra, media_type):
    """
    Adds a new movie or updates an existing one for the user.

    :param user_id: Unique identifier for the user.
    :param title: Title of the movie (mandatory).
    :param date: Additional date (optional).
    """
    if media_type.lower() == "movie":
        table_name = f'"{user_id}_watch_list_Movies"'
    elif media_type.lower() == "tv":
        table_name = f'"{user_id}_watch_list_Series"'
    await create_user_tables(user_id)
    await update_user_ids(user_id)
    conn = await create_connection()
    try:
        async with conn.cursor() as cursor:
            first_value = await get_media_details(media_type, title)
            title = first_value.get("title", title)
            status = first_value.get("status", "To be watched")
            release_date = first_value.get("release_date", "Unknown")
            next_release_date = first_value.get("next_episode_date", "Unknown")
            
                       

            await cursor.execute(
                f"""
                    INSERT INTO {table_name} (title, extra, status, release_date, added_date, next_release_date)
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                (title, extra, status, release_date, date, next_release_date),
            )
           

        await conn.commit()
    finally:
        await conn.close()


async def delete_from_watchlist(user_id, title, media_type):
    """
    Adds a new series or updates an existing one for the user.

    :param user_id: Unique identifier for the user.
    :param title: Title of the series (mandatory).
    :param season: Current season of the series (optional).
    :param episode: Current episode of the series (optional).
    :param date: Additional date (optional).
    """
    if media_type.lower() == "movie":
        table_name = f'"{user_id}_watch_list_Movies"'
    elif media_type.lower() == "series":
        table_name = f'"{user_id}_watch_list_Series"'

    await create_user_tables(user_id)
    conn = await create_connection()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                f"DELETE FROM {table_name} WHERE title LIKE ?", ("%" + title + "%",)
            )
            await conn.commit()
    finally:
        await conn.close()

async def fetch_titles(user_id):
    movie_table = f'"{user_id}_Movies"'
    series_table = f'"{user_id}_Series"'
    watch_list_s_table_name = f'"{user_id}_watch_list_Series"'
    watch_list_m_table_name = f'"{user_id}_watch_list_Movies"'
    await create_user_tables(user_id)
    conn = await create_connection()
    
    titles = set()

    try:
        async with conn.cursor() as cursor:
            # Fetch movie titles
            await cursor.execute(f"SELECT title FROM {movie_table}")
            movie_rows = await cursor.fetchall()
            titles.update(title[0] for title in movie_rows if title[0])

            # Fetch series titles
            await cursor.execute(f"SELECT title FROM {series_table}")
            series_rows = await cursor.fetchall()
            titles.update(title[0] for title in series_rows if title[0])
            
            #fecth watch_list_series titles
            await cursor.execute(f"SELECT title FROM{watch_list_s_table_name}") 
            watch_list_series_rows = await cursor.fetchall()
            titles.update(title[0] for title in watch_list_series_rows if title[0])
                            
            #fecth watch_list_movie titles
            await cursor.execute(f"SELECT title FROM{watch_list_m_table_name}")
            watch_list_movies_rows = await cursor.fetchall()
            titles.update(title[0] for title in watch_list_movies_rows if title[0])
    finally:
        await conn.close()

    return list(titles)

           

async def view_watch_list(user_id, media_type):
    """Retrieves all movies from the user's database."""
    if media_type.lower() == "movie":
        table_name = f'"{user_id}_watch_list_Movies"'
    elif media_type.lower() == "series":
        table_name = f'"{user_id}_watch_list_Series"'
        media_type = "tv"
    await create_user_tables(user_id)
    conn = await create_connection()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(f"SELECT * FROM {table_name}")
            rows = await cursor.fetchall()
            column_names = [column[0] for column in cursor.description]

            results = []
            for row in rows:
                db_data = dict(zip(column_names, row))
                title = db_data.get("title")
                if not title:
                    continue 
                try:
                    api_data = await get_media_details(media_type, title)
                except Exception as e:
                    print(f"[WARN] Failed to fetch API for '{title}': {e}")
                    api_data = None

                # Combine DB + API data
                combined = {
                    "db_data": db_data,
                    "api_data": api_data
                }
                results.append(combined)

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
                    errorHandler.handle_exception(e)
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
        errorHandler.handle_exception(e)
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
        errorHandler.handle_exception(e)
        await conn.commit()
    finally:
        await conn.close()
