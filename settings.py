import os, pathlib, discord,traceback,requests,json
import os,logging,pathlib,traceback,discord
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
ALLOWED_ID = [int(CREATOR_ID)] if CREATOR_ID else []
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
H_BASE_URL = os.getenv("HIANIME_BASE_URL")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

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
        self.notify = False if BOT_MODE == "testing" else True  # TODO: Set to False for local testing, True for production
        
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

        if self.notify:
            Thread(target=self.send_discord_alert, args=(error, context, path)).start()

    def send_discord_alert(self, error, context, file_path):
        """
        Sends a formatted embed to a Discord webhook with error details.
        Runs in a separate thread to avoid blocking.
        """
        try:
            # Build the embed
            embed = {
                "title": "🚨 Bot Error Alert",
                "color": 0xFF0000,
                "fields": [
                    {"name": "Context", "value": context or "N/A", "inline": False},
                    {"name": "Error", "value": str(error)[:1024], "inline": False},
                ],
                "footer": {"text": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
            }

            # Attach a truncated traceback (Discord has a 6000 char limit)
            tb = traceback.format_exc()
            if tb:
                embed["fields"].append({
                    "name": "Traceback",
                    "value": f"```{tb[-1800:]}```",  # keep last part for relevance
                    "inline": False
                })

            # Send the webhook message
            data = {
                "username": "Ouroboros Error Bot",
                "embeds": [embed],
            }

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Include full log as a text file
            files = {"file": (os.path.basename(file_path), content)}

            # FIXED: Use json.dumps() instead of str() to create valid JSON
            response = requests.post(
                DISCORD_WEBHOOK_URL, 
                data={"payload_json": json.dumps(data)}, 
                files=files
            )

            if response.status_code >= 300:
                print(f"[ErrorHandler] Discord alert failed: {response.status_code} {response.text}")

        except Exception as e:
            fallback_path = os.path.join(LOG_BASE_DIR, "webhook_failures.txt")
            with open(fallback_path, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now()} - Failed to send Discord alert: {str(e)}\n")

    def _run_async_notify(self, error: Exception, context: str, traceback_text: str, log_path, timestamp: datetime):
        """Run async Discord notification in new event loop."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(
                self._send_discord_webhook(error, context, traceback_text, log_path, timestamp)
            )
        finally:
            loop.close()

    async def _send_discord_webhook(self, error: Exception, context: str, traceback_text: str, log_path, timestamp: datetime):
        """
        Returns a Discord embed for user-facing error display.
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
