"""
settings.py — Central configuration and utilities for the Discord bot.
Handles environment setup, DB connections, error logging, and notifications.
"""

import os,logging,pathlib,traceback,base64,resend,discord,psycopg2,asyncpg,ssl
from threading import Thread
from datetime import datetime
from dotenv import load_dotenv
import aiohttp
import asyncio

# ---------------------------
# Environment Loading
# ---------------------------
load_dotenv()
BASE_DIR = pathlib.Path(__file__).parent
LOG_BASE_DIR = BASE_DIR / "errors"

BOT_MODE = os.getenv("BOT_MODE", "production").strip().lower()
IS_PRODUCTION = BOT_MODE == "production"
IS_TESTING = BOT_MODE == "testing"

# ---------------------------
# Discord Credentials
# ---------------------------
DISCORD_TOKEN = os.getenv("TEST_DISCORD_TOKEN") if IS_TESTING else os.getenv("DISCORD_TOKEN")
CLIENT_ID = os.getenv("TEST_CLIENT_ID") if IS_TESTING else os.getenv("CLIENT_ID")
PUBLIC_KEY = os.getenv("TEST_PUBLIC_KEY") if IS_TESTING else os.getenv("PUBLIC_KEY")
CREATOR_ID = os.getenv("CREATOR")
ALLOWED_ID = [CREATOR_ID] if CREATOR_ID else []
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
# ---------------------------
# External APIs
# ---------------------------
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
BEARER_TOKEN = os.getenv("BEARER_TOKEN")
X_API_KEY = os.getenv("X_API_KEY")
X_API_SECRET = os.getenv("X_API_SECRET")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN")
X_ACCESS_SECRET = os.getenv("X_ACCESS_SECRET")
MOVIE_BASE_URL = os.getenv("MOVIE_BASE_URL")
MOVIE_API_KEY = os.getenv("MOVIE_API_KEY")
HIANIME_BASE_URL = os.getenv("HIANIME_BASE_URL")

# ---------------------------
# Database Config
# ---------------------------
PGHOST = os.getenv("PGHOST")
PGPORT = int(os.getenv("PGPORT", "5432"))
PGUSER = os.getenv("PGUSER")
PGPASSWORD = os.getenv("PGPASSWORD")
PGDATABASE = os.getenv("PGDATABASE")
SQLITE_DATA_DIR = os.getenv("SQLITE_DATA_DIR", "data")

# ---------------------------
# Paths
# ---------------------------
CMDS_DIR = BASE_DIR / "cmds"
COGS_DIR = BASE_DIR / "cogs"
IMGS_DIR = BASE_DIR / "imgs"
FONT_DIR = BASE_DIR / "fonts"
LOGS_DIR = BASE_DIR / "logs"
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(LOG_BASE_DIR, exist_ok=True)

# ---------------------------
# Logging
# ---------------------------
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "%(asctime)s - %(levelname)-8s - %(message)s"},
        "verbose": {"format": "%(asctime)s - %(levelname)-8s - %(module)s: %(message)s"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "DEBUG" if IS_TESTING else "INFO",
            "formatter": "standard",
        },
        "file": {
            "class": "logging.FileHandler",
            "filename": LOGS_DIR / "bot.log",
            "mode": "a",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "discord": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
        "bot": {"handlers": ["console", "file"], "level": "DEBUG" if IS_TESTING else "INFO"},
    },
}


logger = logging.getLogger("bot")

# ---------------------------
# Database Connectors
# ---------------------------

def create_pg_conn():
    """
    Blocking (synchronous) Postgres connection for scripts, migrations, etc.
    """
    if not all([PGHOST, PGUSER, PGPASSWORD, PGDATABASE]):
        raise RuntimeError("Postgres credentials missing in .env")
    return psycopg2.connect(
    host=PGHOST,
    port=PGPORT,
    sslmode="require",
    dbname=PGDATABASE,
    user=PGUSER,
    password=PGPASSWORD
)

async def create_async_pg_conn():
    """
    Asynchronous Postgres connection for bot runtime.
    """
    if not all([PGHOST, PGUSER, PGPASSWORD, PGDATABASE]):
        raise RuntimeError("Postgres credentials missing in .env")
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    return await asyncpg.connect(
     host=PGHOST,
    port=PGPORT,
    database=PGDATABASE,
    user=PGUSER,
    password=PGPASSWORD,
    ssl=ssl_context
)

async def ensure_user(user_id: int):
    """Ensure the user exists in the users table."""
    conn = await create_async_pg_conn()
    try:
        await conn.execute("""
            INSERT INTO users (user_id)
            VALUES ($1)
            ON CONFLICT (user_id) DO NOTHING;
        """, user_id)
    finally:
        await conn.close()
# ---------------------------
# Error Handling
# ---------------------------

class ErrorHandler:
    """
    Handles exception logging with Discord webhook notifications.
    Creates timestamped error logs in /errors/YYYY-MM-DD/.
    Sends rich embeds to Discord webhook for production errors.
    """

    def __init__(self):
        """
        Initialize the error handler.
        
        Args:
            log_base_dir: Base directory for error logs
        """
        self.webhook_url = DISCORD_WEBHOOK_URL
        self.log_base_dir = LOG_BASE_DIR
        self.notify = True  # TODO: Set to False for local testing, True for production
        
        # Create log directory
        os.makedirs(self.log_base_dir, exist_ok=True)
        
        # Warn if webhook is not configured
        if self.notify and not self.webhook_url:
            print("[WARNING] DISCORD_ERROR_WEBHOOK_URL not set. Error notifications disabled.")
            self.notify = False

    def handle(self, error: Exception, context: str = ""):
        """
        Handle an exception by logging and optionally notifying via Discord webhook.
        
        Args:
            error: The exception that occurred
            context: Additional context about where/why the error occurred
        """
        now = datetime.now()
        folder = self.log_base_dir / now.strftime("%Y-%m-%d")
        folder.mkdir(exist_ok=True)
        
        # Create error log file
        filename = f"error_{now.strftime('%H-%M-%S')}.txt"
        path = folder / filename

        # Format error message
        error_traceback = traceback.format_exc()
        msg = (
            f"Timestamp: {now}\n"
            f"Context: {context}\n"
            f"Exception: {str(error)}\n\n"
            f"Traceback:\n{error_traceback}\n"
        )

        # Write to file
        path.write_text(msg, encoding="utf-8")
        
        # Log to console
        print(f"[ERROR] {context}: {error}")

        # Send Discord notification
        if self.notify and self.webhook_url:
            self._notify_discord_async(error, context, error_traceback, path, now)

    def _notify_discord_async(self, error: Exception, context: str, traceback_text: str, log_path, timestamp: datetime):
        """Start async Discord notification in a separate thread."""
        Thread(
            target=self._run_async_notify,
            args=(error, context, traceback_text, log_path, timestamp),
            daemon=True
        ).start()

    def _run_async_notify(self, error: Exception, context: str, traceback_text: str, log_path, timestamp: datetime):
        """Run async Discord notification in new event loop."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(
                self._send_discord_webhook(error, context, traceback_text, log_path, timestamp)
            )
        except Exception as e:
            self._log_notification_failure(e)
        finally:
            loop.close()

    async def _send_discord_webhook(self, error: Exception, context: str, traceback_text: str, log_path, timestamp: datetime):
        """
        Send error notification to Discord webhook with embed and file attachment.
        
        Args:
            error: The exception object
            context: Context string
            traceback_text: Full traceback string
            log_path: Path to the log file
            timestamp: When the error occurred
        """
        try:
            # Create embed
            embed = discord.Embed(
                title="🚨 Bot Error Detected",
                description=f"**Context:** {context or 'No context provided'}",
                color=discord.Color.red(),
                timestamp=timestamp
            )
            
            # Add error details
            error_type = type(error).__name__
            error_message = str(error) or "No error message"
            
            embed.add_field(
                name="❌ Exception Type",
                value=f"`{error_type}`",
                inline=True
            )
            
            # Truncate error message if too long
            if len(error_message) > 1024:
                error_message = error_message[:1021] + "..."
            
            embed.add_field(
                name="📝 Error Message",
                value=f"```\n{error_message}\n```",
                inline=False
            )
            
            # Add truncated traceback (Discord embed field limit is 1024 chars)
            traceback_lines = traceback_text.split('\n')
            
            # Get last meaningful lines of traceback (most relevant)
            relevant_traceback = '\n'.join(traceback_lines[-15:])
            if len(relevant_traceback) > 1000:
                relevant_traceback = "..." + relevant_traceback[-997:]
            
            embed.add_field(
                name="🔍 Traceback (last 15 lines)",
                value=f"```python\n{relevant_traceback}\n```",
                inline=False
            )
            
            # Add log file info
            embed.add_field(
                name="📁 Log File",
                value=f"`{log_path.parent.name}/{log_path.name}`",
                inline=False
            )
            
            embed.set_footer(text="Error Handler • Check logs for full details")
            
            # Prepare webhook payload
            async with aiohttp.ClientSession() as session:
                webhook = discord.Webhook.from_url(self.webhook_url, session=session)
                
                # Send with file attachment if log exists and is under Discord's 8MB limit
                if log_path.exists() and log_path.stat().st_size < 8_000_000:
                    with open(log_path, 'rb') as f:
                        file = discord.File(f, filename=log_path.name)
                        await webhook.send(
                            embed=embed,
                            file=file,
                            username="Ouroboros Logger",
                            avatar_url="https://cdn.discordapp.com/emojis/1234567890.png"  # Optional: Add custom avatar
                        )
                else:
                    # File too large or doesn't exist, send embed only
                    await webhook.send(
                        embed=embed,
                        username="Ouroboros Logger"
                    )
                    
        except discord.HTTPException as e:
            self._log_notification_failure(e)
        except aiohttp.ClientError as e:
            self._log_notification_failure(e)
        except Exception as e:
            self._log_notification_failure(e)

    def _log_notification_failure(self, error: Exception):
        """Log failures in the notification system itself."""
        failure_log = self.log_base_dir / "notification_failures.txt"
        try:
            with open(failure_log, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now()} - Failed to send Discord notification: {error}\n")
                f.write(f"{traceback.format_exc()}\n\n")
        except Exception as e:
            # Last resort: print to console if we can't even log the failure
            print(f"[CRITICAL] Failed to log notification failure: {e}")

    def help_embed(self) -> discord.Embed:
        """
        Create a user-facing error embed for Discord interactions.
        
        Returns:
            discord.Embed: Embed to show users when an error occurs
        """
        embed = discord.Embed(
            title="⚠️ An Error Occurred",
            description="Something went wrong while processing your request. The error has been logged and the development team has been notified.",
            color=discord.Color.red(),
        )
        
        embed.add_field(
            name="🔄 What to do next",
            value=(
                "• Try your command again\n"
                "• Check if your input was correct\n"
                "• Contact support if the issue persists"
            ),
            inline=False,
        )
        
        embed.add_field(
            name="📞 Need Help?",
            value="[Contact Inphinithy](https://discord.com/users/755872891601551511)",
            inline=False,
        )
        
        embed.set_footer(text="Error handlers are monitoring this issue")
        embed.timestamp = datetime.now()
        
        return embed