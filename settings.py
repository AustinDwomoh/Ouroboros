import os, logging, pathlib, discord,traceback
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
ALLOWED_ID = [755872891601551511]
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
BEARER_TOKEN = os.getenv("BEARER_TOKEN")
X_API_KEY = os.getenv("X_API_KEY")
X_API_SECRET = os.getenv("X_API_SECRET")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN")
X_ACCESS_SECRET = os.getenv("X_ACCESS_SECRET")
MOVIE_BASE_URL = os.getenv("MOVIE_BASE_URL")
MOVIE_API_KEY = os.getenv("MOVIE_API_KEY")
H_BASE_URL = os.getenv("HANIME_BASE_URL")



class ErrorHandler:
    def __init__(self, log_file="data/errors.log"):
        """
        Initializes the ErrorHandler class.
        :param log_file: The file where logs will be stored.
        """
        self.log_file = log_file
        self.logger = logging.getLogger("Ouroboros")
        self.logger.setLevel(logging.INFO)

        if not self.logger.hasHandlers():  # Prevents duplicate handlers
            # Create a file handler
            file_handler = logging.FileHandler(self.log_file)
            file_handler.setLevel(logging.INFO)

            # Create a console handler
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)

            # Create a formatter and set it for both handlers
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            file_handler.setFormatter(formatter)
            console_handler.setFormatter(formatter)

            # Add handlers to the logger
            self.logger.addHandler(file_handler)
            self.logger.addHandler(console_handler)

    def handle_exception(self, exception):
        """
        Handles exceptions by logging the error message along with traceback.
        :param exception: The exception instance to be logged.
        """
        error_message = f"Exception occurred: {exception}\n{traceback.format_exc()}"
    
        with open(self.log_file, "a") as log_file:
            log_file.write(error_message + "\n")
        self.logger.error(error_message)

    

    






BASE_DIR = pathlib.Path(__file__).parent

CMDS_DIR = BASE_DIR / "cmds"
COGS_DIR = BASE_DIR / "cogs"
IMGS_DIR = BASE_DIR / "imgs"

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
