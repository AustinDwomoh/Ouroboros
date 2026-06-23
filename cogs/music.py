import discord
from discord import app_commands
from discord.ext import commands
from spotify_client import SpotifyClient, SpotifyAuthError, SpotifyAPIError
from settings import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET
from spotify_auth import build_auth_url, get_access_token
import asyncio
def make_spotify(refresh_token) -> SpotifyClient:
    """Create a SpotifyClient from settings."""
    return SpotifyClient(
        client_id=SPOTIFY_CLIENT_ID, #type: ignore
        client_secret=SPOTIFY_CLIENT_SECRET, #type: ignore
        refresh_token=refresh_token,
    )


class MusiC(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client
        self.refresh_token = {}
        self.spotify = None
        
    async def get_spotify_token(self, user_id: int) -> str | None:
        """Returns a live access token for the user, or None if not linked."""
        async with self.db.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT token FROM spotify_tokens WHERE user_id = $1", user_id
            )
        if not row:
            return None
        return await asyncio.to_thread(get_access_token, row["token"])

    @app_commands.command(name="spotify_login", description="Link your Spotify account.")
    async def spotify_login(self, interaction: discord.Interaction):
        url = build_auth_url(interaction.user.id)
        await interaction.response.send_message(
            f"[Click here to link your Spotify account]({url})\n"
            "This link is just for you — no one else can see it.",
            ephemeral=True
        )

   
        
    # ------------------------------------------------------------------
    # /nowplaying
    # ------------------------------------------------------------------

    @app_commands.command(name="nowplaying", description="Show what's currently playing on Spotify.")
    @app_commands.guild_only()
    async def nowplaying(self, interaction: discord.Interaction):
        await interaction.response.defer()
        access_token = await self.get_spotify_token(interaction.user.id)
        if not access_token:
            await interaction.followup.send("Please authenticate with Spotify first.")
            return
        self.spotify = make_spotify(access_token)
        try:
            msg = await self.spotify.get_currently_playing()
        except SpotifyAuthError as e:
            msg = f"❌ Auth error: {e}"
        await interaction.followup.send(msg)

    # ------------------------------------------------------------------
    # /play  (search + play immediately, or resume)
    # ------------------------------------------------------------------

    @app_commands.command(name="play", description="Search for a song and play it on Spotify.")
    @app_commands.describe(song_name="Song name or artist + song (leave blank to resume)")
    @app_commands.guild_only()
    async def play(self, interaction: discord.Interaction, song_name: str = ""):
        access_token = await self.get_spotify_token(interaction.user.id)
        if not access_token:
            await interaction.response.send_message(
                "You haven't linked Spotify yet. Run `/spotify_login` first.",
                ephemeral=True
            )
            return
        self.spotify = make_spotify(access_token)
        try:
            if not song_name:
                msg = await self.spotify.play()
                await interaction.followup.send(msg)
                return

            results = await self.spotify.search(song_name, limit=1)
            if not results:
                await interaction.followup.send("❌ No results found.")
                return

            track = results[0]
            msg = await self.spotify.play_track(track["uri"])
            await interaction.followup.send(
                f"{msg}\n🎵 **{track['name']}** by {track['artist']}"
            )

        except SpotifyAuthError as e:
            await interaction.followup.send(f"❌ Auth error: {e}")
        except SpotifyAPIError as e:
            await interaction.followup.send(f"❌ Spotify error {e.status}: {e.reason}")

    # ------------------------------------------------------------------
    # /pause
    # ------------------------------------------------------------------

    @app_commands.command(name="pause", description="Pause Spotify playback.")
    @app_commands.guild_only()
    async def pause(self, interaction: discord.Interaction):
        access_token = await self.get_spotify_token(interaction.user.id)
        if not access_token:
            await interaction.followup.send("Please authenticate with Spotify first.")
            return

        await interaction.response.defer()
        self.spotify = make_spotify(access_token)
        msg = await self.spotify.pause()
        await interaction.followup.send(msg)

    # ------------------------------------------------------------------
    # /skip
    # ------------------------------------------------------------------

    @app_commands.command(name="skip", description="Skip to the next or previous track.")
    @app_commands.describe(direction="'next' or 'previous'")
    @app_commands.guild_only()
    async def skip(self, interaction: discord.Interaction, direction: str = "next"):
        await interaction.response.defer()
        access_token = await self.get_spotify_token(interaction.user.id)
        if not access_token:
            await interaction.followup.send("Please authenticate with Spotify first.")
            return
        self.spotify = make_spotify(access_token)
        direction = direction.lower()
        if direction == "next":
            msg = await self.spotify.skip_next()
        elif direction in ("previous", "prev", "back"):
            msg = await self.spotify.skip_previous()
        else:
            msg = "❌ Use 'next' or 'previous'."
        await interaction.followup.send(msg)

    # ------------------------------------------------------------------
    # /volume
    # ------------------------------------------------------------------

    @app_commands.command(name="volume", description="Set Spotify volume (0–100).")
    @app_commands.describe(level="Volume level between 0 and 100")
    @app_commands.guild_only()
    async def volume(self, interaction: discord.Interaction, level: int):
        await interaction.response.defer()
        access_token = await self.get_spotify_token(interaction.user.id)
        if not access_token:
            await interaction.followup.send("Please authenticate with Spotify first.")
            return
        self.spotify = make_spotify(access_token)
        msg = await self.spotify.set_volume(level)
        await interaction.followup.send(msg)

    # ------------------------------------------------------------------
    # /shuffle
    # ------------------------------------------------------------------

    @app_commands.command(name="shuffle", description="Toggle Spotify shuffle on or off.")
    @app_commands.describe(state="on or off")
    @app_commands.guild_only()
    async def shuffle(self, interaction: discord.Interaction, state: str = "on"):
        await interaction.response.defer()
        access_token = await self.get_spotify_token(interaction.user.id)
        if not access_token:
            await interaction.followup.send("Please authenticate with Spotify first.")
            return
        self.spotify = make_spotify(access_token)
        enabled = state.lower() in ("on", "true", "yes", "1")
        msg = await self.spotify.set_shuffle(enabled)
        await interaction.followup.send(msg)

    # ------------------------------------------------------------------
    # /repeat
    # ------------------------------------------------------------------

    @app_commands.command(name="repeat", description="Set repeat mode: track, context, or off.")
    @app_commands.describe(mode="track, context, or off")
    @app_commands.guild_only()
    async def repeat(self, interaction: discord.Interaction, mode: str = "context"):
        await interaction.response.defer()
        access_token = await self.get_spotify_token(interaction.user.id)
        if not access_token:
            await interaction.followup.send("Please authenticate with Spotify first.")
            return
        self.spotify = make_spotify(access_token)
        msg = await self.spotify.set_repeat(mode.lower())
        await interaction.followup.send(msg)

    # ------------------------------------------------------------------
    # /queue
    # ------------------------------------------------------------------

    @app_commands.command(name="queue", description="Search for a song and add it to the Spotify queue.")
    @app_commands.describe(song_name="Song name or artist + song")
    @app_commands.guild_only()
    async def queue(self, interaction: discord.Interaction, song_name: str):
        await interaction.response.defer()
        access_token = await self.get_spotify_token(interaction.user.id)
        if not access_token:
            await interaction.followup.send("Please authenticate with Spotify first.")
            return
        self.spotify = make_spotify(access_token)
        try:
            results = await self.spotify.search(song_name, limit=1)
            if not results:
                await interaction.followup.send("❌ No results found.")
                return
            track = results[0]
            msg = await self.spotify.add_to_queue(track["uri"])
            await interaction.followup.send(
                f"{msg}\n🎵 **{track['name']}** by {track['artist']}"
            )
        except SpotifyAPIError as e:
            await interaction.followup.send(f"❌ Spotify error {e.status}: {e.reason}")

    # ------------------------------------------------------------------
    # /devices
    # ------------------------------------------------------------------

    @app_commands.command(name="devices", description="List active Spotify devices.")
    @app_commands.guild_only()
    async def devices(self, interaction: discord.Interaction):
        await interaction.response.defer()
        access_token = await self.get_spotify_token(interaction.user.id)
        if not access_token:
            await interaction.followup.send("Please authenticate with Spotify first.")
            return
        self.spotify = make_spotify(access_token)
        try:
            devs = await self.spotify.get_devices()
            if not devs:
                await interaction.followup.send("No active devices found. Open Spotify somewhere first.")
                return
            lines = []
            for d in devs:
                active = "✅" if d["is_active"] else "⬜"
                lines.append(f"{active} **{d['name']}** ({d['type']}) — vol {d['volume_percent']}%  `{d['id']}`")
            await interaction.followup.send("\n".join(lines))
        except SpotifyAPIError as e:
            await interaction.followup.send(f"❌ Spotify error {e.status}: {e.reason}")


async def setup(bot: commands.Bot):
    await bot.add_cog(MusiC(bot))