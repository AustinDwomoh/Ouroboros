from time import time
import settings
import discord
import logging
from discord.ext import commands
from settings import *

# Logging setup
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("Ouroboros")

# Intents configuration
intents = discord.Intents.default()
intents.message_content = True
intents.guild_messages = True
intents.members = True
_seen_users: dict[int, float] = {}
CACHE_TTL = 300 
db_pool: asyncpg.Pool | None = None
class Client(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.synced = False

    async def setup_hook(self):
        await self.init_db_pool()
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

    async def init_db_pool():
        global db_pool
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        db_pool = await asyncpg.create_pool(
            host=PGHOST,
            port=PGPORT,
            database=PGDATABASE,
            user=PGUSER,
            password=PGPASSWORD,
            ssl=ssl_context,
            min_size=2,
            max_size=10,
        )

    async def ensure_user(interaction):
        uid = interaction.user.id
        now = time.time()
        user = interaction.user

        if uid in _seen_users and now - _seen_users[uid] < CACHE_TTL:
            return
        async with db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (user_id, username)
                VALUES ($1, $2)
                ON CONFLICT (user_id)
                DO UPDATE SET
                    username = EXCLUDED.username,
                    updated_at = NOW();
            """, user.id, user.username)


    async def on_ready(self):
        await self.change_presence(activity=discord.Game(name="Eternal loop"))
        #for guild in self.guilds:
         #   await guild.leave()
          #  print(f"Leaving {guild.name} ({guild.id})")
		
        logger.info("Ouroboros Is Ready")

    async def load_commands(self):
        """Load command files from the commands directory."""
        for cmd_file in settings.CMDS_DIR.glob("*.py"):
            if cmd_file.name != "__init__.py":
                try:
                    await self.load_extension(f"cmds.{cmd_file.name[:-3]}")
                    logger.info(f"Loaded command: {cmd_file.name}")
                except Exception as e:
                    logger.error(f"Failed to load command {cmd_file.name}: {e}")

    async def load_cogs(self):
        """Load cog files from the cogs directory."""
        for cog_file in settings.COGS_DIR.glob("*.py"):
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

    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.user.bot:
            return
        uid = interaction.user.id
        if uid in _seen_users:
            return
        _seen_users.add(uid)
        await ensure_user(interaction)
        await self.process_application_commands(interaction)


