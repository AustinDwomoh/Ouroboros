# ============================================================================ #
# MODULE: MovieManager.py

# ============================================================================ #

import aiohttp
from difflib import SequenceMatcher
import discord
from settings import MOVIE_BASE_URL, MOVIE_API_KEY, ErrorHandler
from rimiru import Rimiru
from models import Series, Movie,UserMedia
from constants import FetchType, MediaType

error_handler = ErrorHandler()



# ============================================================================ #
#                                   DB CALLS                                   #
# ============================================================================ #
async def add_or_update_user_movie(user_id: int, title: str, tmdb_id:int=None,watchlist: bool=False):
    """Insert or update a movie watch record for a user."""
   
    conn = await Rimiru.shion()
    try:
        # 1. Look up or insert movie into movies table
        media_data = await get_cached_media(MediaType.MOVIE.value, title)
        db_id = media_data.id if media_data else None
        print("Cached media data:", media_data)
        if media_data is None:
            media_data, db_id = await cache_media(MediaType.MOVIE.value, tmdb_id) 
        if media_data is None:
            raise ValueError("Failed to fetch or cache movie data.")
        # 2. Insert or update user_media record
        print(media_data)
        row = await conn.upsert("user_media", data={
            "user_id": user_id,
            "media_id": db_id,
            "status": "watchlist" if watchlist else "watched"
            }, conflict_column="user_id, media_id")
        if row:
            #the idea is if it actually inserted or updated we return the media data
            #so we can give feedback to the user with the title/poster etc
            return media_data
    except Exception as e:
        error_handler.handle(e, context=f"add_or_update_user_movie({title})")

async def add_or_update_user_series(user_id: int, title: str, season=None, episode=None, tmdb_id:int=None, watchlist: bool=False ):
    """Insert or update a movie watch record for a user."""
   
    conn = await Rimiru.shion()
    try:
        # 1. Look up or insert movie into movies table
        
        media_data = await get_cached_media(MediaType.SERIES.value, title)
        db_id = media_data.id if media_data else None
        print("Cached media data:", media_data)
        if media_data is None:
            media_data,id = await cache_media(MediaType.SERIES.value, tmdb_id)
            db_id = id
        if media_data is None:
            raise ValueError("Failed to fetch or cache movie data.")
        # 2. Insert or update user_media record
        row = await conn.upsert("user_media", data={
            "user_id": user_id,
            "media_id": db_id,
            "progress": {"season": season, "episode": episode} if season and episode else None,
            "status": "watchlist" if watchlist else "watching"
            }, conflict_column="user_id, media_id")
        if row:
            #the idea is if it actually inserted or updated we return the media data
            #so we can give feedback to the user with the title/poster etc
            return media_data
    except Exception as e:
        error_handler.handle(e, context=f"add_or_update_series({title})")
        return None
  
async def add_to_watchlist(user_id: int, title: str, media_type:str,tmdb_id:int=None):
    """Add a media entry to a user's watchlist."""
    conn = await Rimiru.shion()
    try:
        # 1. Look up or insert movie into movies table
        media_type = MediaType.find_media_type(media_type)
        media_data = await get_cached_media(media_type.value, title)
        if media_data is None:
            media_data = await cache_media(media_type.value, tmdb_id) 
        if media_data is None:
            raise ValueError("Failed to fetch or cache movie data.")
        row = await conn.upsert("user_media", 
                        data={"user_id": user_id, 
                            "media_id": media_data.id,
                            "status": "watchlist"},
                                conflict_column="user_id, media_id")
        if row:
            return media_data
    except Exception as e:
        error_handler.handle(e, context=f"add_to_watchlist({user_id}, {media_data.id})")
        return None


async def fetch_media_names():
    """Fetch all distinct media titles a user has interacted with."""
    conn = await Rimiru.shion()
    try:  
        rows = await conn.select("media", columns=["title","id","tmdb_id"], order_by="title ASC")
        return {r['title']: {"id": r["id"], "tmdb_id": r["tmdb_id"]} for r in rows}
    except Exception as e:
        error_handler.handle(e, context="fetch_media_names")
        return {}

async def get_watchlist(user_id: int,):
    """Fetch a user's watchlist entries.
    returns list of dicts with media details.
    """
    conn = await Rimiru.shion()
    try:
        
        rows = await conn.call_function(
            fn="get_user_watchlist", params=[user_id], fetch_type=FetchType.FETCH)
        return [dict(row) for row in rows]
    except Exception as e:
        error_handler.handle(e, context=f"get_watchlist({user_id})")
        return []

async def delete_user_media(user_id: int, media_id: int):
    """Delete a specific media entry from a user's records."""
    conn = await Rimiru.shion()
    try:
        await conn.delete("user_media", filters={"user_id": user_id, "media_id": media_id})
        return True
    except Exception as e:
        error_handler.handle(e, context=f"delete_user_media({user_id}, {media_id})")
        return False
    
# ============================================================================ #

async def fetch_user_media(user_id:int, media_id:int):
    """Fetch a specific media entry for a user by title and type."""
    conn = await Rimiru.shion()
    try:
        rows = await conn.call_function(fn="get_user_media_by_id", params=[user_id, media_id], fetch_type=FetchType.FETCH)

        if rows:
            return UserMedia.from_db(dict(rows[0]))
        return None
    except Exception as e:
        error_handler.handle(e, context=f"fetch_user_media({user_id}, {media_id})")
        return None

async def check_user_completion(user_id: int):
    """Check if a user has completed all media in their watchlist."""
    conn = await Rimiru.shion()
    try:
        rows = await conn.call_function(
            fn="get_user_incomplete_media", params=[user_id], fetch_type=FetchType.FETCH)
        return [UserMedia.from_db(dict(r)) for r in rows]

    except Exception as e:
        error_handler.handle(e, context=f"check_user_completion({user_id})")
        return None


# ============================================================================ #
#                                   API CALLS                                  #
# ============================================================================ #
def is_similar(a: str, b: str, threshold=0.7) -> bool:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= threshold


# ============================================================
# LOCAL ID CACHE - Check DB first before API
# ============================================================
async def get_cached_media(media_type: str, title: str):
    """
    Check if we already have this media stored locally.
    Returns (tmdb_id, local_db_id) if found, else None.
    """
    conn = await Rimiru.shion()
    try:
        table = MediaType.find_media_type(media_type).table_name
        print(f"Looking for cached media: {media_type} - {title}, table: {table}")
        if not table:
            return None
        if table == "movies":
            fn = "get_movie_by_title"
        else:
            fn = "get_series_by_title"
        row = await conn.call_function(fn=fn, params=[title], fetch_type=FetchType.FETCHROW)

        if not row:
            return None
        row = row[0]
        return Series.from_db(row) if media_type == "tv" else Movie.from_db(row)
    except Exception as e:
        error_handler.handle(e, context="get_cached_media")
        return None


async def cache_media(media_type: str,tmdb_id: str):
    """
    When this is called it means this is a new entry we don't have cached yet.
    Fetch from TMDB and store in local DB.
    Since this is called after a search the multi, we assume the tmdb_id is valid.
    ALso returns the media data fetched.
    The multi-search function should ensure the ID is valid before calling this.
    Args:
        media_type: 'movie' or 'tv'
        tmdb_id: TMDB ID to fetch and cache
    """
    conn = await Rimiru.shion()
    try:
        media_type = MediaType.find_media_type(media_type)
        table = media_type.table_name

        media_data = await get_media_details(media_type.value, tmdb_id)
        row = await conn.upsert("media", data=media_data.to_media_dict(), conflict_column="tmdb_id")
        print(row)
        insert_data = media_data.to_db_dict()
        insert_data["id"] = row["id"]
        print("Insert data for specific table:", insert_data)
        await conn.upsert(f"{table}", data=insert_data, conflict_column="id")
        
        print("Cached media:", media_data.title)
        return media_data, row["id"]
    except Exception as e:
        error_handler.handle(e, context="cache_media")

async def search_media_multiple(media_type: str, name: str):
    """
    Search TMDB and return multiple results for user to choose from.
    
    Returns:
        List of dicts: [{id, title, year, poster_url, overview, similarity_score}, ...]
    """
    url = f"{MOVIE_BASE_URL}/search/{media_type}?query={name.replace(' ', '+')}&api_key={MOVIE_API_KEY}"
    print(url)
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as r:
            data = await r.json()
    
    results = []
    for result in data.get("results", []):
        title = result.get("name") or result.get("title", "Unknown")
        year = None
        
        if media_type == "movie" and result.get("release_date"):
            year = result["release_date"][:4]
        elif media_type == "tv" and result.get("first_air_date"):
            year = result["first_air_date"][:4]
        
        poster_path = result.get("poster_path")
        poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
        
        # Calculate similarity for sorting
        similarity = is_similar(title, name, threshold=0.0)
        
        results.append({
            "id": result["id"],
            "title": title,
            "year": year,
            "poster_url": poster_url,
            "overview": result.get("overview", "No description available."),
            "similarity_score": similarity
        })
    
    # Sort by similarity score (highest first)
    results.sort(key=lambda x: x["similarity_score"], reverse=True)
    
    return results


async def get_media_details(media_type: str, media_id: str = None):
    """
    Fetch media metadata from TMDB.
    
    Args:
        media_type: 'movie' or 'tv'
        media_id: Direct TMDB ID to fetch (skips search)
    
    Returns:
        Dict with media details or empty dict if not found
    """
        
    if not media_id:
        return {}

    async with aiohttp.ClientSession() as session:
        url = f"{MOVIE_BASE_URL}/{media_type}/{media_id}?api_key={MOVIE_API_KEY}&append_to_response=watch/providers"
        print(url)
        async with session.get(url) as resp:
            data = await resp.json()

    if data.get("status_code") == 34:
        return {}
    
    if not data.get("title") and not data.get("name"):
        return {}

    return Series.from_api(data) if media_type == "tv" else Movie.from_api(data)




# ============================================================================ #
#                               BACKGROUND TASKS                               #
# ============================================================================ #

import asyncio
from datetime import datetime, timezone
from typing import List
from asyncio import Semaphore

async def send_reminder_to_user(client, user_id: int, reminders: List[Series], semaphore: Semaphore):
    """Send episode reminders to a single user with rate limiting"""
    async with semaphore:  # Limit concurrent sends
        try:
            user = await client.fetch_user(user_id)
            if not user:
                print(f"[REMINDERS] User {user_id} not found")
                return
            
            # Send header embed
            header_embed = discord.Embed(
                title="📺 Upcoming Episodes This Week",
                description=f"You have **{len(reminders)}** show(s) with new episodes coming up!",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            await user.send(embed=header_embed)
            await asyncio.sleep(0.5)
            
            # Send individual show embeds
            for user_show in reminders:
                embed_data = discord.Embed(
                    title=user_show.title,
                    description=user_show.next_release_info,  # FIXED
                    color=discord.Color.purple()
                )
                if user_show.poster_url:
                    embed_data.set_thumbnail(url=user_show.poster_url)
                
                await user.send(embed=embed_data)
                await asyncio.sleep(0.5)  # Rate limit between messages
                
        except discord.Forbidden:
            print(f"[REMINDERS] Cannot send DM to user {user_id} (DMs disabled)")
        except discord.HTTPException as e:
            print(f"[REMINDERS] Discord API error for user {user_id}: {e}")
        except Exception as e:
            error_handler.handle(e, context=f"send_reminder_to_{user_id}")


async def send_incomplete_reminder_to_user(client, user_id: int, incomplete: list[UserMedia], semaphore: Semaphore):
    """Send incomplete media reminders to a single user"""
    async with semaphore:
        try:
            user = await client.fetch_user(user_id)
            if not user:
                print(f"[REMINDERS] User {user_id} not found")
                return
            
            # Send header message
            header_embed = discord.Embed(
                title="📚 Your Incomplete Media",
                description=f"You have **{len(incomplete)}** item(s) to catch up on",
                color=discord.Color.orange(),
                timestamp=datetime.now(timezone.utc)
            )
            await user.send(embed=header_embed)
            await asyncio.sleep(0.5)

            # Send individual embed for each media
            for media in incomplete:
                embed_data = media.to_embed_dict() 
                embed = discord.Embed(
                    title=embed_data["title"],          
                    description=embed_data["description"],
                    color=embed_data["color"]             
                )

                if embed_data.get("thumbnail"):
                    embed.set_thumbnail(url=embed_data["thumbnail"])

                for field in embed_data["fields"]:
                    embed.add_field(
                        name=field["name"],
                        value=field["value"],
                        inline=field.get("inline", False)
                    )

                await user.send(embed=embed)  
                await asyncio.sleep(0.5)
            
            # Send footer message
            footer_embed = discord.Embed(
                description="✅ All incomplete media listed above!",
                color=discord.Color.green()
            )
            await user.send(embed=footer_embed)

        except discord.Forbidden:
            print(f"[REMINDERS] Cannot send DM to user {user_id}")
        except discord.HTTPException as e:
            print(f"[REMINDERS] Discord API error for user {user_id}: {e}")
        except Exception as e:
            error_handler.handle(e, context=f"send_incomplete_reminder_{user_id}")


async def send_upcoming_episode_reminders(client):
    """Send reminders to users about upcoming episodes - PARALLEL VERSION"""
    conn = await Rimiru.shion()
    
    try:
        # Get all users with active media
        rows = await conn.select(
            table="user_media",
            columns=["DISTINCT user_id"],
            raw_where="status IN ('watchlist','watching')"
        )
        
        if not rows:
            print("[REMINDERS] No users to check")
            return
        
        # Fetch reminders for all users
        user_reminders = []
        for row in rows:
            user_id = row["user_id"]
            try:
                reminders = await conn.call_function(
                    fn="get_user_upcoming_episodes",
                    params=[user_id, 7],
                    fetch_type=FetchType.FETCH
                )
                reminders = [Series.from_db(dict(r)) for r in reminders]
                
                if reminders:
                    user_reminders.append((user_id, reminders))
            except Exception as e:
                error_handler.handle(e, context=f"fetch_reminders_{user_id}")
                continue  # FIXED: Continue instead of return
        
        if not user_reminders:
            print("[REMINDERS] No upcoming episodes to notify about")
            return
        
        print(f"[REMINDERS] Sending notifications to {len(user_reminders)} users")
        
        # Create semaphore to limit concurrent sends (avoid rate limits)
        semaphore = Semaphore(3)  # Max 3 users being notified simultaneously
        
        # Send reminders in parallel
        tasks = [
            send_reminder_to_user(client, user_id, reminders, semaphore)
            for user_id, reminders in user_reminders
        ]
        
        await asyncio.gather(*tasks, return_exceptions=True)
        print(f"[REMINDERS] Finished sending episode reminders")
        
    except Exception as e:
        error_handler.handle(e, context="send_upcoming_episode_reminders")

async def send_incomplete_media_reminders(client):
    """Send reminders about incomplete media - PARALLEL VERSION"""
    conn = await Rimiru.shion()

    try:
        # Get all users who have incomplete media
        rows = await conn.select(
            table="user_media",
            columns=["DISTINCT user_id"],
            raw_where="status IN ('watchlist','watching')"
        )
        
        if not rows:
            print("[REMINDERS] No users to check for incomplete media")
            return
        
        # Fetch incomplete media for all users
        user_incomplete = []
        for row in rows:
            user_id = row["user_id"]
            try:
                incomplete = await check_user_completion(user_id)
                if incomplete:
                    user_incomplete.append((user_id, incomplete))
            except Exception as e:
                error_handler.handle(e, context=f"check_completion_{user_id}")
                continue
        
        if not user_incomplete:
            print("[REMINDERS] No incomplete media to notify about")
            return
        
        print(f"[REMINDERS] Sending incomplete media notifications to {len(user_incomplete)} users")
        
        # Create semaphore to limit concurrent sends
        semaphore = Semaphore(3)  # Max 3 users simultaneously
        
        # Send reminders in parallel
        tasks = [
            send_incomplete_reminder_to_user(client, user_id, incomplete, semaphore)
            for user_id, incomplete in user_incomplete
        ]
        
        await asyncio.gather(*tasks, return_exceptions=True)
        print(f"[REMINDERS] Finished sending incomplete media reminders")
        
        await asyncio.sleep(1209600)  # Wait 2 weeks before next run
        
    except Exception as e:
        error_handler.handle(e, context="send_incomplete_media_reminders")


async def update_series_details(series_id: int, tmdb_id: int):
    """Update a single series with latest data from TMDB."""
    conn = await Rimiru.shion()
    try:
        # Fetch latest data from TMDB
        media_data = await get_media_details(MediaType.SERIES.value, tmdb_id)
        if not media_data:
            return False
        
        # Update media table
        await conn.update("media", 
                         data=media_data.to_media_dict(), 
                         filters={"id": series_id})
        
        # Update series_details table
        update_data = media_data.to_db_dict()
        await conn.update("series", 
                         data=update_data, 
                         filters={"id": series_id})
        
        return True
    except Exception as e:
        error_handler.handle(e, context=f"update_series_details({series_id})")
        return False


async def update_movie_details(movie_id: int, tmdb_id: int):
    """Update a single movie with latest data from TMDB."""
    conn = await Rimiru.shion()
    try:
        # Fetch latest data from TMDB
        media_data = await get_media_details(MediaType.MOVIE.value, tmdb_id)
        if not media_data:
            return False
        
        # Update media table
        await conn.update("media", 
                         data=media_data.to_media_dict(), 
                         filters={"id": movie_id})
        
        # Update movies_details table
        update_data = media_data.to_db_dict()
        await conn.update("movies", 
                         data=update_data, 
                         filters={"id": movie_id})
        
        return True
    except Exception as e:
        error_handler.handle(e, context=f"update_movie_details({movie_id})")
        return False


async def get_series_needing_update():
    """Get series that need updating based on their status and last update."""
    conn = await Rimiru.shion()
    try:
        rows = await conn.call_function(
            fn="get_series_needing_update", 
            fetch_type=FetchType.FETCH
        )
        return [{"id": r["id"], "tmdb_id": r["tmdb_id"]} for r in rows]
    except Exception as e:
        error_handler.handle(e, context="get_series_needing_update")
        return []


async def get_movies_needing_update():
    """Get movies that need updating (much less frequent than series)."""
    conn = await Rimiru.shion()
    try:
        rows = await conn.call_function(
            fn="get_movies_needing_update",  
            fetch_type=FetchType.FETCH
        )
        return [{"id": r["id"], "tmdb_id": r["tmdb_id"]} for r in rows]
    except Exception as e:
        error_handler.handle(e, context="get_movies_needing_update")
        return []

async def series_background_updater():
    """Background task to periodically update series data."""
    print("[UPDATER] Series background updater started")
    
    while True:
        try:
            # Get series that need updating
            series_list = await get_series_needing_update()
            
            if series_list:
                print(f"[UPDATER] Updating {len(series_list)} series...")
                
                updated_count = 0
                failed_count = 0
                
                for series in series_list:
                    success = await update_series_details(series["id"], series["tmdb_id"])
                    if success:
                        updated_count += 1
                    else:
                        failed_count += 1
                    await asyncio.sleep(0.5)  # Rate limit
                
                print(f"[UPDATER] Series update complete: {updated_count} updated, {failed_count} failed")
            else:
                print("[UPDATER] No series need updating at this time")
            
            # Wait 1 hour before next check
            await asyncio.sleep(3600)
            
        except Exception as e:
            error_handler.handle(e, context="series_background_updater")
            # Wait 5 minutes before retrying after error
            await asyncio.sleep(300)

async def movie_background_updater():
    """Background task to periodically update movie data (less frequent than series)."""
    print("[UPDATER] Movie background updater started")
    
    while True:
        try:
            # Get movies that need updating
            movies_list = await get_movies_needing_update()
            
            if movies_list:
                print(f"[UPDATER] Updating {len(movies_list)} movies...")
                
                updated_count = 0
                failed_count = 0
                
                for movie in movies_list:
                    success = await update_movie_details(movie["id"], movie["tmdb_id"])
                    if success:
                        updated_count += 1
                    else:
                        failed_count += 1
                    
                    # Rate limiting
                    await asyncio.sleep(0.5)
                
                print(f"[UPDATER] Movie update complete: {updated_count} updated, {failed_count} failed")
            else:
                print("[UPDATER] No movies need updating at this time")
            
            # Wait 12 hours before next check (movies change less frequently)
            await asyncio.sleep(43200)
            
        except Exception as e:
            error_handler.handle(e, context="movie_background_updater")
            # Wait 5 minutes before retrying after error
            await asyncio.sleep(300)

async def start_background_updaters(client):
    """Start all background updater tasks."""
    tasks = [
        asyncio.create_task(series_background_updater()),
        asyncio.create_task(movie_background_updater()),
        asyncio.create_task(send_incomplete_media_reminders(client)),
        asyncio.create_task(send_upcoming_episode_reminders(client))
    ]
    await asyncio.gather(*tasks)