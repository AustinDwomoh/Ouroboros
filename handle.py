import os, json, logging, pathlib, traceback, requests, discord
from threading import Thread
from datetime import datetime

# imported from your settings
from settings import (
    DISCORD_HANDLER_WEBHOOK_URL,
    DISCORD_INTERACTION_WEBHOOK_URL,
    LOG_BASE_DIR,
    BOT_MODE,
)

logger = logging.getLogger("OuroborosHandler")
class OuroborosHandler:
    """
    Central handler for Ouroboros.
    
    - handle()   → exceptions, error logs, error webhook
    - log_task() → operational events (task start/complete/skip), log webhook
    """

    LEVEL_META = {
        "INFO":    {"icon": "🔵", "color": 0x5865F2},
        "SUCCESS": {"icon": "✅", "color": 0x57F287},
        "WARNING": {"icon": "⚠️", "color": 0xFEE75C},
        "SKIP":    {"icon": "⏭️", "color": 0x95A5A6},
        "ERROR":   {"icon": "🚨", "color": 0xFF0000},
    }

    def __init__(self):
        self.error_webhook = DISCORD_HANDLER_WEBHOOK_URL
        self.log_webhook = DISCORD_INTERACTION_WEBHOOK_URL
        self.log_base_dir = LOG_BASE_DIR
        self.notify = BOT_MODE != "testing"

        os.makedirs(self.log_base_dir, exist_ok=True)

        if self.notify and not self.error_webhook:
            logger.warning("DISCORD_HANDLER_WEBHOOK_URL not set. Error notifications disabled.")
        if self.notify and not self.log_webhook:
            logger.warning("DISCORD_INTERACTION_WEBHOOK_URL not set. Task log notifications disabled.")

    # ------------------------------------------------------------------
    # ERROR HANDLING  (unchanged from ErrorHandler)
    # ------------------------------------------------------------------

    def error_handle(self, error: Exception, context: str = ""):
        """
        Handle an exception — log to file, print to console, notify via
        error webhook (production only).
        """
        now = datetime.now()
        folder = self.log_base_dir / now.strftime("%Y-%m-%d")
        folder.mkdir(exist_ok=True)

        filename = f"error_{now.strftime('%H-%M-%S')}.txt"
        path = folder / filename

        error_traceback = traceback.format_exc()
        msg = (
            f"Timestamp: {now}\n"
            f"Context: {context}\n"
            f"Exception: {str(error)}\n\n"
            f"Traceback:\n{error_traceback}\n"
        )

        path.write_text(msg, encoding="utf-8")
        logger.error(f"{context}: {error}")

        if self.notify and self.error_webhook:
            Thread(target=self._send_error_webhook, args=(error, context, path)).start()

    def _send_error_webhook(self, error: Exception, context: str, file_path: pathlib.Path):
        """Send a rich error embed + log file attachment to the error webhook."""
        try:
            embed = {
                "title": "🚨 Bot Error Alert",
                "color": 0xFF0000,
                "fields": [
                    {"name": "Context", "value": context or "N/A", "inline": False},
                    {"name": "Error",   "value": str(error)[:1024], "inline": False},
                ],
                "footer": {"text": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
            }

            tb = traceback.format_exc()
            if tb:
                embed["fields"].append({
                    "name": "Traceback",
                    "value": f"```{tb[-1800:]}```",
                    "inline": False,
                })

            data = {"username": "Ouroboros Error Bot", "embeds": [embed]}

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            files = {"file": (os.path.basename(file_path), content)}
            response = requests.post(
                self.error_webhook,#type: ignore
                data={"payload_json": json.dumps(data)},
                files=files,
            )

            if response.status_code >= 300:
                logger.error(f"[OuroborosHandler] Error webhook failed: {response.status_code} {response.text}")

        except Exception as e:
            fallback = self.log_base_dir / "webhook_failures.txt"
            with open(fallback, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now()} - Failed to send error alert: {str(e)}\n")

    def get_error_embed(self) -> discord.Embed:
        """
        Returns a user-facing Discord embed for command error responses.
        Call this when you want to surface a friendly error message in chat.
        """
        embed = discord.Embed(
            title="⚠️ An Error Occurred",
            description=(
                "Something went wrong while processing your request. "
                "The error has been logged and the development team has been notified."
            ),
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

    # ------------------------------------------------------------------
    # TASK / OPERATIONAL LOGGING  (new)
    # ------------------------------------------------------------------

    def log_task(self, context: str, message: str, level: str = "INFO"):
        """
        Log an operational event.
        Replaces print() calls for task lifecycle messages.

        Levels: INFO | SUCCESS | WARNING | SKIP

        Usage:
            handler.log_task("UPDATER", "Updating 5 series...")
            handler.log_task("UPDATER", "Complete: 5 updated, 0 failed", level="SUCCESS")
            handler.log_task("UPDATER", "No series need updating", level="SKIP")
        """
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
        level = level.upper()

        print(f"[{level}] [{context}] {message}")

        # Append to daily tasks log
        folder = self.log_base_dir / now.strftime("%Y-%m-%d")
        folder.mkdir(exist_ok=True)
        log_file = folder / "tasks.log"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"{timestamp} [{level}] [{context}] {message}\n")

        if self.notify and self.log_webhook:
            Thread(target=self._send_task_webhook, args=(context, message, level, now)).start()

    def _send_task_webhook(self, context: str, message: str, level: str, timestamp: datetime):
        """Send a lightweight embed to the logging webhook."""
        try:
            meta = self.LEVEL_META.get(level, self.LEVEL_META["INFO"])
            embed = {
                "title": f"{meta['icon']} {context}",
                "description": message,
                "color": meta["color"],
                "footer": {"text": timestamp.strftime("%Y-%m-%d %H:%M:%S")},
            }
            response = requests.post(
                self.log_webhook,#type: ignore
                json={"username": "Ouroboros Logger", "embeds": [embed]},
            )
            if response.status_code >= 300:
                logger.error(f"[OuroborosHandler] Log webhook failed: {response.status_code} {response.text}")

        except Exception as e:
            fallback = self.log_base_dir / "webhook_failures.txt"
            with open(fallback, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now()} - Failed to send task log: {str(e)}\n")


# Global instance — import this everywhere
handler = OuroborosHandler()