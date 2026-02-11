from time import time

import asyncpg, discord, logging
from discord.ext import commands
from pyparsing import Path
from rimiru import Rimiru
from settings import *
from dbmanager.MovieManager import MovieManager

# Logging setup
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("Ouroboros")

# Intents configuration
intents = discord.Intents.default()
intents.message_content = True
intents.guild_messages = True
intents.members = True

CACHE_TTL = 1

class Client(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.synced = False
        self.db_pool: asyncpg.Pool | None = None
        self._seen_users: dict[int, float] = {}
        self.pending_announcements = {}
        self.pending_previews = {}

    async def setup_hook(self):
        self.db = await Rimiru.shion() 
        await self.load_commands()
        await self.load_cogs()
        logger.info("Loaded commands and cogs")

        if not self.synced:
            try:
                synced = await self.tree.sync()
                logger.info(
                    f"Slash commands synced successfully: {len(synced)} commands"
                )
                self.synced = True
            except Exception as e:
                logger.error(f"Failed to sync slash commands: {e}")
                await self.close()

    @commands.Cog.listener()
    async def on_message(self, message):
        try:
            if message.author.bot:
                return

            uid = message.author.id
            content = message.content.strip().lower()

            # ARM
            if uid in ALLOWED_ID and content == "$godoflies":
                self.pending_announcements[uid] = True
                await message.channel.send("📝 Announcement mode armed. Send the content.")
                return

            # BUILD PREVIEW
            if uid in self.pending_announcements:
                user_id = self.pending_announcements.pop(uid)

                title, summary, body, footer = self.parse_announcement(message.content)

                embed = discord.Embed(
                    title=title,
                    description=body,
                    color=discord.Color.gold(),
                    timestamp=discord.utils.utcnow()
                )

                if summary:
                    embed.add_field(name="Summary", value=summary, inline=False)

                embed.set_footer(text=footer or f"Posted by {message.author.display_name}")

                self.pending_previews[uid] = embed

                await message.author.send(
                    "👀 **Announcement Preview**\n"
                    "Type `confirm` to publish or `cancel` to discard."
                )
                await message.author.send(embed=embed)
                return

            # CONFIRM / CANCEL
            if uid in self.pending_previews:
                if content == "cancel":
                    self.pending_previews.pop(uid)
                    await message.author.send("❌ Announcement cancelled.")
                    return

                if content == "confirm":
                    embed = self.pending_previews.pop(uid)
                    for guild in self.guilds:
                        news_channels = [
                            ch for ch in guild.channels
                            if ch.type == discord.ChannelType.news
                            and ch.permissions_for(guild.me).send_messages
                            and ch.permissions_for(guild.me).manage_messages
                        ]

                        # CASE A — announcement channels exist
                        if news_channels:
                            for ch in news_channels:
                                try:
                                    msg = await ch.send(embed=embed)
                                    await msg.publish()
                                except Exception as e:
                                    print(f"Publish failed in {ch.name}: {e}")
                            return

                        # CASE B — fallback to system or current channel
                        fallback_channel = (
                            guild.system_channel
                            if guild.system_channel
                            and guild.system_channel.permissions_for(guild.me).send_messages
                            else None
                        )
                        if fallback_channel:
                            await fallback_channel.send(embed=embed)
                            await message.channel.send(
                                "⚠️ No announcement channels found. Sent as a normal message instead."
                            )

                    await message.author.send("✅ Announcement published.")
                    return

            await self.process_commands(message)
        except Exception as e:
            ErrorHandler().handle(e, context="$godoflies:on_message")
     
        # -------------------------------------------------
        # DB Utilities
        # -------------------------------------------------
   
    async def ensure_user(self, interaction: discord.Interaction):
        uid = interaction.user.id
        now = time()

        last_seen = self._seen_users.get(uid)
        if last_seen and now - last_seen < CACHE_TTL:
            return
        
        await self.db.upsert(
                "users", {"discord_id": uid, "username": interaction.user.name}, conflict_column="discord_id"
            )

        self._seen_users[uid] = now
    
    def parse_announcement(self, raw: str):
        sections = [s.strip() for s in raw.split("---")]

        # header
        if "|" in sections[0]:
            title, summary = map(str.strip, sections[0].split("|", 1))
        else:
            title = sections[0]
            summary = None

        body = sections[1] if len(sections) > 1 else ""
        footer = sections[2] if len(sections) > 2 else None

        return title, summary, body, footer


    # -------------------------------------------------
    # Discord Events
    # -------------------------------------------------
    async def on_ready(self):
        await self.change_presence(activity=discord.Game(name="Eternal loop"))
        logger.info("Ouroboros is ready")
        await asyncio.sleep(5)  # Give bot time to initialize
        print("[Movies Cog] Starting background updaters...")
        asyncio.create_task(MovieManager().start_background_updaters(self))

        print("[Movies Cog] Background updaters started!")

    async def on_interaction(self, interaction: discord.Interaction):
        """Handle all interactions and ensure user exists in database."""
        if interaction.user.bot:
            return
        
        # Run ensure_user in background without blocking the interaction
        self.loop.create_task(
            self.ensure_user(interaction)
        )


    async def load_commands(self):
        """Load command files from the commands directory."""
        for cmd_file in CMDS_DIR.glob("*.py"):
            if cmd_file.name != "__init__.py":
                try:
                    await self.load_extension(f"cmds.{cmd_file.name[:-3]}")
                    logger.info(f"Loaded command: {cmd_file.name}")
                except Exception as e:
                    logger.error(f"Failed to load command {cmd_file.name}: {e}")

    async def load_cogs(self):
        """Load cog files from the cogs directory."""
        for cog_file in COGS_DIR.glob("*.py"):
            if cog_file.name != "__init__.py":
                try:
                    await self.load_extension(f"cogs.{cog_file.name[:-3]}")
                    logger.info(f"Loaded cog: {cog_file.name}")
                except Exception as e:
                    logger.error(f"Failed to load cog {cog_file.name}: {e}")

    # Error handler for unknown commands or permissions
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            await ctx.send("Please specify a valid command.")
        elif isinstance(error, commands.CheckFailure):
            await ctx.send("You do not have permission to use this command.")

  

