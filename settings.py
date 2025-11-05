"""
settings.py — Central configuration and utilities for the Discord bot.
Handles environment setup, DB connections, error logging, and notifications.
"""

import os,logging,pathlib,traceback,base64,resend,discord,psycopg2,asyncpg
from threading import Thread
from datetime import datetime
from dotenv import load_dotenv


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
ALLOWED_IDS = [CREATOR_ID] if CREATOR_ID else []

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
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL")
RESEND_API = os.getenv("RESEND_API")

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

logging.config.dictConfig(LOGGING_CONFIG)
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
        host=PGHOST, port=PGPORT, user=PGUSER, password=PGPASSWORD, dbname=PGDATABASE
    )


async def create_async_pg_conn():
    """
    Asynchronous Postgres connection for bot runtime.
    """
    if not all([PGHOST, PGUSER, PGPASSWORD, PGDATABASE]):
        raise RuntimeError("Postgres credentials missing in .env")
    return await asyncpg.connect(
        host=PGHOST, port=PGPORT, user=PGUSER, password=PGPASSWORD, database=PGDATABASE
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
    Handles exception logging and optional email notifications.
    Creates timestamped error logs in /errors/YYYY-MM-DD/.
    """

    NOTIFY_EMAIL = "dwomohaustin14@gmail.com"

    def __init__(self):
        self.notify = IS_PRODUCTION
        os.makedirs(LOG_BASE_DIR, exist_ok=True)

    def handle(self, error: Exception, context: str = ""):
        now = datetime.now()
        folder = LOG_BASE_DIR / now.strftime("%Y-%m-%d")
        folder.mkdir(exist_ok=True)
        path = folder / f"error_{now.strftime('%H-%M-%S')}.txt"

        msg = (
            f"Timestamp: {now}\n"
            f"Context: {context}\n"
            f"Exception: {str(error)}\n\n"
            f"Traceback:\n{traceback.format_exc()}\n"
        )

        path.write_text(msg, encoding="utf-8")
        logger.error(f"[ERROR] {context}: {error}")

        if self.notify:
            self._notify_admin_async(path)

    def _notify_admin_async(self, file_path):
        Thread(target=self._send_email_with_attachment, args=("Bot Error", "See log file.", self.NOTIFY_EMAIL, file_path)).start()

    def help_embed(self):
        embed = discord.Embed(
            title="Bot Error",
            description="An error occurred. Please contact **Inphinithy** for support.",
            color=0xE53935,
        )
        embed.add_field(
            name="Contact",
            value="[DM Inphinithy](https://discord.com/users/755872891601551511)",
            inline=False,
        )
        return embed

    def _send_email_with_attachment(self, subject, body, to_email, file_path):
        resend.api_key = RESEND_API
        attachments = []
        if file_path.exists():
            encoded = base64.b64encode(file_path.read_bytes()).decode("ascii")
            attachments = [{"filename": file_path.name, "content": encoded, "disposition": "attachment"}]

        try:
            resend.Emails.send({
                "from": DEFAULT_FROM_EMAIL,
                "to": [to_email],
                "subject": subject,
                "text": body,
                "attachments": attachments,
            })
        except Exception as e:
            with open(LOG_BASE_DIR / "notify_failures.txt", "a", encoding="utf-8") as f:
                f.write(f"{datetime.now()} - Failed to notify admin: {e}\n")
