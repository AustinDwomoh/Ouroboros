import os
import sys
import secrets
import dataclasses
from datetime import date, datetime
from enum import Enum as StdEnum
from typing import Any, Literal, Optional
import uvicorn
from pydantic import BaseModel
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Security,Query
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rimiru import Rimiru
from handle import handler
from constants import MediaType
from dbmanager.MovieManager import MovieManager
from dbmanager.SharedCollectionManager import sharedCollectionManager
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware


load_dotenv()

movieManager = MovieManager()
API_KEY = os.getenv("API_KEY")



api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(x_api_key: str | None = Security(api_key_header)):
    """Every endpoint acts on arbitrary Discord user IDs, so gate the whole API behind a shared key."""
    if not API_KEY:
        raise HTTPException(status_code=500, detail="OUROBOROS_API_KEY is not configured on the server")
    if not x_api_key or not secrets.compare_digest(x_api_key, API_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key header")


app = FastAPI(title="Ouroboros Media API", dependencies=[Depends(require_api_key)])
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8081",   # Expo web dev server
        "http://127.0.0.1:8081",
    ],
    allow_methods=["*"],
    allow_headers=["*"],           # must cover X-API-Key and Content-Type
    allow_credentials=False,
)

@app.on_event("startup")
async def startup():
    global connect_db
    connect_db = await Rimiru.shion()


@app.on_event("shutdown")
async def shutdown():
    if connect_db:
        await connect_db.pool.close()


# ============================================================================ #
#                                    HELPERS                                   #
# ============================================================================ #
def to_json(obj: Any) -> Any:
    """Convert models (dataclasses, discord Enums, dates, asyncpg records) into JSON-safe data."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        data = {f.name: to_json(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
        if hasattr(obj, "poster_url"):
            data["poster_url"] = obj.poster_url
        return data
    if isinstance(obj, MediaType):
        return obj.value
    if isinstance(obj, StdEnum):
        return obj.value
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: to_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_json(v) for v in obj]
    if hasattr(obj, "items"):  # asyncpg.Record
        return {k: to_json(v) for k, v in obj.items()}
    return str(obj)


def parse_media_type(media_type: str) -> MediaType:
    try:
        return MediaType.find_media_type(media_type)  # type: ignore
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


async def run_shared(coro):
    """Map SharedCollectionManager's exceptions onto HTTP status codes."""
    try:
        return await coro
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        handler.error_handle(e, context="media api: shared collection")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================ #
#                                 REQUEST BODIES                               #
# ============================================================================ #
class AddMovieBody(BaseModel):
    title: str
    tmdb_id: Optional[int] = None
    watchlist: bool = False


class AddSeriesBody(BaseModel):
    title: str
    tmdb_id: int = 0
    season: Optional[int] = None
    episode: Optional[int] = None
    watchlist: bool = False


class AddWatchlistBody(BaseModel):
    title: str
    media_type: str
    tmdb_id: Optional[int] = None


class CreateCollectionBody(BaseModel):
    owner_id: int
    name: str
    collection_type: Literal["watchlist", "playlist"]


class InviteBody(BaseModel):
    inviter_id: int
    invitee_id: int


class RespondInviteBody(BaseModel):
    user_id: int
    accept: bool


class AddItemBody(BaseModel):
    user_id: int
    media_id: int


class MarkWatchedBody(BaseModel):
    user_id: int
    everyone: bool = False


# ============================================================================ #
#                                  MEDIA (TMDB)                                #
# ============================================================================ #
@app.get("/api/live")
async def live():
    return {"status": "ok"}


@app.get("/api/media/search")
async def search_media(q: str = Query(..., min_length=1), media_type: str = "movie"):
    mt = parse_media_type(media_type)
    return await movieManager.search_media_multiple(mt.value, q)


@app.get("/api/media/names")
async def media_names():
    return await movieManager.fetch_media_names()


@app.get("/api/media/{media_type}/{tmdb_id}")
async def media_details(media_type: str, tmdb_id: int):
    mt = parse_media_type(media_type)
    media = await movieManager.get_media_details(mt.value, tmdb_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found on TMDB")
    return to_json(media)


@app.post("/api/media/refresh")
async def refresh_media():
    """Run the TMDB series + movie background updaters once."""
    await movieManager.series_background_updater()
    await movieManager.movie_background_updater()
    return {"status": "ok"}


# ============================================================================ #
#                                USER MEDIA                                    #
# ============================================================================ #
@app.post("/api/users/{user_id}/movies")
async def add_movie(user_id: int, body: AddMovieBody):
    media = await movieManager.add_or_update_user_movie(user_id, body.title, body.tmdb_id, body.watchlist)
    if not media:
        raise HTTPException(status_code=400, detail="Failed to add movie")
    return to_json(media)


@app.post("/api/users/{user_id}/series")
async def add_series(user_id: int, body: AddSeriesBody):
    media = await movieManager.add_or_update_user_series(
        user_id, body.title, body.season, body.episode, body.tmdb_id, body.watchlist
    )
    if not media:
        raise HTTPException(status_code=400, detail="Failed to add series")
    return to_json(media)


@app.post("/api/users/{user_id}/watchlist")
async def add_to_watchlist(user_id: int, body: AddWatchlistBody):
    mt = parse_media_type(body.media_type)
    media = await movieManager.add_to_watchlist(user_id, body.title, mt.value, body.tmdb_id)
    if not media:
        raise HTTPException(status_code=400, detail="Failed to add to watchlist")
    return to_json(media)


@app.get("/api/users/{user_id}/watchlist")
async def get_watchlist(user_id: int):
    return to_json(await movieManager.get_watchlist(user_id))


@app.get("/api/users/{user_id}/history")
async def get_history(user_id: int):
    return to_json(await movieManager.get_user_watch_history(user_id) or [])


@app.get("/api/users/{user_id}/incomplete")
async def get_incomplete(user_id: int):
    return to_json(await movieManager.check_user_completion(user_id) or [])


@app.get("/api/users/{user_id}/upcoming")
async def get_upcoming(user_id: int):
    return to_json(await movieManager.upcoming_reminders(user_id) or [])


@app.get("/api/users/{user_id}/media/{media_id}")
async def get_user_media(user_id: int, media_id: int):
    media = await movieManager.fetch_user_media(user_id, {"id": media_id})
    if not media:
        raise HTTPException(status_code=404, detail="Media not found for this user")
    return to_json(media)


@app.delete("/api/users/{user_id}/media/{media_id}")
async def delete_user_media(user_id: int, media_id: int):
    if not await movieManager.delete_user_media(user_id, media_id):
        raise HTTPException(status_code=500, detail="Failed to delete media")
    return {"status": "deleted"}


# ============================================================================ #
#                              SHARED COLLECTIONS                              #
# ============================================================================ #
@app.get("/api/users/{user_id}/collections")
async def get_user_collections(user_id: int):
    return to_json(await run_shared(sharedCollectionManager.get_user_collections(user_id)))


@app.post("/api/collections")
async def create_collection(body: CreateCollectionBody):
    return to_json(await run_shared(
        sharedCollectionManager.create_collection(body.owner_id, body.name, body.collection_type)
    ))


@app.get("/api/collections/lookup")
async def lookup_collection(user_id: int, name: str):
    collection_id = await run_shared(sharedCollectionManager.get_collection_id(user_id, name))
    if collection_id is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    return {"id": collection_id}


@app.get("/api/collections/{collection_id}")
async def get_collection(collection_id: int, user_id: int):
    collection = await run_shared(sharedCollectionManager.get_collection(collection_id, user_id))
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found or you are not a member")
    return to_json(collection)


@app.post("/api/collections/{collection_id}/invites")
async def invite(collection_id: int, body: InviteBody):
    return to_json(await run_shared(
        sharedCollectionManager.invite(collection_id, body.inviter_id, body.invitee_id)
    ))


@app.post("/api/invites/{invite_id}/respond")
async def respond_to_invite(invite_id: int, body: RespondInviteBody):
    return to_json(await run_shared(
        sharedCollectionManager.respond_to_invite(invite_id, body.user_id, body.accept)
    ))


@app.post("/api/collections/{collection_id}/items")
async def add_item(collection_id: int, body: AddItemBody):
    return to_json(await run_shared(
        sharedCollectionManager.add_item(collection_id, body.user_id, body.media_id)
    ))


@app.post("/api/collections/{collection_id}/items/{media_id}/watched")
async def mark_watched(collection_id: int, media_id: int, body: MarkWatchedBody):
    return to_json(await run_shared(
        sharedCollectionManager.mark_watched(collection_id, media_id, body.user_id, body.everyone)
    ))


if __name__ == "__main__":
    # Bound to localhost; nginx terminates TLS for the public domain and proxies here.
    uvicorn.run(
        app,
        host=os.getenv("API_HOST", "127.0.0.1"),
        port=int(os.getenv("API_PORT", "8000")),
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1",
    )
