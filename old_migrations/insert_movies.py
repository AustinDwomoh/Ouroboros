#!/usr/bin/env python3
"""
Script to insert media data from JSON file into the database.
Handles movies, series, and watchlist items.
"""

import asyncio
import json
from pathlib import Path
from dbmanager.MovieManager import (
    add_or_update_user_movie,
    add_or_update_user_series,
    search_media_multiple,
    MediaType
)
from settings import ErrorHandler

error_handler = ErrorHandler()


async def find_best_match(media_type: str, title: str):
    """
    Search TMDB for the best match for a given title.
    Returns the TMDB ID of the best match or None if not found.
    """
    try:
        results = await search_media_multiple(media_type, title)
        if results:
            # Return the top result (highest similarity score)
            best_match = results[0]
            print(f"✓ Found match for '{title}': {best_match['title']} ({best_match['year']}) - ID: {best_match['id']}")
            return best_match['id']
        else:
            print(f"✗ No match found for '{title}'")
            return None
    except Exception as e:
        error_handler.handle(e, context=f"find_best_match({media_type}, {title})")
        return None


async def insert_movie(user_id: int, title: str, watchlist: bool = False):
    """Insert a movie into the database."""
    try:
        tmdb_id = await find_best_match(MediaType.MOVIE.value, title)
        if tmdb_id:
            result = await add_or_update_user_movie(
                user_id=user_id,
                title=title,
                tmdb_id=tmdb_id,
                watchlist=watchlist
            )
            if result:
                status = "watchlist" if watchlist else "watched"
                print(f"  → Added to {status}: {result.title}")
                return True
        return False
    except Exception as e:
        error_handler.handle(e, context=f"insert_movie({title})")
        return False


async def insert_series(user_id: int, title: str, season=None, episode=None, watchlist: bool = False):
    """Insert a series into the database."""
    try:
        tmdb_id = await find_best_match(MediaType.SERIES.value, title)
        if tmdb_id:
            result = await add_or_update_user_series(
                user_id=user_id,
                title=title,
                season=season,
                episode=episode,
                tmdb_id=tmdb_id,
                watchlist=watchlist
            )
            if result:
                if watchlist:
                    print(f"  → Added to watchlist: {result.title}")
                else:
                    print(f"  → Added: {result.title} (S{season}E{episode})")
                return True
        return False
    except Exception as e:
        error_handler.handle(e, context=f"insert_series({title})")
        return False


async def process_json_file(json_file_path: str, user_id: int):
    """
    Process the JSON file and insert all media items into the database.
    
    Args:
        json_file_path: Path to the JSON file
        user_id: Discord user ID to associate media with
    """
    try:
        # Load JSON data
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print(f"\n{'='*70}")
        print(f"Starting import for User ID: {user_id}")
        print(f"Total items to process: {len(data)}")
        print(f"{'='*70}\n")
        
        stats = {
            'movies_watched': 0,
            'series_watching': 0,
            'watchlist_movies': 0,
            'watchlist_series': 0,
            'failed': 0
        }
        
        for idx, item in enumerate(data, 1):
            item_type = item.get('type')
            title = item.get('title')
            
            print(f"\n[{idx}/{len(data)}] Processing: {title} ({item_type})")
            
            success = False
            
            if item_type == 'movie':
                success = await insert_movie(user_id, title, watchlist=False)
                if success:
                    stats['movies_watched'] += 1
                    
            elif item_type == 'series':
                season = item.get('season')
                episode = item.get('episode')
                success = await insert_series(user_id, title, season, episode, watchlist=False)
                if success:
                    stats['series_watching'] += 1
                    
            elif item_type == 'watchlist_movie':
                success = await insert_movie(user_id, title, watchlist=True)
                if success:
                    stats['watchlist_movies'] += 1
                    
            elif item_type == 'watchlist_series':
                success = await insert_series(user_id, title, watchlist=True)
                if success:
                    stats['watchlist_series'] += 1
            
            if not success:
                stats['failed'] += 1
                print(f"  ✗ Failed to process: {title}")
            
            # Rate limiting to avoid overwhelming TMDB API
            await asyncio.sleep(0.3)
        
        # Print summary
        print(f"\n{'='*70}")
        print("IMPORT SUMMARY")
        print(f"{'='*70}")
        print(f"Movies watched:        {stats['movies_watched']}")
        print(f"Series watching:       {stats['series_watching']}")
        print(f"Watchlist movies:      {stats['watchlist_movies']}")
        print(f"Watchlist series:      {stats['watchlist_series']}")
        print(f"Failed:                {stats['failed']}")
        print(f"Total successful:      {sum(stats.values()) - stats['failed']}")
        print(f"{'='*70}\n")
        
    except FileNotFoundError:
        print(f"Error: File not found: {json_file_path}")
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON format: {e}")
    except Exception as e:
        error_handler.handle(e, context="process_json_file")


async def main():
    """Main entry point for the script."""
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python insert_media_data.py <json_file_path> <user_id>")
        print("\nExample:")
        print("  python insert_media_data.py media_data.json 123456789")
        sys.exit(1)
    
    json_file_path = sys.argv[1]
    user_id = int(sys.argv[2])
    
    if not Path(json_file_path).exists():
        print(f"Error: File '{json_file_path}' does not exist")
        sys.exit(1)
    
    print(f"\nStarting media import...")
    print(f"File: {json_file_path}")
    print(f"User ID: {user_id}")
    
    await process_json_file(json_file_path, user_id)
    
    print("\nImport complete!")


if __name__ == "__main__":
    asyncio.run(main())