from time import time

import asyncpg, discord, logging
from discord.ext import commands
from rimiru import Rimiru
from settings import *
from dbmanager import MovieManager
from gather_data import NotificationManager

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
        """This meant to b used for updates to users"""
        if message.author.bot:
            return  # Ignore messages from bots
        print("Message received:", message.content)
        state = (message.author.id in ALLOWED_ID) and (message.content.strip() == "$GodOfLies")
        print("State:", state)
        print("Author ID:", message.author.id," Allowed IDs:", ALLOWED_ID)
        

        if state:
            await message.channel.send("Ready to serve, Master.")
            await NotificationManager.notify_users(self)
            await message.add_reaction("✅")
            return  # stop ONLY this message # Ignore messages from users not in ALLOWED_ID
       
        await self.process_commands(message)
     
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

    # -------------------------------------------------
    # Discord Events
    # -------------------------------------------------
    async def on_ready(self):
        await self.change_presence(activity=discord.Game(name="Eternal loop"))
        logger.info("Ouroboros is ready")
        await asyncio.sleep(5)  # Give bot time to initialize
        print("[Movies Cog] Starting background updaters...")
        await asyncio.create_task(MovieManager.start_background_updaters(self))
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

  

