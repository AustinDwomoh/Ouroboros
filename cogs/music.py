import discord
from discord import app_commands
from discord.ext import commands
from spotify.spotify_client import SpotifyClient
from settings import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET
from handle import handler
from rimiru import Rimiru
from spotify.spotify_auth import build_auth_url
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
        self.db = None

    async def get_spotify_token(self, user_id: int) -> str | None:
        """Returns a live access token for the user, or None if not linked."""
        self.db = await Rimiru.shion()  # Ensure DB connection is established
        row = await self.db.selectOne(
                table="spotify_tokens",
                columns=["token"],
                filters={"user_id": user_id},
                
            )
        if not row:
            return None
        return row["token"]  # type: ignore

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
        refresh_token = await self.get_spotify_token(interaction.user.id)
        if not refresh_token:
            await interaction.followup.send("Please authenticate with Spotify first.")
            return
        self.spotify = make_spotify(refresh_token)
        try:
            msg = await self.spotify.get_currently_playing()
            await interaction.followup.send(msg)
        except Exception as e:
            handler.error_handle(context=f"Spotify auth error for user `{interaction.user.id}`: {e}", error=e)
        

    # ------------------------------------------------------------------
    # /play  (search + play immediately, or resume)
    # ------------------------------------------------------------------

    @app_commands.command(name="play", description="Search for a song and play it on Spotify.")
    @app_commands.describe(song_name="Song name or artist + song (leave blank to resume)")
    @app_commands.guild_only()
    async def play(self, interaction: discord.Interaction, song_name: str = ""):
        await interaction.response.defer()
        refresh_token = await self.get_spotify_token(interaction.user.id)
        print(f"Access token for user {interaction.user.id}: {refresh_token}")  # Debugging line
    
        if not refresh_token:
            await interaction.response.send_message(
                "You haven't linked Spotify yet. Run `/spotify_login` first.",
                ephemeral=True
            )
            return
        self.spotify = make_spotify(refresh_token)
        try:
            if not song_name:
                
                msg = await self.spotify.play()
                await interaction.followup.send(msg)
                return
            handler.log_task(context=f"Spotify search for user `{interaction.user.id}`", message=f"Searching for song: {song_name}")
            results = await self.spotify.search(song_name, limit=1)
            print(f"Search results for '{song_name}': {results}")  # Debugging line
            if not results:
                await interaction.followup.send("❌ No results found.")
                return

            track = results[0]
            msg = await self.spotify.play_track(track["uri"])
            await interaction.followup.send(
                f"{msg}\n🎵 **{track['name']}** by {track['artist']}"
            )

        except Exception as e:
            await interaction.followup.send("   Spotify authentication error. Please re-link your account.")
            handler.error_handle(context=f"Spotify auth error for user `{interaction.user.id}`: {e}", error=e)

    # ------------------------------------------------------------------
    # /pause
    # ------------------------------------------------------------------

    @app_commands.command(name="pause", description="Pause Spotify playback.")
    @app_commands.guild_only()
    async def pause(self, interaction: discord.Interaction):
        try:
            refresh_token = await self.get_spotify_token(interaction.user.id)
            if not refresh_token:
                await interaction.followup.send("Please authenticate with Spotify first.")
                return

            await interaction.response.defer()
            self.spotify = make_spotify(refresh_token)
            msg = await self.spotify.pause()
            await interaction.followup.send(msg)
        except Exception as e:
            await interaction.followup.send("Spotify authentication error. Please re-link your account.")
            handler.error_handle(context=f"Spotify auth error for user `{interaction.user.id}`: {e}", error=e)
    # ------------------------------------------------------------------
    # /skip
    # ------------------------------------------------------------------

    @app_commands.command(name="skip", description="Skip to the next or previous track.")
    @app_commands.describe(direction="'next' or 'previous'")
    @app_commands.guild_only()
    async def skip(self, interaction: discord.Interaction, direction: str = "next"):
        await interaction.response.defer()
        try:
            refresh_token = await self.get_spotify_token(interaction.user.id)
            if not refresh_token:
                await interaction.followup.send("Please authenticate with Spotify first.")
                return
            self.spotify = make_spotify(refresh_token)
            direction = direction.lower()
            if direction == "next":
                msg = await self.spotify.skip_next()
            elif direction in ("previous", "prev", "back"):
                msg = await self.spotify.skip_previous()
            else:
                msg = "❌ Use 'next' or 'previous'."
            await interaction.followup.send(msg)
        except Exception as e:
            await interaction.followup.send("Spotify authentication error. Please re-link your account.")
            handler.error_handle(context=f"Spotify auth error for user `{interaction.user.id}`: {e}", error=e)

    # ------------------------------------------------------------------
    # /volume
    # ------------------------------------------------------------------

    @app_commands.command(name="volume", description="Set Spotify volume (0–100).")
    @app_commands.describe(level="Volume level between 0 and 100")
    @app_commands.guild_only()
    async def volume(self, interaction: discord.Interaction, level: int):
        if level < 0 or level > 100:
            await interaction.response.send_message("❌ Volume must be between 0 and 100.", ephemeral=True)
            return
        try:
            await interaction.response.defer()
            refresh_token = await self.get_spotify_token(interaction.user.id)
            if not refresh_token:
                await interaction.followup.send("Please authenticate with Spotify first.")
                return
            self.spotify = make_spotify(refresh_token)
            msg = await self.spotify.set_volume(level)
            await interaction.followup.send(msg)
        except Exception as e:
            await interaction.followup.send("Spotify authentication error. Please re-link your account.")
            handler.error_handle(context=f"Spotify auth error for user `{interaction.user.id}`: {e}", error=e)

    # ------------------------------------------------------------------
    # /shuffle
    # ------------------------------------------------------------------

    @app_commands.command(name="shuffle", description="Toggle Spotify shuffle on or off.")
    @app_commands.describe(state="on or off")
    @app_commands.guild_only()
    async def shuffle(self, interaction: discord.Interaction, state: str = "on"):
        await interaction.response.defer()
        refresh_token = await self.get_spotify_token(interaction.user.id)
        if not refresh_token:
            await interaction.followup.send("Please authenticate with Spotify first.")
            return
        self.spotify = make_spotify(refresh_token)
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
        refresh_token = await self.get_spotify_token(interaction.user.id)
        if not refresh_token:
            await interaction.followup.send("Please authenticate with Spotify first.")
            return
        self.spotify = make_spotify(refresh_token)
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
        refresh_token = await self.get_spotify_token(interaction.user.id)
        if not refresh_token:
            await interaction.followup.send("Please authenticate with Spotify first.")
            return
        self.spotify = make_spotify(refresh_token)
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
        except Exception as e:
            await interaction.followup.send("❌ An error occurred while searching for the song.")
            handler.error_handle(context=f"Spotify search error for user `{interaction.user.id}`: {e}", error=e)

    # ------------------------------------------------------------------
    # /devices
    # ------------------------------------------------------------------

    @app_commands.command(name="devices", description="List active Spotify devices.")
    @app_commands.guild_only()
    async def devices(self, interaction: discord.Interaction):
        await interaction.response.defer()
        refresh_token = await self.get_spotify_token(interaction.user.id)
        if not refresh_token:
            await interaction.followup.send("Please authenticate with Spotify first.")
            return
        self.spotify = make_spotify(refresh_token)
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
        except Exception as e:
            await interaction.followup.send("❌ An error occurred while fetching Spotify devices.")
            handler.error_handle(context=f"Spotify devices error for user `{interaction.user.id}`: {e}", error=e)


async def setup(bot: commands.Bot):
    await bot.add_cog(MusiC(bot))