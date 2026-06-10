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
    async def make_message(self, msg, uid,c3=None) -> discord.Embed:
        """Helper function to create a consistent embed."""
        title, summary, body, footer = self.parse_announcement(msg.content)
        if c3:
            body += f"""\n\n⚠️ Announcement could not be sent in the server due to missing permissions or channels. 
            Please check your server settings.
            \n\nIf you want to receive announcements, please create a news channel or set a system channel and ensure the 
            bot has permission to send messages there."
                                """
        embed = discord.Embed(title=title, description=body, color=discord.Color.gold(),
                    timestamp=discord.utils.utcnow())
        embed.set_footer(text="Ouroboros Bot")
        if summary:
            embed.add_field(name="Summary", value=summary, inline=False)
            embed.set_footer(text=footer or f"Posted by {msg.author.display_name}")
        
        self.pending_previews[uid] = embed
        await msg.author.send(
                    "👀 **Announcement Preview**\n"
                    "Type `confirm` to publish or `cancel` to discard."
                )
        await msg.author.send(embed=embed)
        return embed
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
                self.pending_messages[uid] = message  # store original message
                await self.make_message(message, uid)
                self.pending_announcements.pop(uid)
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
                        try:
                            owner = await guild.fetch_member(guild.owner_id) #type: ignore
                        except discord.NotFound:
                            owner = await self.fetch_user(guild.owner_id) #type: ignore
                                                
                        # CASE A — announcement channels exist
                        if news_channels:
                            for ch in news_channels:
                                try:
                                    msg = await ch.send(embed=embed)
                                    await msg.publish()
                                except Exception as e:
                                    print(f"Publish failed in {ch.name}: {e}")
                            return

                        #case B — no suitable channels at all
                        #dm owner of the guild if we can't send the announcement in the guild
                         
                        elif guild.owner:
                            owner = guild.owner
                            original_message = self.pending_messages.get(uid)
                            Owner_DM_embed =  await self.make_message(original_message, uid,c3=True)  
                            try:
                                await owner.send(embed=Owner_DM_embed)
                                continue
                            except Exception as e:
                                print(f"Failed to DM owner of {guild.name}: {e}")
                        
                        # CASE C — fallback to system or current channel
                        else:
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

  

