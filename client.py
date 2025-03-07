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


class Client(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.synced = False

    async def setup_hook(self):
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

    async def on_ready(self):
        await self.change_presence(activity=discord.Game(name="Eternal loop"))
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
