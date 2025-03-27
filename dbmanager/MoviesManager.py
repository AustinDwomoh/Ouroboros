from settings import *
import  aiohttp, aiosqlite
from bs4 import BeautifulSoup
from datetime import datetime, timedelta


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
            media_data = await get_media_details("tv", title)
            first_key = next(iter(media_data), None)
            first_value = media_data.get(first_key, {})
            next_release_date = (
                first_value.get("next_episode_date", "N/A")
                if "next_episode_date" in first_value
                else None
            )
            if existing:
                # Update existing series
                await cursor.execute(
                    f"""
                    UPDATE {table_name}
                    SET season = COALESCE(?, season),
                        episode = COALESCE(?, episode),
                        date = COALESCE(?, date),
                        next_release_date = COALESCE(?, next_release_date)
                    WHERE title = ?
                """,
                    (season, episode, date,next_release_date,title),
                )
            else:
                # Insert new series
                await cursor.execute(
                    f"""
                    INSERT INTO {table_name} (title, season, episode, date, next_release_date)
                    VALUES (?, ?, ?, ?,?)
                """,
                    (title, season, episode, date, next_release_date),
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

    # Construct the query to fetch all columns
    query = f"SELECT * FROM {table_name} WHERE title LIKE ?"

    # Execute the query and fetch the results
    conn = await create_connection()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(query, (f"%{title}%",))
            column_names = [description[0] for description in cursor.description]
            rows = await cursor.fetchall()
            results = [dict(zip(column_names, row)) for row in rows]
        return results
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
    await create_user_tables(user_id)
    conn = await create_connection()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(f"SELECT * FROM {table_name}")
            return await cursor.fetchall()
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
            await cursor.execute(
                f"SELECT * FROM {table_name} WHERE title LIKE ?", ("%" + title + "%",)
            )
            existing = await cursor.fetchone()
            if existing:
                await cursor.execute(
                    f"""
                    UPDATE {table_name}
                    SET date = COALESCE(?, date),
                        extra = COALESCE(?, extra)
                    WHERE title = ?
                """,
                    (date, extra, title),
                )
            else:
                media_data = await get_media_details(media_type, title)
                first_key = next(iter(media_data), None)
                first_value = media_data.get(first_key, {})
                title = first_value.get("title", "Unknown")
                status = first_value.get("status", "Unknown")
                release_date = first_value.get("release_date", "Unknown")
                next_release_date = (
                    first_value.get("next_episode_date", "N/A")
                    if "next_episode_date" in first_value
                    else None
                )
                

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


async def view_watch_list(user_id, media_type):
    """Retrieves all movies from the user's database."""
    if media_type.lower() == "movie":
        table_name = f'"{user_id}_watch_list_Movies"'
    elif media_type.lower() == "series":
        table_name = f'"{user_id}_watch_list_Series"'
    await create_user_tables(user_id)
    conn = await create_connection()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(f"SELECT * FROM {table_name}")
            return await cursor.fetchall()
    finally:
        await conn.close()


# ============================================================================ #
#                         MOVIE AND SERIES API SERVICES                        #
# ============================================================================ #
async def get_media_details(media, media_name):
    ids = await search_media_id(media, media_name)

    media_data = {}
    for i in range(len(ids)):

        url = f"{MOVIE_BASE_URL}/{media}/{ids[i]}?api_key={MOVIE_API_KEY}&append_to_response=watch/providers"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                if media == "tv":
                    media_data[f"{media}_{i}"] = {
                        "title": data["name"],
                        "overview": data["overview"],
                        "genres": [genre["name"] for genre in data["genres"]],
                        "release_date": data["first_air_date"],
                        "last_air_date": data["last_air_date"],
                        "next_episode_date": (
                            data["next_episode_to_air"]["air_date"]
                            if data.get("next_episode_to_air")
                            else "N/A"
                        ),
                        "seasons": [
                            {
                                "season_number": season["season_number"],
                                "episode_count": season["episode_count"],
                            }
                            for season in data["seasons"]
                        ],
                        "poster_url": (
                            f"https://image.tmdb.org/t/p/w500{data['poster_path']}"
                            if data.get("poster_path")
                            else None
                        ),
                        "homepage": data["homepage"],
                        "status": data["status"],
                        "networks": [network["name"] for network in data["networks"]],
                    }
                else:
                    media_data[f"{media}_{i}"] = {
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
    ids = []
    for data in results:
        ids.append(data["id"])
    return ids


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



async def check_upcoming_dates():
    today = datetime.today().strftime("%Y-%m-%d")
    upcoming_date = (datetime.today() + timedelta(days=7)).strftime("%Y-%m-%d")
    reminders = []
    conn = await create_connection()
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
                    SELECT title, season, episode, next_release_date
                    FROM {table_name}  
                    WHERE next_release_date IS NOT NULL 
                    AND next_release_date BETWEEN ? AND ? 
                    ORDER BY next_release_date ASC
                """,
                        (today, upcoming_date),
                    )

                    user_reminders = await cursor.fetchall()
                    for title, season, episode, next_release_date in user_reminders:
                        reminders.append(
                            {
                                "user_id": user_id,
                                "name": title,
                                "season": season,
                                "episode": episode,
                                "next_release_date": next_release_date,
                            }
                        )

                except aiosqlite.OperationalError as e:
                    pass

                table_name = f'"{user_id}_watch_list_Movies"'
                try:
                    await cursor.execute(f"SELECT * FROM {table_name} ")
                    user_reminders = await cursor.fetchall()
                    for item in user_reminders:
                        reminders.append(
                            {
                                "user_id": user_id,
                                "name": item[1],
                                "status": item[3],
                                "release_date": item[4],
                                "next_release_date": item[6],
                            }
                        )
                except aiosqlite.OperationalError as e:
                    pass

                table_name = f'"{user_id}_watch_list_Series"'
                try:

                    await cursor.execute(f"SELECT * FROM {table_name} ")
                    user_reminders = await cursor.fetchall()
                    for item in user_reminders:
                        reminders.append(
                            {
                                "user_id": user_id,
                                "name": item[1],
                                "status": item[3],
                                "release_date": item[4],
                                "next_release_date": item[6],
                            }
                        )
                except aiosqlite.OperationalError as e:
                    pass
    finally:
        await conn.close()

    return reminders
