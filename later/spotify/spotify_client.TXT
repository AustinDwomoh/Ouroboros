import aiohttp
import base64
import asyncio
from typing import Optional
from handle import handler
class SpotifyClient:
    """
    Full Spotify client using the Web API (Premium account).
    Handles OAuth2 token refresh automatically.
    """

    TOKEN_URL = "https://accounts.spotify.com/api/token"
    BASE_URL = "https://api.spotify.com/v1"

    def __init__(self, client_id: str, client_secret: str, refresh_token: str):
        """
        Args:
            client_id:      Your Spotify app's Client ID.
            client_secret:  Your Spotify app's Client Secret.
            refresh_token:  A long-lived refresh token (see spotify_auth.py).
        """
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0  # epoch seconds

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    async def _get_access_token(self) -> str:
        """Return a valid access token, refreshing if needed."""
        import time
        if self._access_token and time.time() < self._token_expires_at - 30:
            return self._access_token

        credentials = f"{self._client_id}:{self._client_secret}"
        encoded = base64.b64encode(credentials.encode()).decode()

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.TOKEN_URL,
                headers={
                    "Authorization": f"Basic {encoded}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self._refresh_token,
                },
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    handler.error_handle(context=f"Token refresh failed ({resp.status}): {body}", error=Exception(f"Token refresh failed ({resp.status}): {body}"))
                    raise Exception(f"Token refresh failed ({resp.status}): {body}")
                data = await resp.json()
                handler.log_task(context="Spotify token refresh", message=f"Access token refreshed successfully.")
                print(f"Spotify token refreshed successfully. New access token: {data}")  # Debugging line

        self._access_token = data["access_token"]
        self._token_expires_at = time.time() + data["expires_in"]
        return self._access_token

    # ------------------------------------------------------------------
    # Core request helper
    # ------------------------------------------------------------------

    async def _request(self, method: str, path: str, **kwargs) -> Optional[dict]:
        """Make an authenticated request to the Spotify Web API."""
        token = await self._get_access_token()

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        headers.update(kwargs.pop("headers", {}))

        async with aiohttp.ClientSession() as session:
            async with session.request(
                method,
                f"{self.BASE_URL}{path}",
                headers=headers,
                **kwargs,
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                elif resp.status == 204:
                    return {}           # success, no body (e.g. play/pause)
                elif resp.status == 401:
                    raise Exception ("Access token rejected (401).")
                elif resp.status == 403:
                    return {"error": "Premium account required for this action."}
                elif resp.status == 404:
                    return {"error": "Device not found. Open Spotify on a device first."}
                elif resp.status == 429:
                    retry_after = int(resp.headers.get("Retry-After", 1))
                    await asyncio.sleep(retry_after)
                    return await self._request(method, path, **kwargs)
                else:
                    body = await resp.text()
                    raise Exception(f"Spotify API error {resp.status}: {resp.reason} - {body}")

    # ------------------------------------------------------------------
    # Playback — currently playing
    # ------------------------------------------------------------------

    async def get_currently_playing(self) -> str:
        """Return a formatted string of the currently playing track."""
        data = await self._request("GET", "/me/player/currently-playing")

        if not data or not data.get("is_playing"):
            return "Nothing is currently playing."

        item = data.get("item", {})
        artist = item["artists"][0]["name"]
        title = item["name"]
        album = item["album"]["name"]
        cover = item["album"]["images"][0]["url"] if item["album"]["images"] else None
        progress_ms = data.get("progress_ms", 0)
        duration_ms = item.get("duration_ms", 1)
        progress_pct = int((progress_ms / duration_ms) * 100)

        msg = (
            f"🎵 **{title}**\n"
            f"👤 {artist} — {album}\n"
            f"⏱ {_ms_to_time(progress_ms)} / {_ms_to_time(duration_ms)} "
            f"({progress_pct}%)"
        )
        if cover:
            msg += f"\n🖼 {cover}"
        return msg

    # ------------------------------------------------------------------
    # Playback — transport controls (Premium)
    # ------------------------------------------------------------------

    async def play(self, device_id: Optional[str] = None) -> str:
        """Resume playback."""
        try:
            params = {}
            if device_id:
                params["device_id"] = device_id
            result = await self._request("PUT", "/me/player/play", params=params)
            return result.get("error", "▶️ Playback started.")
        except Exception as e:
            handler.error_handle(context=f"Spotify play error: {e}", error=e)
            return "❌ An error occurred while trying to start playback."

    async def pause(self, device_id: Optional[str] = None) -> str:
        """Pause playback."""
        try:
            params = {}
            if device_id:
                params["device_id"] = device_id
            result = await self._request("PUT", "/me/player/pause", params=params)
            return result.get("error", "⏸ Playback paused.")
        except Exception as e:
            handler.error_handle(context=f"Spotify pause error: {e}", error=e)
            return "❌ An error occurred while trying to pause playback."   
            
        

    async def skip_next(self, device_id: Optional[str] = None) -> str:
        """Skip to next track."""
        params = {}
        if device_id:
            params["device_id"] = device_id
        result = await self._request("POST", "/me/player/next", params=params)
        return result.get("error", "⏭ Skipped to next track.")

    async def skip_previous(self, device_id: Optional[str] = None) -> str:
        """Skip to previous track."""
        params = {}
        if device_id:
            params["device_id"] = device_id
        result = await self._request("POST", "/me/player/previous", params=params)
        return result.get("error", "⏮ Went to previous track.")

    async def set_volume(self, level: int, device_id: Optional[str] = None) -> str:
        """Set volume (0–100)."""
        if not 0 <= level <= 100:
            return "❌ Volume must be between 0 and 100."
        params = {"volume_percent": level}
        if device_id:
            params["device_id"] = device_id
        result = await self._request("PUT", "/me/player/volume", params=params)
        return result.get("error", f"🔊 Volume set to {level}%.")

    async def set_shuffle(self, state: bool, device_id: Optional[str] = None) -> str:
        """Enable or disable shuffle."""
        params = {"state": str(state).lower()}
        if device_id:
            params["device_id"] = device_id
        result = await self._request("PUT", "/me/player/shuffle", params=params)
        label = "on 🔀" if state else "off"
        return result.get("error", f"Shuffle {label}.")

    async def set_repeat(self, mode: str, device_id: Optional[str] = None) -> str:
        """Set repeat mode: 'track', 'context', or 'off'."""
        if mode not in ("track", "context", "off"):
            return "❌ Mode must be 'track', 'context', or 'off'."
        params = {"state": mode}
        if device_id:
            params["device_id"] = device_id
        result = await self._request("PUT", "/me/player/repeat", params=params)
        return result.get("error", f"🔁 Repeat set to '{mode}'.")

    # ------------------------------------------------------------------
    # Search & queue
    # ------------------------------------------------------------------

    async def search(self, query: str, limit: int = 5) -> list[dict]:
        """
        Search for tracks by name/artist.
        Returns a list of dicts: {name, artist, uri, duration_ms, url}
        """
        try:
            data = await self._request(
                "GET", "/search",
                params={"q": query, "type": "track", "limit": limit}
            )
            if not data or "tracks" not in data:
                return []

            results = []
            for item in data["tracks"]["items"]:
                results.append({
                    "name": item["name"],
                    "artist": item["artists"][0]["name"],
                    "uri": item["uri"],               # spotify:track:XXXX
                    "duration_ms": item["duration_ms"],
                    "url": item["external_urls"]["spotify"],
                })
            return results
        except Exception as e:
            handler.error_handle(context=f"Spotify search error: {e}", error=e)
            return []

    async def add_to_queue(self, track_uri: str, device_id: Optional[str] = None) -> str:
        """Add a track URI to the playback queue."""
        params = {"uri": track_uri}
        if device_id:
            params["device_id"] = device_id
        result = await self._request("POST", "/me/player/queue", params=params)
        return result.get("error", "➕ Track added to queue.")

    async def play_track(self, track_uri: str, device_id: Optional[str] = None) -> str:
        """Play a specific track immediately (by Spotify URI)."""
        params = {}
        if device_id:
            params["device_id"] = device_id
        result = await self._request(
            "PUT", "/me/player/play",
            params=params,
            json={"uris": [track_uri]}
        )
        return result.get("error", "▶️ Playing track.")

    # ------------------------------------------------------------------
    # Devices
    # ------------------------------------------------------------------

    async def get_devices(self) -> list[dict]:
        """Return a list of active Spotify devices."""
        data = await self._request("GET", "/me/player/devices")
        if not data:
            return []
        return data.get("devices", [])

    async def transfer_playback(self, device_id: str) -> str:
        """Transfer playback to a specific device."""
        result = await self._request(
            "PUT", "/me/player",
            json={"device_ids": [device_id], "play": True}
        )
        return result.get("error", "✅ Playback transferred.")


# ------------------------------------------------------------------
# Utility
# ------------------------------------------------------------------

def _ms_to_time(ms: int) -> str:
    """Convert milliseconds to m:ss string."""
    seconds = ms // 1000
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"