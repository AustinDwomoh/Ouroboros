import asyncio
import os
import urllib.request
import urllib.parse
import base64
import json
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv
from rimiru import Rimiru
from handle import handler
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()



app = FastAPI()
@app.on_event("startup")
async def startup():
    global connect_db
    connect_db = await Rimiru.shion()


@app.on_event("shutdown")
async def shutdown():
    if connect_db:
        await connect_db.pool.close()
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")



@app.get("/callback", response_class=HTMLResponse)
async def spotify_callback(request: Request):
    code  = request.query_params.get("code")
    error = request.query_params.get("error")
    state = request.query_params.get("state")  # discord_user_id

    # ── error from Spotify (user denied, etc.) ──────────────────────────────
    if error or not code or not state:
        handler.error_handle(context=f"Spotify callback error: {error or 'Missing code/state'}", 
            error=Exception(f"Spotify callback error: {error or 'Missing code/state'}"))
        return HTMLResponse("""
            <h2>Something went wrong.</h2>
            <p>You can close this tab and try again, or contact support.</p>
        """, status_code=400)

    # ── exchange code for refresh token ─────────────────────────────────────
    try:
        refresh_token = await asyncio.to_thread(_exchange_code, code)
    except Exception as e:
        handler.error_handle(context=f"Token exchange failed for user `{state}`: {e}", 
            error=Exception(f"Token exchange failed for user `{state}`: {e}"))
        return HTMLResponse("""
            <h2>Failed to connect your Spotify account.</h2>
            <p>Please try again or contact support.</p>
        """, status_code=500)

    # ── upsert into spotify_tokens ───────────────────────────────────────────
    try:
        rs = await connect_db.upsert(table="spotify_tokens", data={"token": refresh_token, "user_id": int(state)}, conflict_column="user_id"
        )
        handler.log_task(context=f"Spotify token stored for user `{state}`", message=f"Refresh token stored in DB for user `{state}`")
    except Exception as e:
        handler.error_handle(context=f"DB write failed for user `{state}`: {e}", 
            error=Exception(f"DB write failed for user `{state}`: {e}"))
        return HTMLResponse("<h2>Database error. Please contact support.</h2>", status_code=500)

    return HTMLResponse("""
        <h2>✅ Spotify connected!</h2>
        <p>You can close this tab and return to Discord.</p>
    """)


def _exchange_code(code: str) -> str:
    credentials = base64.b64encode(
        f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()
    ).decode()
    try:
        data = urllib.parse.urlencode({
            "grant_type":   "authorization_code",
            "code":         code,
            "redirect_uri": SPOTIFY_REDIRECT_URI,
        }).encode()
        req = urllib.request.Request(
            "https://accounts.spotify.com/api/token",
            data=data,
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type":  "application/x-www-form-urlencoded",
            },
        )
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())["refresh_token"]
    except Exception as e:
        handler.error_handle(context=f"Error exchanging code for token: {e}", error=e)
        raise


