import os
import sys
import time
import asyncio
import secrets
import dataclasses
import json
import csv
import io
import re
from datetime import date, datetime
from enum import Enum as StdEnum
from typing import Any, Literal, Optional
import httpx
import uvicorn
from pydantic import BaseModel
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, Security,Query
from fastapi.responses import Response
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests
from google.auth.exceptions import TransportError
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rimiru import Rimiru
from progress import episode_counts
from handle import handler
from constants import MediaType
from dbmanager.MovieManager import MovieManager
from dbmanager.SharedCollectionManager import sharedCollectionManager
from dbmanager.SharedExtrasManager import sharedExtrasManager
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
PUBLIC_PATHS = {"/api/live", "/api/media/recent", "/api/testers"}


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
    async with connect_db.pool.acquire() as connection:
        await connection.execute(TESTERS_TABLE)
    await sharedCollectionManager.ensure_tables()


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


# ============================================================================ #
#                               EPISODE PROGRESS                               #
# ============================================================================ #
async def with_episode_counts(items: list) -> list[dict]:
    """to_json(items) with `episodes_watched` / `episodes_aired` on each series, for the app's
    progress bars. One query for the whole list."""
    data = to_json(items or [])
    ids = [d["id"] for d in data if d.get("media_type") == MediaType.SERIES.value]
    if not ids:
        return data
    async with connect_db.pool.acquire() as connection:
        rows = await connection.fetch(
            "SELECT id, seasons, last_episode_to_air FROM series WHERE id = ANY($1::int[])", ids
        )
    series = {r["id"]: r for r in rows}
    for d in data:
        s = series.get(d.get("id"))
        counts = episode_counts(s["seasons"], s["last_episode_to_air"], d.get("progress")) if s else None
        if counts:
            d["episodes_watched"] = counts["watched"]
            d["episodes_aired"] = counts["aired"]
    return data


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
class TesterSignupBody(BaseModel):
    email: str
    name: Optional[str] = None
    website: Optional[str] = None  # honeypot: hidden on the form, so only bots fill it in


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
    """Either a cached media_id, or tmdb_id + media_type to cache it first."""
    user_id: Optional[int] = None
    media_id: Optional[int] = None
    tmdb_id: Optional[int] = None
    media_type: Optional[str] = None


class SharedProgressBody(BaseModel):
    user_id: Optional[int] = None
    season: int
    episode: int


class InviteCodeBody(BaseModel):
    user_id: Optional[int] = None
    rotate: bool = False


class JoinBody(BaseModel):
    user_id: Optional[int] = None
    code: str


class ActingUserBody(BaseModel):
    user_id: Optional[int] = None


class UpdateCollectionBody(BaseModel):
    user_id: Optional[int] = None
    name: Optional[str] = None
    emoji: Optional[str] = None  # "" clears
    color: Optional[str] = None  # "#22aacc"; "" clears


class RoleBody(BaseModel):
    user_id: Optional[int] = None
    role: Literal["admin", "member"]


class VoteBody(BaseModel):
    user_id: Optional[int] = None
    up: bool = True


class RatingBody(BaseModel):
    user_id: Optional[int] = None
    rating: Optional[int] = None
    reaction: Optional[str] = None


class CommentBody(BaseModel):
    user_id: Optional[int] = None
    body: str


class NudgeBody(BaseModel):
    user_id: Optional[int] = None
    target_user_id: int


class PartyBody(BaseModel):
    user_id: Optional[int] = None
    media_id: int
    starts_at: datetime  # ISO 8601 with an offset
    note: Optional[str] = None


class RsvpBody(BaseModel):
    user_id: Optional[int] = None
    going: bool


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


# ============================================================================ #
#                                 BETA TESTERS                                 #
# ============================================================================ #
# The landing page's /testers/ form posts here. Emails are only used to add people to the
# Google Play testing list; GET /api/testers.csv (bot key) exports them for Play Console's upload.
TESTERS_TABLE = """
CREATE TABLE IF NOT EXISTS testers (
    id SERIAL PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""
TESTERS_WEBHOOK = os.getenv("TESTERS_WEBHOOK")  # optional Discord webhook, pinged on each new signup
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_signup_hits: dict[str, list[float]] = {}  # ip -> recent signup times, for a simple rate limit


def _rate_limited(ip: str, limit: int = 5, window: float = 3600) -> bool:
    now = time.time()
    hits = [t for t in _signup_hits.get(ip, []) if now - t < window]
    if len(_signup_hits) > 5000:
        _signup_hits.clear()
    _signup_hits[ip] = hits + [now]
    return len(hits) >= limit


@app.post("/api/testers")
async def tester_signup(body: TesterSignupBody, request: Request):
    if body.website:  # bot filled the honeypot; pretend it worked
        return {"ok": True}
    ip = request.client.host if request.client else "unknown"
    if _rate_limited(ip):
        raise HTTPException(status_code=429, detail="Too many signups from this network, try again later")

    email = body.email.strip().lower()
    if len(email) > 254 or not _EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="That doesn't look like an email address")
    name = (body.name or "").strip()[:100] or None

    async with connect_db.pool.acquire() as connection:
        inserted = await connection.fetchval(
            "INSERT INTO testers (email, name) VALUES ($1, $2) ON CONFLICT (email) DO NOTHING RETURNING id",
            email,
            name,
        )
    if inserted and TESTERS_WEBHOOK:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(TESTERS_WEBHOOK, json={
                    "content": f"New Cyan tester signup: {name or 'someone'} ({email})",
                    "allowed_mentions": {"parse": []},  # a name like "@everyone" must not ping anyone
                })
        except httpx.HTTPError:
            pass  # a failed ping must never fail the signup
    # Same answer whether or not the email was already on the list, so the form can't be used to probe it.
    return {"ok": True}


@app.get("/api/testers.csv", dependencies=[Depends(require_bot)])
async def testers_csv():
    """One email per line, no header: the format Play Console's "Upload CSV file" expects."""
    async with connect_db.pool.acquire() as connection:
        rows = await connection.fetch("SELECT email FROM testers ORDER BY created_at")
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    for r in rows:
        writer.writerow([r["email"]])
    return Response(
        out.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="cyan-testers.csv"'},
    )


@app.get("/api/media/search")
async def search_media(q: str = Query(..., min_length=1), media_type: str = "movie"):
    mt = parse_media_type(media_type)
    return await movieManager.search_media_multiple(mt.value, q)


@app.get("/api/media/names")
async def media_names():
    return await movieManager.fetch_media_names()


# Detail pages, keyed by (media type, tmdb id). In memory, so a restart empties it; entries expire
# after a day so ratings, next episodes and the like stay reasonably fresh.
DETAILS_TTL = 24 * 60 * 60
DETAILS_MAX = 500
_details_cache: dict[tuple[str, int], tuple[float, dict]] = {}


@app.get("/api/media/{media_type}/{tmdb_id}")
async def media_details(media_type: str, tmdb_id: int):
    """Movie/Series plus the detail-page extras (genres, cast, trailer, recommendations...)."""
    mt = parse_media_type(media_type)
    key = (mt.value, tmdb_id)
    cached = _details_cache.get(key)
    if cached and time.time() - cached[0] < DETAILS_TTL:
        return cached[1]

    page = await movieManager.get_media_page(mt.value, tmdb_id)
    if not page:
        raise HTTPException(status_code=404, detail="Media not found on TMDB")
    media, extras = page
    body = {**to_json(media), **extras}

    if len(_details_cache) >= DETAILS_MAX:
        del _details_cache[min(_details_cache, key=lambda k: _details_cache[k][0])]
    _details_cache[key] = (time.time(), body)
    return body


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
    # What was actually saved: the episode may have rolled over into the next season, and the
    # status may now be 'watched'.
    async with connect_db.pool.acquire() as connection:
        saved = await connection.fetchrow(
            "SELECT progress, trim(status) AS status FROM user_media WHERE user_id = $1 AND media_id = $2",
            user_id, media.id,
        )
    result = to_json(media)
    if saved:
        progress = saved["progress"]
        result["progress"] = json.loads(progress) if isinstance(progress, str) else progress
        result["user_status"] = saved["status"]
    return result


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
    return await with_episode_counts(await movieManager.get_user_watch_history(user_id))


@app.get("/api/users/{user_id}/incomplete", dependencies=[Depends(ensure_self)])
async def get_incomplete(user_id: int):
    return await with_episode_counts(await movieManager.check_user_completion(user_id))


@app.get("/api/users/{user_id}/upcoming", dependencies=[Depends(ensure_self)])
async def get_upcoming(user_id: int):
    return await with_episode_counts(await movieManager.upcoming_reminders(user_id))


@app.get("/api/users/{user_id}/media/{media_id}", dependencies=[Depends(ensure_self)])
async def get_user_media(user_id: int, media_id: int):
    media = await movieManager.fetch_user_media(user_id, {"id": media_id})
    if not media:
        raise HTTPException(status_code=404, detail="Media not found for this user")
    return (await with_episode_counts([media]))[0]


@app.get("/api/users/{user_id}/media/tmdb/{media_type}/{tmdb_id}", dependencies=[Depends(ensure_self)])
async def get_user_media_by_tmdb(user_id: int, media_type: str, tmdb_id: int):
    """The user's row for a TMDB title, for detail pages opened without a DB id (search,
    recommendations). 404 when it isn't on their list, or nobody has added it yet."""
    mt = parse_media_type(media_type)
    async with connect_db.pool.acquire() as connection:
        # Movie and TV ids are separate TMDB sequences, so the type is part of the match.
        media_id = await connection.fetchval(
            "SELECT id FROM media WHERE tmdb_id = $1 AND media_type = $2", tmdb_id, mt.table_name
        )
    media = await movieManager.fetch_user_media(user_id, {"id": media_id}) if media_id else None
    if not media:
        raise HTTPException(status_code=404, detail="Not on this user's list")
    return (await with_episode_counts([media]))[0]


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
    media_id = body.media_id
    if media_id is None:
        if body.tmdb_id is None or not body.media_type:
            raise HTTPException(status_code=400, detail="Send media_id, or tmdb_id and media_type")
        # Cache the title without putting it on anyone's personal list.
        media = await movieManager.cache_media(parse_media_type(body.media_type).value, body.tmdb_id)
        if not media or getattr(media, "id", None) is None:
            raise HTTPException(status_code=404, detail="Could not find that title on TMDB")
        media_id = media.id
    return to_json(await run_shared(
        sharedCollectionManager.add_item(collection_id, user_id, media_id)
    ))


@app.post("/api/collections/{collection_id}/items/{media_id}/watched")
async def mark_watched(collection_id: int, media_id: int, body: MarkWatchedBody, me: int | None = Depends(current_user_id)):
    user_id = acting_user(me, body.user_id, "user_id")
    return to_json(await run_shared(
        sharedCollectionManager.mark_watched(collection_id, media_id, user_id, body.everyone)
    ))


@app.delete("/api/collections/{collection_id}/items/{media_id}")
async def remove_item(collection_id: int, media_id: int, user_id: Optional[int] = None, me: int | None = Depends(current_user_id)):
    """Owner, or whoever added it."""
    user_id = acting_user(me, user_id, "user_id")
    return await run_shared(sharedCollectionManager.remove_item(collection_id, user_id, media_id))


@app.put("/api/collections/{collection_id}/items/{media_id}/progress")
async def set_shared_progress(collection_id: int, media_id: int, body: SharedProgressBody, me: int | None = Depends(current_user_id)):
    """The caller's last watched episode of a series in this collection. Personal lists are untouched."""
    user_id = acting_user(me, body.user_id, "user_id")
    return to_json(await run_shared(
        sharedCollectionManager.set_progress(collection_id, media_id, user_id, body.season, body.episode)
    ))


@app.delete("/api/collections/{collection_id}/items/{media_id}/progress")
async def reset_shared_progress(collection_id: int, media_id: int, user_id: Optional[int] = None, me: int | None = Depends(current_user_id)):
    user_id = acting_user(me, user_id, "user_id")
    return await run_shared(sharedCollectionManager.reset_progress(collection_id, media_id, user_id))


@app.post("/api/collections/{collection_id}/invite-code")
async def collection_invite_code(collection_id: int, body: InviteCodeBody, me: int | None = Depends(current_user_id)):
    """Any member gets the join code to share; the owner can rotate it."""
    user_id = acting_user(me, body.user_id, "user_id")
    code = await run_shared(sharedCollectionManager.invite_code(collection_id, user_id, body.rotate))
    return {"code": code}


@app.post("/api/collections/join")
async def join_collection(body: JoinBody, me: int | None = Depends(current_user_id)):
    user_id = acting_user(me, body.user_id, "user_id")
    return to_json(await run_shared(sharedCollectionManager.join_with_code(body.code, user_id)))


@app.post("/api/collections/{collection_id}/leave")
async def leave_collection(collection_id: int, body: ActingUserBody, me: int | None = Depends(current_user_id)):
    user_id = acting_user(me, body.user_id, "user_id")
    return await run_shared(sharedCollectionManager.leave(collection_id, user_id))


@app.delete("/api/collections/{collection_id}/members/{member_id}")
async def remove_member(collection_id: int, member_id: int, user_id: Optional[int] = None, me: int | None = Depends(current_user_id)):
    """Owner only."""
    user_id = acting_user(me, user_id, "user_id")
    return await run_shared(sharedCollectionManager.remove_member(collection_id, user_id, member_id))


SUGGESTION_SEEDS = 8   # most recently added items whose recommendations are pooled
SUGGESTION_LIMIT = 20


@app.get("/api/collections/{collection_id}/suggestions")
async def collection_suggestions(collection_id: int, user_id: Optional[int] = None, me: int | None = Depends(current_user_id)):
    """Titles to add, from TMDB recommendations for what's already on the list. A title
    recommended by several items ranks higher; `because` names up to two of them."""
    user_id = acting_user(me, user_id, "user_id")
    collection = await run_shared(sharedCollectionManager.get_collection(collection_id, user_id))
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found or you are not a member")

    def api_type(media_type: str) -> str:
        return "tv" if media_type in ("series", "tv") else "movie"

    items = [i for i in collection["items"] if i.get("tmdb_id")]
    have = {(api_type(i["media_type"]), i["tmdb_id"]) for i in items}
    seeds = sorted(items, key=lambda i: i.get("added_at") or datetime.min, reverse=True)[:SUGGESTION_SEEDS]
    pages = await asyncio.gather(
        *(media_details(api_type(i["media_type"]), i["tmdb_id"]) for i in seeds),
        return_exceptions=True,
    )

    pooled: dict[tuple[str, int], dict] = {}
    for seed, page in zip(seeds, pages):
        if not isinstance(page, dict):
            continue
        recs = page.get("recommendations") or []
        for position, rec in enumerate(recs):
            key = (rec["media_type"], rec["tmdb_id"])
            if key in have:
                continue
            entry = pooled.setdefault(key, {**rec, "because": [], "_score": 0.0})
            entry["_score"] += 1 + (len(recs) - position) / (2 * len(recs))
            if seed["title"] not in entry["because"]:
                entry["because"].append(seed["title"])

    ranked = sorted(pooled.values(), key=lambda e: e["_score"], reverse=True)[:SUGGESTION_LIMIT]
    return [
        {**{k: v for k, v in e.items() if k != "_score"}, "because": e["because"][:2]}
        for e in ranked
    ]


# ---------------------------------------------------------------------------- #
#                         SHARED COLLECTIONS: SOCIAL                            #
# ---------------------------------------------------------------------------- #
APP_URL = os.getenv("APP_URL", "https://cyan.austindwomoh.xyz/app")


async def dm_users(user_ids: list[int], message: str) -> None:
    """Best-effort Discord DMs through the bot's token. App-only users (no Discord) are skipped,
    and failures never break the request that triggered them."""
    token = os.getenv("DISCORD_TOKEN")
    if not token or not user_ids:
        return
    try:
        discord_ids = await UserManager.get_discord_ids(user_ids)
        headers = {"Authorization": f"Bot {token}"}
        async with httpx.AsyncClient(timeout=10) as client:
            for discord_id in discord_ids.values():
                channel = await client.post(
                    f"{DISCORD_API}/users/@me/channels", headers=headers, json={"recipient_id": str(discord_id)}
                )
                if channel.status_code >= 300:
                    continue
                await client.post(
                    f"{DISCORD_API}/channels/{channel.json()['id']}/messages",
                    headers=headers,
                    json={"content": message, "allowed_mentions": {"parse": []}},
                )
    except Exception as e:
        handler.error_handle(e, context="media api: dm_users")


@app.patch("/api/collections/{collection_id}")
async def update_collection(collection_id: int, body: UpdateCollectionBody, me: int | None = Depends(current_user_id)):
    """Rename, or set the list's emoji / colour. Owner or co-owner."""
    user_id = acting_user(me, body.user_id, "user_id")
    return to_json(await run_shared(sharedCollectionManager.update_collection(
        collection_id, user_id, body.name, body.emoji, body.color
    )))


@app.put("/api/collections/{collection_id}/members/{member_id}/role")
async def set_member_role(collection_id: int, member_id: int, body: RoleBody, me: int | None = Depends(current_user_id)):
    """Owner only: 'admin' (co-owner) or 'member'."""
    user_id = acting_user(me, body.user_id, "user_id")
    return await run_shared(sharedCollectionManager.set_role(collection_id, user_id, member_id, body.role))


@app.get("/api/invite-codes/{code}")
async def preview_invite_code(code: str, me: int | None = Depends(current_user_id)):
    """What a code joins (name, type, member and item counts), for the join page."""
    preview = await run_shared(sharedCollectionManager.preview_code(code))
    if not preview:
        raise HTTPException(status_code=404, detail="That invite code doesn't match any shared list")
    return to_json(preview)


@app.post("/api/collections/{collection_id}/items/{media_id}/vote")
async def vote_item(collection_id: int, media_id: int, body: VoteBody, me: int | None = Depends(current_user_id)):
    user_id = acting_user(me, body.user_id, "user_id")
    return await run_shared(sharedExtrasManager.vote(collection_id, media_id, user_id, body.up))


@app.put("/api/collections/{collection_id}/items/{media_id}/rating")
async def rate_item(collection_id: int, media_id: int, body: RatingBody, me: int | None = Depends(current_user_id)):
    user_id = acting_user(me, body.user_id, "user_id")
    return await run_shared(sharedExtrasManager.rate(collection_id, media_id, user_id, body.rating, body.reaction))


@app.get("/api/collections/{collection_id}/items/{media_id}/comments")
async def item_comments(collection_id: int, media_id: int, user_id: Optional[int] = None, me: int | None = Depends(current_user_id)):
    user_id = acting_user(me, user_id, "user_id")
    return to_json(await run_shared(sharedExtrasManager.comments(collection_id, media_id, user_id)))


@app.post("/api/collections/{collection_id}/items/{media_id}/comments")
async def add_item_comment(collection_id: int, media_id: int, body: CommentBody, me: int | None = Depends(current_user_id)):
    user_id = acting_user(me, body.user_id, "user_id")
    return to_json(await run_shared(sharedExtrasManager.add_comment(collection_id, media_id, user_id, body.body)))


@app.delete("/api/collections/{collection_id}/comments/{comment_id}")
async def delete_item_comment(collection_id: int, comment_id: int, user_id: Optional[int] = None, me: int | None = Depends(current_user_id)):
    user_id = acting_user(me, user_id, "user_id")
    return await run_shared(sharedExtrasManager.delete_comment(collection_id, comment_id, user_id))


@app.get("/api/collections/{collection_id}/activity")
async def collection_activity(collection_id: int, user_id: Optional[int] = None, limit: int = 30, me: int | None = Depends(current_user_id)):
    user_id = acting_user(me, user_id, "user_id")
    return to_json(await run_shared(sharedExtrasManager.activity(collection_id, user_id, limit)))


@app.post("/api/collections/{collection_id}/items/{media_id}/nudge")
async def nudge_member(collection_id: int, media_id: int, body: NudgeBody, me: int | None = Depends(current_user_id)):
    """Shows on their Home tab, and DMs them on Discord if they have it linked."""
    user_id = acting_user(me, body.user_id, "user_id")
    n = await run_shared(sharedExtrasManager.nudge(collection_id, media_id, user_id, body.target_user_id))
    asyncio.create_task(dm_users(
        [body.target_user_id],
        f"👋 **{n['nudger'] or 'Someone'}** nudged you to catch up on **{n['title']}** in "
        f"**{n['collection_name']}**. {APP_URL}/shared",
    ))
    return {"nudged": body.target_user_id}


@app.get("/api/users/{user_id}/nudges", dependencies=[Depends(ensure_self)])
async def user_nudges(user_id: int):
    return to_json(await run_shared(sharedExtrasManager.nudges_for(user_id)))


@app.get("/api/collections/{collection_id}/parties")
async def collection_parties(collection_id: int, user_id: Optional[int] = None, me: int | None = Depends(current_user_id)):
    user_id = acting_user(me, user_id, "user_id")
    return to_json(await run_shared(sharedExtrasManager.parties(collection_id, user_id)))


@app.get("/api/users/{user_id}/parties", dependencies=[Depends(ensure_self)])
async def user_parties(user_id: int):
    """Upcoming watch parties across all the user's shared lists, for Home."""
    return to_json(await run_shared(sharedExtrasManager.parties_for(user_id)))


@app.post("/api/collections/{collection_id}/parties")
async def create_party(collection_id: int, body: PartyBody, me: int | None = Depends(current_user_id)):
    """Plan a watch party; the other members get a Discord DM, and the bot reminds everyone
    who's going an hour before."""
    user_id = acting_user(me, body.user_id, "user_id")
    party = await run_shared(sharedExtrasManager.create_party(
        collection_id, body.media_id, user_id, body.starts_at, body.note
    ))
    when = int(party["starts_at"].timestamp())
    note = f"\n> {party['note']}" if party["note"] else ""
    asyncio.create_task(dm_users(
        [m for m in party.pop("member_ids") if m != user_id],
        f"🍿 **{party['created_by_username'] or 'Someone'}** planned a watch party for **{party['title']}** "
        f"in **{party['collection_name']}** on <t:{when}:F> (<t:{when}:R>).{note}\n"
        f"Are you in? {APP_URL}/shared",
    ))
    return to_json(party)


@app.post("/api/parties/{party_id}/rsvp")
async def rsvp_party(party_id: int, body: RsvpBody, me: int | None = Depends(current_user_id)):
    user_id = acting_user(me, body.user_id, "user_id")
    return to_json(await run_shared(sharedExtrasManager.rsvp(party_id, user_id, body.going)))


@app.delete("/api/parties/{party_id}")
async def cancel_party(party_id: int, user_id: Optional[int] = None, me: int | None = Depends(current_user_id)):
    user_id = acting_user(me, user_id, "user_id")
    return await run_shared(sharedExtrasManager.cancel_party(party_id, user_id))

if __name__ == "__main__":
    # Bound to localhost; nginx terminates TLS for the public domain and proxies here.
    uvicorn.run(
        app,
        host=os.getenv("API_HOST", "127.0.0.1"),
        port=int(os.getenv("API_PORT", "8000")),
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1",
    )
