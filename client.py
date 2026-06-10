from time import time

import asyncpg, discord, logging
from discord.ext import commands
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

CACHE_TTL = 300

class Client(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.synced = False
        self.db_pool: asyncpg.Pool | None = None
        self._seen_users: dict[int, float] = {}
        self.pending_announcements = {}
        self.pending_previews = {}
        self.pending_messages = {} 

    async def setup_hook(self):
        self.db = await Rimiru.shion() 
        await self.load_commands()
        await self.load_cogs()
        self.add_listener(self.on_interaction, "on_interaction") 
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
            #with the new join method in the welcome cog, this is no longer needed, but we can keep it for testing or future use
            #if uid in ALLOWED_ID and content == "$godoflies":
            #    self.pending_announcements[uid] = True
            #    await message.channel.send("📝 Announcement mode armed. Send the content.")
            #    return
            
            if uid in ALLOWED_ID and content == "$nuke":
                for guild in self.guilds:
                    await guild.leave()
                    await message.author.send(f"Left guild: {guild.name}")
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
            logger.info(f"User {uid} seen recently, skipping DB check")
            logger.info(f"Current _seen_users: {self._seen_users}")
            return
        logger.info(f"User {uid} not seen recently, proceeding with DB check")
        logger.info(f"Current _seen_users: {self._seen_users}")
        hw = await self.db.upsert(
                "users", {"discord_id": uid, "username": interaction.user.name}, conflict_column="discord_id"
            )
        logger.info(f"User {uid} saved to DB: {hw}")
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
        # Log the interaction
        print(f"[Interaction] Received interaction from {interaction.user} with ID {interaction.id}")
        logger.info(f"[Interaction] Received interaction from {interaction.user} with ID {interaction.id}")
        if interaction.user.bot:
            logger.info(f"Interaction from bot ignored: {interaction.user}")
            return
        
        # Run ensure_user in background without blocking the interaction
        command_color = {
            # Universal
            "ouroboros":        discord.Color.og_blurple(),
            "rps":              discord.Color.blue(),
            "sporty":           discord.Color.purple(),
            "help":             discord.Color.light_grey(),
            "hi":               discord.Color.teal(),

            # Server only
            "rpvp":             discord.Color.orange(),
            "leaderboard":      discord.Color.gold(),
            "rank":             discord.Color.yellow(),
            "level_self":       discord.Color.green(),
            "level_server":     discord.Color.dark_green(),
            "coinflip":         discord.Color.greyple(),
            "create_embed":     discord.Color.magenta(),

            # DM / Media
            "add_movie":        discord.Color.red(),
            "add_series":       discord.Color.dark_red(),
            "add_to_watchlist": discord.Color.brand_red(),
            "watchlist":        discord.Color.dark_magenta(),
            "incomplete":       discord.Color.dark_orange(),
            "search_media":     discord.Color.blurple(),
            "delete_media":     discord.Color.dark_grey(),

            # Admin
            "set_welcome_channel":  discord.Color.brand_green(),
            "set_goodbye_channel":  discord.Color.dark_teal(),
            "server_stats":         discord.Color.dark_blue(),
            "activate_tournament":  discord.Color.fuchsia(),
            "set_tour_role":        discord.Color.dark_gold(),
        }
        command_name = interaction.data.get("name", "Unknown") if interaction.data else "Unknown"
        category_map = {
            "ouroboros": " Universal", "rps": " Universal", "sporty": " Universal",
            "help": " Universal", "hi": " Universal",
            "rpvp": "Server", "leaderboard": " Server", "rank": " Server",
            "level_self": " Server", "level_server": " Server",
            "coinflip": "Server", "create_embed": " Server",
            "add_movie": " DM", "add_series": " DM", "add_to_watchlist": " DM",
            "watchlist": " DM", "incomplete": " DM",
            "search_media": " DM", "delete_media": " DM",
            "set_welcome_channel": " Admin", "set_goodbye_channel": " Admin",
            "server_stats": " Admin", "activate_tournament": " Admin",
            "set_tour_role": " Admin",
        }

        embed = discord.Embed(
            title=f"Interaction Logged",
            color=command_color.get(command_name, discord.Color.blurple()),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Command", value=f"`/{command_name}`", inline=True)
        embed.add_field(name="Category", value=category_map.get(command_name, " Unknown"), inline=True)
        embed.add_field(name="User", value=f"{interaction.user} (`{interaction.user.id}`)", inline=False)
        embed.add_field(name="Server", value=f"{interaction.guild} (`{interaction.guild_id}`)" if interaction.guild else "💬 Direct Message", inline=False)
        embed.add_field(name="Channel", value=f"{interaction.channel}" if interaction.guild else "DM", inline=False)
        embed.add_field(name="Type", value=str(interaction.type), inline=True)
        try:
            async with aiohttp.ClientSession() as session:
                webhook = discord.Webhook.from_url(DISCORD_LOGGING_WEBHOOK_URL, session=session)#type: ignore
                embed = discord.Embed(
                    title="Interaction Logged",
                    color=command_color.get(command_name, discord.Color.blurple()),
                    timestamp=discord.utils.utcnow()
                )
                embed.add_field(name="User", value=f"{interaction.user} (`{interaction.user.id}`)", inline=False)
                embed.add_field(name="Server", value=f"{interaction.guild} (`{interaction.guild_id}`)" if interaction.guild else "Direct Message", inline=False)
                embed.add_field(name="Command", value=interaction.data.get("name", "Unknown"), inline=False)#type: ignore
                embed.add_field(name="Type", value=str(interaction.type), inline=False)
                embed.add_field(name="Channel",value=f"{interaction.channel}" if interaction.guild else "DM",inline=False)
                await webhook.send(embed=embed)
        except Exception as e:
            logger.error(f"Failed to send to webhook: {e}")
        try:
            logger.info(f"Ensuring user {interaction.user.id} exists in DB")
            await self.ensure_user(interaction)
        except Exception as e:
            # Log but don't break the interaction
            logger.error(f"Error ensuring user in DB: {e}")


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

  

