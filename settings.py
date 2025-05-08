import os, logging, pathlib, discord,traceback,os,smtplib
from datetime import datetime
from dotenv import load_dotenv
from email.message import EmailMessage
import re
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
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS") 
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")  



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



class ErrorHandler:
    def __init__(self, log_dir="errors"):
        """
        Initializes the ErrorHandler class.
        :param log_dir: The directory where logs will be stored.
        """
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)  # Ensure log directory exists

        # Set up logging
        self.logger = logging.getLogger("Ouroboros")
        self.logger.setLevel(logging.INFO)

        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

        # Avoid adding duplicate handlers
        if not self.logger.handlers:
            # File handler
            file_handler = logging.FileHandler(self.get_log_file())
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)

            # Console handler
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)


    def get_log_file(self):
        """Generates a log file name based on the current date."""
        date_str = datetime.now().strftime("%Y-%m-%d")
        return os.path.join(self.log_dir, f"{date_str}.txt")
    

    def handle_exception(self, exception):
        """
        Handles exceptions by logging the error message along with traceback.
        :param exception: The exception instance to be logged.
        """
        error_message = f"Exception occurred on {datetime.now()}:\n{exception}\n{traceback.format_exc()}"
        log_file_path = self.get_log_file()

        # Write to file
        with open(log_file_path, "a") as log_file:
            log_file.write(error_message + "\n")
        
        # Log to console
        self.logger.error(error_message)
        self.send_error_log(EMAIL_ADDRESS,EMAIL_PASSWORD)

    def help_embed(self):
        """Returns a Discord embed with help information."""
        embed = discord.Embed(
            title="Error Handling",
            description="If an error occured feel free to let me know, please contact:\n**Inphinithy**",
            color=0xFF0000
        )
        embed.add_field(
            name="Contact",
            value="[Send a DM](https://discord.com/users/755872891601551511)",
            inline=False
        )
        return embed


    def send_error_log(self, email_address, email_password):
        """
        Sends the latest error log file via email.
        :param email_address: Sender's email address.
        :param email_password: Sender's email password.
        """
        if state != "testing":
            log_file_path = self.get_log_file()
            if not os.path.exists(log_file_path):
                return

            msg = EmailMessage()
            msg["From"] = email_address
            msg["To"] = email_address  # Send to self or an admin
            msg["Subject"] = f"Error Log - {datetime.now().strftime('%Y-%m-%d')}"
            msg.set_content("Please find the attached error log.")

            # Attach the log file
            try:
                with open(log_file_path, "rb") as f:
                    msg.add_attachment(f.read(), maintype="application", subtype="txt", filename=os.path.basename(log_file_path))
            except FileNotFoundError:
                return

            # Send email
            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls()
                server.login(email_address, email_password)
                server.send_message(msg)
        

