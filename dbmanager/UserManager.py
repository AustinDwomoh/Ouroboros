# ============================================================================ #
# MODULE: UserManager.py
# Identity translation between the edges (Discord IDs, Google subs) and the
# internal `users.id`, which is the only user identifier the managers and
# every FK use.
# ============================================================================ #
import discord

from rimiru import Rimiru

# {discord_id: users.id}. users.id never changes for a row, so entries only
# need clearing when accounts are merged.
_discord_cache: dict[int, int] = {}


async def resolve_discord_user(user: discord.abc.User) -> int:
    """Return users.id for a Discord user, creating the row on first sight."""
    cached = _discord_cache.get(user.id)
    if cached is not None:
        return cached
    conn = await Rimiru.shion()
    user_id = await conn.resolve_user(user.id, user.name)
    _discord_cache[user.id] = user_id
    return user_id


async def uid(interaction: discord.Interaction) -> int:
    """users.id of whoever triggered the interaction (resolved once per interaction)."""
    user_id = interaction.extras.get("uid")
    if user_id is None:
        user_id = await resolve_discord_user(interaction.user)
        interaction.extras["uid"] = user_id
    return user_id


async def find_by_discord_id(discord_id: int) -> int | None:
    """users.id for a Discord ID without creating a row (for read-only lookups)."""
    cached = _discord_cache.get(discord_id)
    if cached is not None:
        return cached
    conn = await Rimiru.shion()
    row = await conn.selectOne("users", columns=["id"], filters={"discord_id": discord_id})
    if not row:
        return None
    _discord_cache[discord_id] = row["id"]
    return row["id"]


async def get_discord_ids(user_ids: list[int]) -> dict[int, int]:
    """Map users.id -> discord_id. Users without a Discord account (Google-only) are omitted."""
    if not user_ids:
        return {}
    conn = await Rimiru.shion()
    rows = await conn.select(
        "users",
        columns=["id", "discord_id"],
        raw_where="id = ANY($1::int[]) AND discord_id IS NOT NULL",
        raw_params=[list(set(user_ids))],
    )
    return {row["id"]: row["discord_id"] for row in rows}


async def get_or_create_google_user(google_sub: str, email: str | None, username: str) -> dict:
    """Find or create the users row for a verified Google identity -> {id, username}."""
    conn = await Rimiru.shion()
    return await conn.resolve_google_user(google_sub, email, username)


async def find_by_google_sub(google_sub: str) -> int | None:
    conn = await Rimiru.shion()
    row = await conn.selectOne("users", columns=["id"], filters={"google_sub": google_sub})
    return row["id"] if row else None


def forget_discord_user(discord_id: int | None = None) -> None:
    """Drop one cached mapping (after an account merge), or all of them."""
    if discord_id is None:
        _discord_cache.clear()
    else:
        _discord_cache.pop(discord_id, None)
