import os, logging, pathlib, discord,traceback,os,resend,base64
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
DEFAULT_FROM_EMAIL=os.getenv("DEFAULT_FROM_EMAIL") 
RESEND_API=os.getenv("RESEND_API")


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
    Optionally sends asynchronous email notifications with the log attached.
    Also provides a Discord embed for user-friendly error feedback.

    Attributes:
        NOTIFY_EMAIL (str): Email address to receive error notifications.
        notify (bool): Whether to send email notifications on errors.

    Methods:
        handle(error, context=""): Logs error info and triggers notification if enabled.
        notify_admin(file_path): Sends an email with the error log attachment asynchronously.
        help_embed(): Returns a Discord embed for displaying error contact info.
    """

    NOTIFY_EMAIL = 'dwomohaustin14@gmail.com'
    
    def __init__(self, notify=True):
        self.notify = notify
       
        os.makedirs(LOG_BASE_DIR, exist_ok=True)

    def handle(self, error, context=""):
        """
        Handles exceptions by logging error details to a timestamped file 
        and optionally notifying the admin via email.

        Args:
            error (Exception): The caught exception.
            context (str): Optional context string describing where the error occurred.
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
            self.notify_admin(file_path)

    def notify_admin(self, file_path):
        """
        Sends an email to the admin with the error log attached.
        Runs asynchronously in a separate thread.

        Args:
            file_path (str): Path to the error log file to attach.
        """
        subject = '[ALERT] Discord Bot Error'
        body = 'An error occurred. Please see the attached log file.'

        Thread(
            target=self.send_email_with_attachment,
            kwargs={
                "subject": subject,
                "body": body,
                "to_email": self.NOTIFY_EMAIL,
                "file_path": file_path,
            },
        ).start()

    def help_embed(self):
        """
        Returns a Discord embed with help information.
        This is meant to be sent to users when an error occurs.
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


    def send_email_with_attachment(self,subject, body, to_email, file_path=None, from_email=None, html_content=None):
        """
        Sends an email using the Resend API, optionally with an attachment and HTML content.
        Falls back to logging errors in a local file if the email fails to send.

        Args:
            subject (str): Subject line of the email.
            body (str): Plain text body of the email.
            to_email (str or list): Recipient email address(es).
            file_path (str, optional): Path to a file to attach.
            from_email (str, optional): Sender's email address. Defaults to settings.DEFAULT_FROM_EMAIL.
            html_content (str, optional): HTML content of the email. If provided, overrides plain text body.
        """
        from_email = from_email or DEFAULT_FROM_EMAIL
        fallback_path = os.path.join(LOG_BASE_DIR, "notify_failures.txt")
        resend.api_key = RESEND_API  # Ensure the Resend API key is set

        if not isinstance(to_email, (list, tuple)):
            to_email = [to_email]

        # Prepare attachments payload for Resend
        attachments = []
        if file_path and os.path.isfile(file_path):
            with open(file_path, "rb") as f:
                file_data = f.read()
                encoded_content = base64.b64encode(file_data).decode("ascii")
                attachments.append({
                    "filename": os.path.basename(file_path),
                    "content": encoded_content,
                    "disposition": "attachment",
                    
                })

        try:
            resend.Emails.send({
                "from": from_email,
                "to": to_email,
                "subject": subject,
                **({"html": html_content} if html_content else {}),
                **({"text": body} if not html_content else {}),
                **({"attachments": attachments} if attachments else {}),
            })
        except Exception as e:
            os.makedirs(os.path.dirname(fallback_path), exist_ok=True)
            with open(fallback_path, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now()} - Failed to notify admin: {str(e)}\n")
          


