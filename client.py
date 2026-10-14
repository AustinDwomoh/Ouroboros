import asyncpg, discord, logging, aiohttp
from discord import app_commands
from discord.ext import commands
from rimiru import Rimiru
from settings import *
from handle import handler
from dbmanager import UserManager


# Logging setup
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("Ouroboros")

# Intents configuration
intents = discord.Intents.default()
intents.message_content = True
intents.guild_messages = True
intents.members = True

class OuroborosTree(app_commands.CommandTree):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Resolve the caller's users.id before any slash command or autocomplete runs."""
        if interaction.user.bot:
            return True
        try:
            await UserManager.uid(interaction)
        except Exception as e:
            # Commands resolve lazily via UserManager.uid, so don't block them here
            handler.error_handle(e, context="OuroborosTree.interaction_check")
        return True


class Client(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents, tree_cls=OuroborosTree)
        self.synced = False
        self.db_pool: asyncpg.Pool | None = None
        self.pending_announcements = {}
        self.pending_previews = {}
        self.pending_messages = {}
        self._warned_missing_interaction_webhook = False


    async def setup_hook(self):
        self.db = await Rimiru.shion() 
        await self.load_commands()
        await self.load_cogs()
        self.add_listener(self.on_interaction, "on_interaction") 
        handler.log_task("BOT", "Loaded commands and cogs", level="SUCCESS")

        if not self.synced:
            try:
                synced = await self.tree.sync()
                handler.log_task("BOT", f"Slash commands synced successfully: {len(synced)} commands", level="SUCCESS")
                self.synced = True
            except Exception as e:
                handler.log_task("BOT", f"Failed to sync slash commands: {e}", level="ERROR")
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
            
            if uid in ALLOWED_ID:
                if content == "$nuke":
                    for guild in self.guilds:
                        await guild.leave()
                        await message.author.send(f"Left guild: {guild.name}")
                    return
                if content == "$sync":
                    try:
                        synced = await self.tree.sync()
                        await message.channel.send(f"✅ Synced {len(synced)} commands.")
                    except Exception as e:
                        await message.channel.send(f"❌ Sync failed: {e}")
                    return
                if content == "$clearcache":
                    UserManager.forget_discord_user()
                    await message.channel.send("🧹 User cache cleared.")
                    return
               
            await self.process_commands(message)
            
        except Exception as e:
            handler.error_handle(e, context="$godoflies:on_message")
    
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
        handler.log_task("BOT", "Ouroboros is ready", level="SUCCESS")
        
        inphinithy = self.get_user(ALLOWED_ID[0])
        if inphinithy:
            try:
                embed = discord.Embed(
                    title="Ouroboros Startup",
                    description="The bot has successfully started and is ready to serve!",
                    color=discord.Color.green(),
                    timestamp=discord.utils.utcnow()
                )
                embed.add_field(
                    name="Admin Commands",
                    value=(
                        "`$nuke` — leave all guilds\n"
                        "`$sync` — sync slash commands\n"
                        "`$clearcache` — clear user cache\n"
                
                    ),
                    inline=False
                )
                await inphinithy.send("Ouroboros is now online! Here's a summary of the admin commands:")
                await inphinithy.send(embed=embed)
                handler.log_task("BOT", "Startup DM sent to creator", level="SUCCESS")
            except Exception as e:
                handler.error_handle(e, context="on_ready startup DM")
        else:
            handler.log_task("BOT", "Creator user not found, cannot send startup DM", level="WARNING")
       

  
    async def on_interaction(self, interaction: discord.Interaction):
        """Handle all interactions and ensure user exists in database."""
        # Log the interaction
        #print(f"[Interaction] Received interaction from {interaction.user} with ID {interaction.id}")
        #logger.info(f"[Interaction] Received interaction from {interaction.user} with ID {interaction.id}")
        if interaction.user.bot:
            #logger.info(f"Interaction from bot ignored: {interaction.user}")
            return
        
        # Run ensure_user in background without blocking the interaction
        
        command_name = interaction.data.get("name", "Unknown") if interaction.data else "Unknown"
       
        embed = discord.Embed(
            title=f"Interaction Logged",
            color=COLOR_MAP.get(command_name, discord.Color.blurple()),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Command", value=f"`/{command_name}`", inline=True)
        embed.add_field(name="Category", value=CATEGORY_MAP.get(command_name, " Unknown"), inline=True)
        embed.add_field(name="User", value=f"{interaction.user} (`{interaction.user.id}`)", inline=False)
        embed.add_field(name="Server", value=f"{interaction.guild} (`{interaction.guild_id}`)" if interaction.guild else "💬 Direct Message", inline=False)
        embed.add_field(name="Channel", value=f"{interaction.channel}" if interaction.guild else "DM", inline=False)
        if not DISCORD_INTERACTION_WEBHOOK_URL:
            if not self._warned_missing_interaction_webhook:
                logger.warning("DISCORD_INTERACTION_WEBHOOK_URL not set. Interaction logging disabled.")
                self._warned_missing_interaction_webhook = True
        else:
            try:
                async with aiohttp.ClientSession() as session:
                    webhook = discord.Webhook.from_url(DISCORD_INTERACTION_WEBHOOK_URL, session=session)#type: ignore
                    embed = discord.Embed(
                        title="Interaction Logged",
                        color=COLOR_MAP.get(command_name, discord.Color.blurple()),
                        timestamp=discord.utils.utcnow()
                    )
                    embed.add_field(name="User", value=f"{interaction.user} (`{interaction.user.id}`)", inline=False)
                    embed.add_field(name="Server", value=f"{interaction.guild} (`{interaction.guild_id}`)" if interaction.guild else "Direct Message", inline=False)
                    embed.add_field(name="Command", value=interaction.data.get("name", "Unknown"), inline=False)#type: ignore
                    embed.add_field(name="Channel",value=f"{interaction.channel}" if interaction.guild else "DM",inline=False)
                    await webhook.send(embed=embed)
            except Exception as e:
                handler.error_handle(e, context="Failed to send to webhook in on_interaction")
        try:
            # Slash commands are already resolved by OuroborosTree.interaction_check; this covers
            # buttons/selects so Discord-keyed tables (levels, game_scores) always have a users row.
            await UserManager.resolve_discord_user(interaction.user)
        except Exception as e:
            handler.error_handle(e, context="Error ensuring user in DB during on_interaction")


    async def load_commands(self):
        """Load command files from the commands directory."""
        for cmd_file in CMDS_DIR.glob("*.py"):
            if cmd_file.name != "__init__.py":
                try:
                    await self.load_extension(f"cmds.{cmd_file.name[:-3]}")
                    handler.log_task("BOT", f"Loaded command: {cmd_file.name}", level="SUCCESS")
                except Exception as e:
                    handler.error_handle(e, context=f"Failed to load command {cmd_file.name}")

    async def load_cogs(self):
        """Load cog files from the cogs directory."""
        for cog_file in COGS_DIR.glob("*.py"):
            if cog_file.name != "__init__.py":
                try:
                    await self.load_extension(f"cogs.{cog_file.name[:-3]}")
                    handler.log_task("BOT", f"Loaded cog: {cog_file.name}", level="SUCCESS")
                except Exception as e:
                    handler.error_handle(e, context=f"Failed to load cog {cog_file.name}")

    # Error handler for unknown commands or permissions
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            await ctx.send("Please specify a valid command.")
        elif isinstance(error, commands.CheckFailure):
            await ctx.send("You do not have permission to use this command.")

  

