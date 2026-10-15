import os
import sys
import time
import asyncio
import secrets
import dataclasses
from datetime import date, datetime
from enum import Enum as StdEnum
from typing import Any, Literal, Optional
import httpx
import uvicorn
from pydantic import BaseModel
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, Security,Query
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests
from google.auth.exceptions import TransportError
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rimiru import Rimiru
from handle import handler
from constants import MediaType
from dbmanager.MovieManager import MovieManager
from dbmanager.SharedCollectionManager import sharedCollectionManager
from dbmanager import UserManager
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from fastapi.middleware.cors import CORSMiddleware


load_dotenv()

movieManager = MovieManager()
API_KEY = os.getenv("API_KEY")
# Comma-separated OAuth client IDs of the Expo app (web, iOS, Android); a token's `aud` must be one of them
GOOGLE_CLIENT_IDS = {c.strip() for c in os.getenv("GOOGLE_CLIENT_IDS", "").split(",") if c.strip()}
# The bot's Discord application, used for the app's "Link Discord" OAuth flow. Read directly (not the
# BOT_MODE-aware settings.CLIENT_ID) so the id always matches CLIENT_SECRET; any app sees the same user ids.
DISCORD_CLIENT_ID = os.getenv("CLIENT_ID")
DISCORD_CLIENT_SECRET = os.getenv("CLIENT_SECRET")
DISCORD_API = "https://discord.com/api/v10"


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)
_google_request = google_requests.Request()
# {id_token: claims} for already-verified tokens, so Google's certs aren't re-fetched on every call
_verified_tokens: dict[str, dict] = {}


@dataclasses.dataclass
class Caller:
    kind: Literal["bot", "app", "public"]
    google: dict | None = None  # verified Google ID token claims (app callers only)


def _verify_google_token(token: str) -> dict:
    """Blocking: checks signature, expiry and issuer, then that the audience is one of our app's client IDs."""
    claims = google_id_token.verify_oauth2_token(token, _google_request)
    if claims.get("aud") not in GOOGLE_CLIENT_IDS:
        raise ValueError("Token was not issued for this app")
    return claims


# Routes anyone may call without credentials. They must never return user data.
PUBLIC_PATHS = {"/api/live", "/api/media/recent"}


async def require_auth(
    request: Request,
    x_api_key: str | None = Security(api_key_header),
    bearer: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> Caller:
    """The bot authenticates with the shared X-API-Key; the app with a Google ID token (Authorization: Bearer)."""
    if request.url.path in PUBLIC_PATHS:
        return Caller(kind="public")
    if x_api_key:
        if not API_KEY:
            raise HTTPException(status_code=500, detail="API_KEY is not configured on the server")
        if not secrets.compare_digest(x_api_key, API_KEY):
            raise HTTPException(status_code=401, detail="Invalid X-API-Key header")
        return Caller(kind="bot")

    if not bearer:
        raise HTTPException(status_code=401, detail="Missing credentials")
    if not GOOGLE_CLIENT_IDS:
        raise HTTPException(status_code=500, detail="GOOGLE_CLIENT_IDS is not configured on the server")

    token = bearer.credentials
    claims = _verified_tokens.get(token)
    if claims is None or claims["exp"] <= time.time():
        try:
            claims = await asyncio.to_thread(_verify_google_token, token)
        except TransportError:
            raise HTTPException(status_code=503, detail="Could not reach Google to verify the token")
        except ValueError as e:
            raise HTTPException(status_code=401, detail=f"Invalid Google ID token: {e}")
        if len(_verified_tokens) > 1000:
            now = time.time()
            for stale in [t for t, c in _verified_tokens.items() if c["exp"] <= now]:
                del _verified_tokens[stale]
        _verified_tokens[token] = claims
    return Caller(kind="app", google=claims)


async def current_user_id(caller: Caller = Depends(require_auth)) -> int | None:
    """users.id of an app caller (from the token's `sub`); None for the bot, which acts on behalf of any user."""
    if caller.kind == "bot":
        return None
    user_id = await UserManager.find_by_google_sub(caller.google["sub"])  # type: ignore
    if user_id is None:
        raise HTTPException(status_code=403, detail="No account yet: call POST /api/auth/google first")
    return user_id


async def ensure_self(user_id: int, me: int | None = Depends(current_user_id)) -> None:
    """App callers may only touch their own /api/users/{user_id}/... routes."""
    if me is not None and user_id != me:
        raise HTTPException(status_code=403, detail="You can only access your own data")


def require_bot(caller: Caller = Depends(require_auth)) -> None:
    if caller.kind != "bot":
        raise HTTPException(status_code=403, detail="This endpoint is only available to the bot")


def acting_user(me: int | None, supplied: int | None, field: str) -> int:
    """Identity for body/query based routes: app callers are always themselves, the bot must say who it acts for."""
    if me is not None:
        return me
    if supplied is None:
        raise HTTPException(status_code=422, detail=f"`{field}` is required")
    return supplied


app = FastAPI(title="Ouroboros Media API", dependencies=[Depends(require_auth)])
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
    "https://cyan.austindwomoh.xyz",
    "http://localhost:8081",
    "http://localhost:4173",   # npm run preview:site
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
            data["poster_url"] = obj.poster_url # type: ignore
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
        return {k: to_json(v) for k, v in obj.items()} # type: ignore
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
class LinkDiscordBody(BaseModel):
    code: str
    code_verifier: str
    redirect_uri: str


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


# All user ids below are users.id. The acting-user fields (owner_id, inviter_id, user_id)
# are only read for the bot; for app callers they are ignored and taken from the Google token.
class CreateCollectionBody(BaseModel):
    owner_id: Optional[int] = None
    name: str
    collection_type: Literal["watchlist", "playlist"]


class InviteBody(BaseModel):
    inviter_id: Optional[int] = None
    invitee_id: int


class RespondInviteBody(BaseModel):
    user_id: Optional[int] = None
    accept: bool


class AddItemBody(BaseModel):
    user_id: Optional[int] = None
    media_id: int


class MarkWatchedBody(BaseModel):
    user_id: Optional[int] = None
    everyone: bool = False


# ============================================================================ #
#                                  MEDIA (TMDB)                                #
# ============================================================================ #
@app.get("/api/live")
async def live():
    return {"status": "ok"}


# ============================================================================ #
#                                     AUTH                                     #
# ============================================================================ #
@app.post("/api/auth/google")
async def auth_google(caller: Caller = Depends(require_auth)):
    """Exchange a verified Google ID token for the app's users.id, creating the user on first login."""
    if caller.kind != "app":
        raise HTTPException(status_code=400, detail="Send a Google ID token as Authorization: Bearer")
    claims = caller.google or {}
    email = claims.get("email")
    username = claims.get("name") or (email.split("@")[0] if email else None) or "user"
    user = await UserManager.get_or_create_google_user(claims["sub"], email, username)
    return {"user_id": user["id"], "username": user["username"], "discord_linked": user["discord_id"] is not None}


async def _discord_identity(body: LinkDiscordBody) -> dict:
    """Redeem the app's OAuth code (PKCE) for the Discord user it was issued to."""
    if not DISCORD_CLIENT_ID or not DISCORD_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="CLIENT_ID / CLIENT_SECRET are not configured on the server")
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            token = await http.post(
                f"{DISCORD_API}/oauth2/token",
                data={
                    "grant_type": "authorization_code",
                    "code": body.code,
                    "redirect_uri": body.redirect_uri,
                    "code_verifier": body.code_verifier,
                },
                auth=(DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET),
            )
            if token.status_code != 200:
                raise HTTPException(status_code=400, detail="Discord rejected the authorization code")
            me = await http.get(
                f"{DISCORD_API}/users/@me",
                headers={"Authorization": f"Bearer {token.json()['access_token']}"},
            )
            me.raise_for_status()
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Could not reach Discord")
    return me.json()


@app.post("/api/auth/discord/link")
async def link_discord(body: LinkDiscordBody, me: int | None = Depends(current_user_id)):
    """
    Link the caller's Discord account to their Google login. If the bot already knows that
    Discord user, the two accounts are merged and the returned user_id replaces the old one.
    """
    if me is None:
        raise HTTPException(status_code=400, detail="Send a Google ID token as Authorization: Bearer")
    discord_user = await _discord_identity(body)
    try:
        user = await UserManager.link_discord(me, int(discord_user["id"]))
    except UserManager.LinkConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        handler.error_handle(e, context="media api: link discord")
        raise HTTPException(status_code=500, detail="Internal server error")
    return {"user_id": user["id"], "username": user["username"], "discord_linked": True}


# Public: the login screen's slideshow. Titles and posters only, cached so it can't hammer the DB.
_recent_cache: tuple[float, list[dict]] = (0.0, [])


@app.get("/api/media/recent")
async def recent_media():
    global _recent_cache
    cached_at, items = _recent_cache
    if time.time() - cached_at > 300:
        items = await movieManager.fetch_recent_media(limit=10)
        _recent_cache = (time.time(), items)
    return items


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


@app.post("/api/media/refresh", dependencies=[Depends(require_bot)])
async def refresh_media():
    """Run the TMDB series + movie background updaters once."""
    await movieManager.series_background_updater()
    await movieManager.movie_background_updater()
    return {"status": "ok"}


# ============================================================================ #
#                                USER MEDIA                                    #
# ============================================================================ #
# Every /api/users/{user_id}/... route carries `dependencies=[Depends(ensure_self)]`.
@app.post("/api/users/{user_id}/movies", dependencies=[Depends(ensure_self)])
async def add_movie(user_id: int, body: AddMovieBody):
    media = await movieManager.add_or_update_user_movie(user_id, body.title, body.tmdb_id, body.watchlist)
    if not media:
        raise HTTPException(status_code=400, detail="Failed to add movie")
    return to_json(media)


@app.post("/api/users/{user_id}/series", dependencies=[Depends(ensure_self)])
async def add_series(user_id: int, body: AddSeriesBody):
    media = await movieManager.add_or_update_user_series(
        user_id, body.title, body.season, body.episode, body.tmdb_id, body.watchlist
    )
    if not media:
        raise HTTPException(status_code=400, detail="Failed to add series")
    return to_json(media)


@app.post("/api/users/{user_id}/watchlist", dependencies=[Depends(ensure_self)])
async def add_to_watchlist(user_id: int, body: AddWatchlistBody):
    mt = parse_media_type(body.media_type)
    media = await movieManager.add_to_watchlist(user_id, body.title, mt.value, body.tmdb_id)
    if not media:
        raise HTTPException(status_code=400, detail="Failed to add to watchlist")
    return to_json(media)


@app.get("/api/users/{user_id}/watchlist", dependencies=[Depends(ensure_self)])
async def get_watchlist(user_id: int):
    return to_json(await movieManager.get_watchlist(user_id))


@app.get("/api/users/{user_id}/history", dependencies=[Depends(ensure_self)])
async def get_history(user_id: int):
    return to_json(await movieManager.get_user_watch_history(user_id) or [])


@app.get("/api/users/{user_id}/incomplete", dependencies=[Depends(ensure_self)])
async def get_incomplete(user_id: int):
    return to_json(await movieManager.check_user_completion(user_id) or [])


@app.get("/api/users/{user_id}/upcoming", dependencies=[Depends(ensure_self)])
async def get_upcoming(user_id: int):
    return to_json(await movieManager.upcoming_reminders(user_id) or [])


@app.get("/api/users/{user_id}/media/{media_id}", dependencies=[Depends(ensure_self)])
async def get_user_media(user_id: int, media_id: int):
    media = await movieManager.fetch_user_media(user_id, {"id": media_id})
    if not media:
        raise HTTPException(status_code=404, detail="Media not found for this user")
    return to_json(media)


@app.delete("/api/users/{user_id}/media/{media_id}", dependencies=[Depends(ensure_self)])
async def delete_user_media(user_id: int, media_id: int):
    if not await movieManager.delete_user_media(user_id, media_id):
        raise HTTPException(status_code=500, detail="Failed to delete media")
    return {"status": "deleted"}


# ============================================================================ #
#                              SHARED COLLECTIONS                              #
# ============================================================================ #
@app.get("/api/users/{user_id}/collections", dependencies=[Depends(ensure_self)])
async def get_user_collections(user_id: int):
    return to_json(await run_shared(sharedCollectionManager.get_user_collections(user_id)))


@app.post("/api/collections")
async def create_collection(body: CreateCollectionBody, me: int | None = Depends(current_user_id)):
    owner_id = acting_user(me, body.owner_id, "owner_id")
    return to_json(await run_shared(
        sharedCollectionManager.create_collection(owner_id, body.name, body.collection_type)
    ))


@app.get("/api/collections/lookup")
async def lookup_collection(name: str, user_id: Optional[int] = None, me: int | None = Depends(current_user_id)):
    user_id = acting_user(me, user_id, "user_id")
    collection_id = await run_shared(sharedCollectionManager.get_collection_id(user_id, name))
    if collection_id is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    return {"id": collection_id}


@app.get("/api/collections/{collection_id}")
async def get_collection(collection_id: int, user_id: Optional[int] = None, me: int | None = Depends(current_user_id)):
    user_id = acting_user(me, user_id, "user_id")
    collection = await run_shared(sharedCollectionManager.get_collection(collection_id, user_id))
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found or you are not a member")
    return to_json(collection)


@app.post("/api/collections/{collection_id}/invites")
async def invite(collection_id: int, body: InviteBody, me: int | None = Depends(current_user_id)):
    inviter_id = acting_user(me, body.inviter_id, "inviter_id")
    return to_json(await run_shared(
        sharedCollectionManager.invite(collection_id, inviter_id, body.invitee_id)
    ))


@app.get("/api/users/{user_id}/invites", dependencies=[Depends(ensure_self)])
async def get_pending_invites(user_id: int):
    """Pending invites for the app's notification / inbox view."""
    return to_json(await run_shared(sharedCollectionManager.get_pending_invites(user_id)))


@app.post("/api/invites/{invite_id}/respond")
async def respond_to_invite(invite_id: int, body: RespondInviteBody, me: int | None = Depends(current_user_id)):
    user_id = acting_user(me, body.user_id, "user_id")
    return to_json(await run_shared(
        sharedCollectionManager.respond_to_invite(invite_id, user_id, body.accept)
    ))


@app.post("/api/collections/{collection_id}/items")
async def add_item(collection_id: int, body: AddItemBody, me: int | None = Depends(current_user_id)):
    user_id = acting_user(me, body.user_id, "user_id")
    return to_json(await run_shared(
        sharedCollectionManager.add_item(collection_id, user_id, body.media_id)
    ))


@app.post("/api/collections/{collection_id}/items/{media_id}/watched")
async def mark_watched(collection_id: int, media_id: int, body: MarkWatchedBody, me: int | None = Depends(current_user_id)):
    user_id = acting_user(me, body.user_id, "user_id")
    return to_json(await run_shared(
        sharedCollectionManager.mark_watched(collection_id, media_id, user_id, body.everyone)
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
