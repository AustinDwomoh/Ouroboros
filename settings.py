import pathlib, discord,json, os,logging
from dotenv import load_dotenv

# ---------------------------
# Environment Loading
# ---------------------------
load_dotenv()
BASE_DIR = pathlib.Path(__file__).parent
LOG_BASE_DIR = BASE_DIR / "logs"

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
DISCORD_HANDLER_WEBHOOK_URL = os.getenv("DISCORD_HANDLER_WEBHOOK_URL")
DISCORD_INTERACTION_WEBHOOK_URL = os.getenv("DISCORD_INTERACTION_WEBHOOK_URL")
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

import json

with open("commands.json", "r") as f:
    COMMANDS = json.load(f)["commands"]

# build the two dicts dynamically
COLOR_MAP = {
    name: getattr(discord.Color, data["color"])()
    for name, data in COMMANDS.items()
}

CATEGORY_MAP = {
    name: data["category"]
    for name, data in COMMANDS.items()
}