# ============================================================================ #
# MODULE: task_schedule.py
# Keeps periodic tasks on their schedule across restarts.
#
# discord.ext.tasks loops run their first iteration as soon as they start, so every deploy
# (which restarts the bot) would fire them again, e.g. re-sending everyone's media reminders.
# Each task's last run is stored in the DB instead; on startup a loop sleeps until it's
# actually due.
# ============================================================================ #
from datetime import datetime, timedelta, timezone

import discord

from handle import handler
from rimiru import Rimiru

_TABLE = """
CREATE TABLE IF NOT EXISTS bot_task_runs (
    name TEXT PRIMARY KEY,
    last_run TIMESTAMPTZ NOT NULL
)
"""


async def wait_until_due(name: str, interval: timedelta) -> None:
    """Sleep until `interval` has passed since the task last ran.

    A task with no record yet counts as having just run: shipping this must not trigger a
    round of notifications either. Call from a loop's before_loop.
    """
    conn = await Rimiru.shion()
    async with conn.pool.acquire() as connection:
        await connection.execute(_TABLE)
        last_run = await connection.fetchval(
            """
            INSERT INTO bot_task_runs (name, last_run) VALUES ($1, now())
            ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
            RETURNING last_run
            """,
            name,
        )

    due = last_run + interval
    now = datetime.now(timezone.utc)
    if due > now:
        handler.log_task(
            context="SCHEDULE",
            message=f"{name}: next run {due.isoformat(timespec='minutes')} (last {last_run.isoformat(timespec='minutes')})",
            level="Info",
        )
        await discord.utils.sleep_until(due)


async def mark_ran(name: str) -> None:
    """Record that the task just ran. Call at the end of each loop iteration."""
    conn = await Rimiru.shion()
    async with conn.pool.acquire() as connection:
        await connection.execute(
            """
            INSERT INTO bot_task_runs (name, last_run) VALUES ($1, now())
            ON CONFLICT (name) DO UPDATE SET last_run = EXCLUDED.last_run
            """,
            name,
        )
