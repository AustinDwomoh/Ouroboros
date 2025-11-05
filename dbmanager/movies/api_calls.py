# services/media_service.py
import aiohttp
from difflib import SequenceMatcher
from bs4 import BeautifulSoup
from settings import MOVIE_BASE_URL, MOVIE_API_KEY, HIANIME_BASE_URL, ErrorHandler

# services/anime_service.py

error_handler = ErrorHandler()


def is_similar(a: str, b: str, threshold=0.7) -> bool:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= threshold


# thinking of storing media IDs locally to reduce API calls
# it should help with better calling for names that are similar
async def search_media_id(media, name):
    url = f"{MOVIE_BASE_URL}/search/{media}?query={name.replace(' ', '+')}&api_key={MOVIE_API_KEY}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as r:
            data = await r.json()
    for result in data.get("results", []):
        title = result.get("name") or result.get("title")
        if title and is_similar(title, name):
            return result["id"]
    return None


async def get_media_details(media, name):
    """Fetch media metadata from TMDB."""
    media_id = await search_media_id(media, name)
    if not media_id:
        return {}

    async with aiohttp.ClientSession() as session:
        url = f"{MOVIE_BASE_URL}/{media}/{media_id}?api_key={MOVIE_API_KEY}&append_to_response=watch/providers"
        async with session.get(url) as resp:
            data = await resp.json()

    if data.get("status_code") == 34:
        return {}

    return parse_tv(data) if media == "tv" else parse_movie(data)


def parse_tv(data):
    return {
        "title": data.get("name"),
        "overview": data.get("overview"),
        "genres": [g["name"] for g in data.get("genres", [])],
        "release_date": data.get("first_air_date"),
        "release_date": data.get("first_air_date"),
        "last_air_date": data.get("last_air_date"),
        "next_episode_date": (
            data.get("next_episode_to_air", {}).get("air_date")
            if data.get("next_episode_to_air")
            else None
        ),
        "next_episode_number": (
            data.get("next_episode_to_air", {}).get("episode_number")
            if data.get("next_episode_to_air")
            else None
        ),
        "next_season_number": (
            data.get("next_episode_to_air", {}).get("season_number")
            if data.get("next_episode_to_air")
            else None
        ),
        "seasons": [
            {
                "season_number": season.get("season_number"),
                "episode_count": season.get("episode_count"),
            }
            for season in data.get("seasons", [])
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
            f"https://image.tmdb.org/t/p/w500{data['poster_path']}"
            if data.get("poster_path")
            else None
        ),
        "homepage": data.get("homepage"),
        "status": data.get("status"),
    }


def parse_movie(data):
    collection = data.get("belongs_to_collection") or {}
    return {
        "title": data.get("title"),
        "overview": data.get("overview"),
        "genres": [g["name"] for g in data.get("genres", [])],
        "release_date": data.get("release_date"),
        "poster_url": (
            f"https://image.tmdb.org/t/p/w500{data['poster_path']}"
            if data.get("poster_path")
            else None
        ),
        "status": data.get("status"),
        "homepage": data.get("homepage"),
        "in_collection": (
            [
                {
                    "id": collection.get("id"),
                    "name": collection.get("name"),
                    "poster_path": (
                        f"https://image.tmdb.org/t/p/w500{collection['poster_path']}"
                        if collection.get("poster_path")
                        else None
                    ),
                    "backdrop_path": (
                        f"https://image.tmdb.org/t/p/w500{collection['backdrop_path']}"
                        if collection.get("backdrop_path")
                        else None
                    ),
                }
            ]
            if collection
            else []
        ),
    }


async def search_hianime(keyword: str):
    """Scrape Hianime search results."""
    url = f"{HIANIME_BASE_URL}/search?keyword={keyword}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as r:
            if r.status != 200:
                return {"error": "Failed to fetch data"}
            html = await r.text()

    soup = BeautifulSoup(html, "html.parser")
    results = []
    for item in soup.select(".film_list-wrap .flw-item"):
        title_tag = item.select_one(".dynamic-name")
        link_tag = item.select_one("a")
        img_tag = item.select_one("img")
        if title_tag and link_tag and img_tag:
            results.append(
                {
                    "title": title_tag.text.strip(),
                    "link": HIANIME_BASE_URL + link_tag["href"],
                    "thumbnail": img_tag.get("data-src") or img_tag.get("src"),
                }
            )
    return results
