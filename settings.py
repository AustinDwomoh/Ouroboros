import os, pathlib, discord,traceback,requests,json
from threading import Thread
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


state = os.getenv("BOT_MODE", "production").strip().lower()
# Accessing environment variables
if state == "testing":
    DISCORD_TOKEN = os.getenv("TEST_DISCORD_TOKEN")
    CLIENT_ID = os.getenv("TEST_CLIENT_ID")
    PUBLIC_KEY = os.getenv("TEST_PUBLIC_KEY")
else:
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
    CLIENT_ID = os.getenv("CLIENT_ID")
    PUBLIC_KEY = os.getenv("PUBLIC_KEY")


CREATOR_ID = os.getenv("CREATOR")
ALLOWED_ID = [CREATOR_ID]
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


BASE_DIR = pathlib.Path(__file__).parent

CMDS_DIR = BASE_DIR / "cmds"
COGS_DIR = BASE_DIR / "cogs"
IMGS_DIR = BASE_DIR / "imgs"
FONT_DIR = BASE_DIR / "fonts"
# Load logging configuration from file
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(asctime)s - %(levelname)-10s -%(module)-15s:%(message)s"
        },
        "standard": {"format": "%(asctime)s - %(levelname)-10s - %(message)s"},
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
        "console2": {
            "level": "WARNING",
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
        "file": {
            "level": "INFO",
            "class": "logging.FileHandler",
            "filename": "logs/infos.log",
            "mode": "w",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "bot": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "discord": {
            "handlers": ["console2", "file"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

LOG_BASE_DIR =BASE_DIR / "errors"

class ErrorHandler:
    """
    Handles exceptions by logging error details to timestamped daily files.
    Optionally sends asynchronous Discord webhook notifications.
    Also provides a Discord embed for user-friendly error feedback.
    """

    def __init__(self):
        self.notify = True #if state == "production" else False
        os.makedirs(LOG_BASE_DIR, exist_ok=True)

    def handle(self, error, context=""):
        """
        Logs error details and notifies via Discord if enabled.
        """
        now = datetime.now()
        day_folder = now.strftime("%Y-%m-%d")
        time_stamp = now.strftime("%H-%M-%S")

        folder_path = os.path.join(LOG_BASE_DIR, day_folder)
        os.makedirs(folder_path, exist_ok=True)
        file_path = os.path.join(folder_path, f"error_{time_stamp}.txt")

        error_message = (
            f"Timestamp: {now}\n"
            f"Context: {context}\n"
            f"Exception: {str(error)}\n\n"
            f"Traceback:\n{traceback.format_exc()}\n"
        )

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(error_message)

        if self.notify:
            Thread(target=self.send_discord_alert, args=(error, context, file_path)).start()

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

    def help_embed(self):
        """
        Returns a Discord embed for user-facing error display.
        """
        embed = discord.Embed(
            title="Error Handling",
            description="An error occurred. Please contact the admin if it persists:\n**Inphinithy**",
            color=0xFF0000
        )
        embed.add_field(
            name="Contact",
            value="[Send a DM](https://discord.com/users/755872891601551511)",
            inline=False
        )
        return embed
