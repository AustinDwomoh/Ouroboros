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
    """Find or create the users row for a verified Google identity -> {id, username, discord_id}."""
    conn = await Rimiru.shion()
    return await conn.resolve_google_user(google_sub, email, username)


async def find_by_google_sub(google_sub: str) -> int | None:
    conn = await Rimiru.shion()
    row = await conn.selectOne("users", columns=["id"], filters={"google_sub": google_sub})
    return row["id"] if row else None


class LinkConflict(Exception):
    """The Discord or Google side is already tied to a different account."""


async def link_discord(user_id: int, discord_id: int) -> dict:
    """
    Attach a verified Discord identity to the Google user `user_id` -> {id, username}.

    If the bot already has a row for that Discord user, the Google-only row is merged
    into it and deleted, so the returned id can differ from `user_id`. The Discord row
    survives because levels, game_scores and spotify_tokens are keyed on discord_id.
    """
    conn = await Rimiru.shion()
    async with conn.transaction() as tx:
        g = await tx.fetchrow(
            "SELECT id, username, discord_id, google_sub, email FROM users WHERE id = $1 FOR UPDATE",
            user_id,
        )
        if g is None:
            raise LookupError("User not found")
        if g["discord_id"] == discord_id:
            return {"id": g["id"], "username": g["username"]}
        if g["discord_id"] is not None:
            raise LinkConflict("Your account is already linked to a different Discord account")

        d = await tx.fetchrow(
            "SELECT id, google_sub FROM users WHERE discord_id = $1 FOR UPDATE", discord_id
        )
        if d is None:
            row = await tx.fetchrow(
                "UPDATE users SET discord_id = $2, updated_at = now() WHERE id = $1 RETURNING id, username",
                user_id,
                discord_id,
            )
            forget_discord_user(discord_id)
            return dict(row)
        if d["google_sub"] is not None:
            raise LinkConflict("That Discord account is already linked to another Google account")

        # Merge G (Google-only) into D (Discord). On a clash D's row wins.
        G, D = g["id"], d["id"]
        await tx.execute(
            """
            UPDATE user_media SET user_id = $2
            WHERE user_id = $1
              AND media_id NOT IN (SELECT media_id FROM user_media WHERE user_id = $2)
            """,
            G, D,
        )
        await tx.execute("DELETE FROM user_media WHERE user_id = $1", G)

        # Same collection on both sides: keep D's membership, but with the stronger role
        await tx.execute(
            """
            UPDATE shared_collection_members dm SET role = 'owner'
            FROM shared_collection_members gm
            WHERE gm.user_id = $1 AND gm.role = 'owner'
              AND dm.user_id = $2 AND dm.collection_id = gm.collection_id
            """,
            G, D,
        )
        await tx.execute(
            """
            UPDATE shared_collection_members SET user_id = $2
            WHERE user_id = $1
              AND collection_id NOT IN (SELECT collection_id FROM shared_collection_members WHERE user_id = $2)
            """,
            G, D,
        )
        await tx.execute("DELETE FROM shared_collection_members WHERE user_id = $1", G)
        await tx.execute("UPDATE shared_collections SET owner_id = $2 WHERE owner_id = $1", G, D)
        await tx.execute("UPDATE shared_collection_items SET added_by = $2 WHERE added_by = $1", G, D)

        # Invites between the two halves would become self-invites; pending invites to G
        # are moot where D is already a member or already has its own pending invite.
        await tx.execute(
            """
            DELETE FROM shared_collection_invites
            WHERE (inviter_id = $1 AND invitee_id = $2) OR (inviter_id = $2 AND invitee_id = $1)
            """,
            G, D,
        )
        await tx.execute(
            """
            DELETE FROM shared_collection_invites i
            WHERE i.invitee_id = $1 AND i.status = 'pending'
              AND (
                EXISTS (SELECT 1 FROM shared_collection_members m
                        WHERE m.collection_id = i.collection_id AND m.user_id = $2)
                OR EXISTS (SELECT 1 FROM shared_collection_invites o
                           WHERE o.collection_id = i.collection_id AND o.invitee_id = $2
                             AND o.status = 'pending')
              )
            """,
            G, D,
        )
        await tx.execute("UPDATE shared_collection_invites SET invitee_id = $2 WHERE invitee_id = $1", G, D)
        await tx.execute("UPDATE shared_collection_invites SET inviter_id = $2 WHERE inviter_id = $1", G, D)

        # Free google_sub's unique index before moving it onto D
        await tx.execute("DELETE FROM users WHERE id = $1", G)
        row = await tx.fetchrow(
            """
            UPDATE users SET google_sub = $2, email = COALESCE($3, email), updated_at = now()
            WHERE id = $1
            RETURNING id, username
            """,
            D, g["google_sub"], g["email"],
        )
    forget_discord_user(discord_id)
    return dict(row)


async def get_discord_id(user_id: int) -> int | None:
    conn = await Rimiru.shion()
    row = await conn.selectOne("users", columns=["discord_id"], filters={"id": user_id})
    return row["discord_id"] if row else None


def forget_discord_user(discord_id: int | None = None) -> None:
    """Drop one cached mapping (after an account merge), or all of them."""
    if discord_id is None:
        _discord_cache.clear()
    else:
        _discord_cache.pop(discord_id, None)
