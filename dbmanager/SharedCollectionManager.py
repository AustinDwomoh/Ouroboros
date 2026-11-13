import json
import secrets
from types import SimpleNamespace
from typing import Any

import asyncpg

from dbmanager.shared_common import (
    MANAGER_ROLES,
    SCHEMA,
    ensure_tables,
    loads as _loads,
    log_activity,
    require_member,
)
from progress import episode_counts, series_status
from rimiru import Rimiru

# Progress inside a shared collection is its own thing, kept apart from everyone's personal
# user_media rows: watching a show with friends doesn't move your own progress, and having seen
# it already doesn't mark it watched for the group. A missing row means "not started".
PROGRESS_TABLE = SCHEMA  # kept for UserManager's merge

# No 0/O/1/I/L, so a code read out loud or typed from a screenshot comes out right.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 8


class SharedCollectionManager:
    """Database operations for shared watchlists and playlists."""

    async def ensure_tables(self) -> None:
        await ensure_tables()

    _require_member = staticmethod(require_member)

    # ------------------------------------------------------------------ #
    #                       collections and members                      #
    # ------------------------------------------------------------------ #
    async def create_collection(self, owner_id: int, name: str, collection_type: str) -> dict:
        if collection_type not in {"watchlist", "playlist"}:
            raise ValueError("Invalid collection type")

        await ensure_tables()
        conn = await Rimiru.shion()
        async with conn.pool.acquire() as connection:
            async with connection.transaction():
                collection = await connection.fetchrow(
                    """
                    INSERT INTO shared_collections (owner_id, name, collection_type)
                    VALUES ($1, $2, $3)
                    RETURNING id, name, collection_type
                    """,
                    owner_id,
                    name.strip(),
                    collection_type,
                )
                await connection.execute(
                    """
                    INSERT INTO shared_collection_members (collection_id, user_id, role)
                    VALUES ($1, $2, 'owner')
                    """,
                    collection["id"],
                    owner_id,
                )
        return dict(collection)

    async def update_collection(
        self,
        collection_id: int,
        user_id: int,
        name: str | None = None,
        emoji: str | None = None,
        color: str | None = None,
    ) -> dict:
        """Owner or admin. Empty emoji/color clears them; None leaves them as they are."""
        await ensure_tables()
        if name is not None and not name.strip():
            raise ValueError("The name can't be empty")
        if emoji is not None and len(emoji) > 16:
            raise ValueError("Pick a single emoji")
        if color is not None and color and not (len(color) in (4, 7) and color.startswith("#")):
            raise ValueError("Colour must look like #22aacc")
        conn = await Rimiru.shion()
        async with conn.pool.acquire() as connection:
            async with connection.transaction():
                role = await require_member(connection, collection_id, user_id)
                if role not in MANAGER_ROLES:
                    raise PermissionError("Only the owner or a co-owner can edit the list")
                old_name = await connection.fetchval(
                    "SELECT name FROM shared_collections WHERE id = $1", collection_id
                )
                row = await connection.fetchrow(
                    """
                    UPDATE shared_collections
                    SET name = COALESCE($2, name),
                        emoji = CASE WHEN $3::text IS NULL THEN emoji ELSE NULLIF($3, '') END,
                        color = CASE WHEN $4::text IS NULL THEN color ELSE NULLIF($4, '') END
                    WHERE id = $1
                    RETURNING id, name, collection_type, emoji, color
                    """,
                    collection_id,
                    name.strip() if name is not None else None,
                    emoji,
                    color,
                )
                if name is not None and name.strip() != old_name:
                    await log_activity(
                        connection, collection_id, user_id, "renamed",
                        data={"from": old_name, "to": name.strip()},
                    )
        return dict(row)

    async def set_role(self, collection_id: int, owner_id: int, member_id: int, role: str) -> dict:
        """Owner only: make a member a co-owner ('admin') or back to 'member'."""
        if role not in {"admin", "member"}:
            raise ValueError("Role must be admin or member")
        await ensure_tables()
        conn = await Rimiru.shion()
        async with conn.pool.acquire() as connection:
            async with connection.transaction():
                if await require_member(connection, collection_id, owner_id) != "owner":
                    raise PermissionError("Only the owner can change roles")
                if member_id == owner_id:
                    raise ValueError("You're the owner")
                result = await connection.execute(
                    """
                    UPDATE shared_collection_members SET role = $3
                    WHERE collection_id = $1 AND user_id = $2 AND role <> 'owner'
                    """,
                    collection_id,
                    member_id,
                    role,
                )
                if result.endswith(" 0"):
                    raise ValueError("That user isn't a member")
                await log_activity(
                    connection, collection_id, owner_id, "role",
                    target_user_id=member_id, data={"role": role},
                )
        return {"user_id": member_id, "role": role}

    async def invite(self, collection_id: int, inviter_id: int, invitee_id: int) -> dict:
        """Any member can invite. The invitee accepts in Discord or on the app's Home tab."""
        conn = await Rimiru.shion()
        async with conn.pool.acquire() as connection:
            await require_member(connection, collection_id, inviter_id)
            if inviter_id == invitee_id:
                raise ValueError("You are already a member")

            member = await connection.fetchval(
                """
                SELECT EXISTS(
                    SELECT 1 FROM shared_collection_members
                    WHERE collection_id = $1 AND user_id = $2
                )
                """,
                collection_id,
                invitee_id,
            )
            if member:
                raise ValueError("That user is already a member")

            invite = await connection.fetchrow(
                """
                INSERT INTO shared_collection_invites
                    (collection_id, inviter_id, invitee_id, expires_at)
                VALUES ($1, $2, $3, now() + interval '7 days')
                RETURNING id, collection_id, invitee_id, expires_at
                """,
                collection_id,
                inviter_id,
                invitee_id,
            )
        return dict(invite)

    async def respond_to_invite(self, invite_id: int, user_id: int, accept: bool) -> dict:
        await ensure_tables()
        conn = await Rimiru.shion()
        async with conn.pool.acquire() as connection:
            async with connection.transaction():
                invite = await connection.fetchrow(
                    """
                    SELECT * FROM shared_collection_invites
                    WHERE id = $1 AND invitee_id = $2 AND status = 'pending'
                    FOR UPDATE
                    """,
                    invite_id,
                    user_id,
                )
                if not invite:
                    raise ValueError("Invitation is missing, expired, or already answered")
                if invite["expires_at"] is not None:
                    expired = await connection.fetchval(
                        "SELECT $1 <= now()", invite["expires_at"]
                    )
                    if expired:
                        await connection.execute(
                            """
                            UPDATE shared_collection_invites
                            SET status = 'expired', responded_at = now()
                            WHERE id = $1
                            """,
                            invite_id,
                        )
                        raise ValueError("Invitation has expired")

                status = "accepted" if accept else "declined"
                if accept:
                    # Joining doesn't touch the new member's personal list.
                    joined = await connection.execute(
                        """
                        INSERT INTO shared_collection_members (collection_id, user_id)
                        VALUES ($1, $2)
                        ON CONFLICT (collection_id, user_id) DO NOTHING
                        """,
                        invite["collection_id"],
                        user_id,
                    )
                    if not joined.endswith(" 0"):
                        await log_activity(connection, invite["collection_id"], user_id, "joined")
                await connection.execute(
                    """
                    UPDATE shared_collection_invites
                    SET status = $1, responded_at = now()
                    WHERE id = $2
                    """,
                    status,
                    invite_id,
                )
        return {"status": status, "collection_id": invite["collection_id"]}

    async def invite_code(self, collection_id: int, user_id: int, rotate: bool = False) -> str:
        """The collection's join code, made on first use. rotate=True (owner or co-owner)
        replaces it, so an old code that was shared too widely stops working."""
        await ensure_tables()
        conn = await Rimiru.shion()
        async with conn.pool.acquire() as connection:
            role = await require_member(connection, collection_id, user_id)
            if rotate and role not in MANAGER_ROLES:
                raise PermissionError("Only the owner or a co-owner can reset the invite code")
            code = await connection.fetchval(
                "SELECT invite_code FROM shared_collections WHERE id = $1", collection_id
            )
            if code and not rotate:
                return code
            for _ in range(5):
                code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
                try:
                    await connection.execute(
                        "UPDATE shared_collections SET invite_code = $1 WHERE id = $2",
                        code,
                        collection_id,
                    )
                    return code
                except asyncpg.UniqueViolationError:
                    continue
        raise RuntimeError("Could not generate an invite code")

    async def preview_code(self, code: str) -> dict | None:
        """Name, type and member count behind a code, for the join page before joining."""
        await ensure_tables()
        conn = await Rimiru.shion()
        async with conn.pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT c.id, c.name, c.collection_type, c.emoji, c.color,
                       (SELECT count(*) FROM shared_collection_members m WHERE m.collection_id = c.id) AS member_count,
                       (SELECT count(*) FROM shared_collection_items i WHERE i.collection_id = c.id) AS item_count
                FROM shared_collections c WHERE c.invite_code = $1
                """,
                _normalize_code(code),
            )
        return dict(row) if row else None

    async def join_with_code(self, code: str, user_id: int) -> dict:
        await ensure_tables()
        conn = await Rimiru.shion()
        async with conn.pool.acquire() as connection:
            async with connection.transaction():
                collection = await connection.fetchrow(
                    "SELECT id, name, collection_type FROM shared_collections WHERE invite_code = $1",
                    _normalize_code(code),
                )
                if not collection:
                    raise ValueError("That invite code doesn't match any shared list")
                joined = await connection.execute(
                    """
                    INSERT INTO shared_collection_members (collection_id, user_id)
                    VALUES ($1, $2)
                    ON CONFLICT (collection_id, user_id) DO NOTHING
                    """,
                    collection["id"],
                    user_id,
                )
                already = joined.endswith(" 0")
                if not already:
                    await log_activity(connection, collection["id"], user_id, "joined")
                # Any invite they were sitting on is answered by joining.
                await connection.execute(
                    """
                    UPDATE shared_collection_invites
                    SET status = 'accepted', responded_at = now()
                    WHERE collection_id = $1 AND invitee_id = $2 AND status = 'pending'
                    """,
                    collection["id"],
                    user_id,
                )
        return {**dict(collection), "already_member": already}

    async def leave(self, collection_id: int, user_id: int) -> dict:
        """Leave a collection. An owner hands it to a co-owner, else the longest-standing
        member; the last member out deletes it."""
        await ensure_tables()
        conn = await Rimiru.shion()
        async with conn.pool.acquire() as connection:
            async with connection.transaction():
                await connection.fetchval(
                    "SELECT id FROM shared_collections WHERE id = $1 FOR UPDATE", collection_id
                )
                role = await require_member(connection, collection_id, user_id)
                await self._drop_member(connection, collection_id, user_id)

                successor = await connection.fetchval(
                    """
                    SELECT user_id FROM shared_collection_members
                    WHERE collection_id = $1
                    ORDER BY role = 'admin' DESC, joined_at NULLS LAST, user_id
                    LIMIT 1
                    """,
                    collection_id,
                )
                if successor is None:
                    await connection.execute(
                        "DELETE FROM shared_collection_items WHERE collection_id = $1", collection_id
                    )
                    await connection.execute(
                        "DELETE FROM shared_collection_invites WHERE collection_id = $1", collection_id
                    )
                    await connection.execute(
                        "DELETE FROM shared_collections WHERE id = $1", collection_id
                    )
                    return {"left": True, "deleted": True, "new_owner_id": None}

                new_owner = None
                if role == "owner":
                    await connection.execute(
                        """
                        UPDATE shared_collection_members SET role = 'owner'
                        WHERE collection_id = $1 AND user_id = $2
                        """,
                        collection_id,
                        successor,
                    )
                    await connection.execute(
                        "UPDATE shared_collections SET owner_id = $2 WHERE id = $1",
                        collection_id,
                        successor,
                    )
                    new_owner = successor
                await log_activity(
                    connection, collection_id, user_id, "left",
                    target_user_id=new_owner,
                )
        return {"left": True, "deleted": False, "new_owner_id": new_owner}

    async def remove_member(self, collection_id: int, owner_id: int, member_id: int) -> dict:
        """Owner removes anyone; a co-owner removes plain members."""
        await ensure_tables()
        conn = await Rimiru.shion()
        async with conn.pool.acquire() as connection:
            async with connection.transaction():
                role = await require_member(connection, collection_id, owner_id)
                if role not in MANAGER_ROLES:
                    raise PermissionError("Only the owner or a co-owner can remove members")
                if member_id == owner_id:
                    raise ValueError("Use leave to remove yourself")
                target = await connection.fetchval(
                    "SELECT role FROM shared_collection_members WHERE collection_id = $1 AND user_id = $2",
                    collection_id,
                    member_id,
                )
                if target is None:
                    raise ValueError("That user isn't a member")
                if role == "admin" and target != "member":
                    raise PermissionError("Co-owners can only remove members")
                await self._drop_member(connection, collection_id, member_id)
        return {"removed": member_id}

    @staticmethod
    async def _drop_member(connection, collection_id: int, user_id: int) -> bool:
        """Their progress, votes and RSVPs go; their comments and ratings stay for the others."""
        for table in ("shared_collection_progress", "shared_collection_votes"):
            await connection.execute(
                f"DELETE FROM {table} WHERE collection_id = $1 AND user_id = $2",
                collection_id,
                user_id,
            )
        await connection.execute(
            """
            DELETE FROM shared_watch_party_rsvps r
            USING shared_watch_parties p
            WHERE r.party_id = p.id AND p.collection_id = $1 AND r.user_id = $2
            """,
            collection_id,
            user_id,
        )
        result = await connection.execute(
            "DELETE FROM shared_collection_members WHERE collection_id = $1 AND user_id = $2",
            collection_id,
            user_id,
        )
        return not result.endswith(" 0")

    # ------------------------------------------------------------------ #
    #                                items                               #
    # ------------------------------------------------------------------ #
    async def add_item(self, collection_id: int, user_id: int, media_id: int) -> dict[str, Any]:
        """Add media to a collection and report who else should be notified about it.
        Members' personal lists are left alone."""
        await ensure_tables()
        conn = await Rimiru.shion()
        async with conn.pool.acquire() as connection:
            await require_member(connection, collection_id, user_id)

            media = await connection.fetchrow(
                "SELECT title, media_type FROM media WHERE id = $1", media_id
            )
            if not media:
                raise ValueError("That media does not exist")
            collection_name = await connection.fetchval(
                "SELECT name FROM shared_collections WHERE id = $1", collection_id
            )
            inserted = await connection.execute(
                """
                INSERT INTO shared_collection_items (collection_id, media_id, added_by)
                VALUES ($1, $2, $3)
                ON CONFLICT (collection_id, media_id) DO NOTHING
                """,
                collection_id,
                media_id,
                user_id,
            )
            if not inserted.endswith(" 0"):
                await log_activity(connection, collection_id, user_id, "added", media_id)
            members = await connection.fetch(
                "SELECT user_id FROM shared_collection_members WHERE collection_id = $1",
                collection_id,
            )

        return {
            "media_id": media_id,
            "title": media["title"],
            "media_type": media["media_type"],
            "collection_name": collection_name,
            "member_ids": [member["user_id"] for member in members],
        }

    async def remove_item(self, collection_id: int, user_id: int, media_id: int) -> dict:
        """The owner, a co-owner, or whoever added it can take an item off the list."""
        await ensure_tables()
        conn = await Rimiru.shion()
        async with conn.pool.acquire() as connection:
            async with connection.transaction():
                role = await require_member(connection, collection_id, user_id)
                added_by = await connection.fetchval(
                    "SELECT added_by FROM shared_collection_items WHERE collection_id = $1 AND media_id = $2",
                    collection_id,
                    media_id,
                )
                exists = await connection.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM shared_collection_items WHERE collection_id = $1 AND media_id = $2)",
                    collection_id,
                    media_id,
                )
                if not exists:
                    raise ValueError("That media is not in this collection")
                if role not in MANAGER_ROLES and added_by != user_id:
                    raise PermissionError("Only the owner, a co-owner or whoever added it can remove it")
                for table in (
                    "shared_collection_progress",
                    "shared_collection_votes",
                    "shared_collection_ratings",
                    "shared_collection_comments",
                    "shared_watch_parties",
                ):
                    await connection.execute(
                        f"DELETE FROM {table} WHERE collection_id = $1 AND media_id = $2",
                        collection_id,
                        media_id,
                    )
                await connection.execute(
                    "DELETE FROM shared_collection_items WHERE collection_id = $1 AND media_id = $2",
                    collection_id,
                    media_id,
                )
                await log_activity(connection, collection_id, user_id, "removed", media_id)
        return {"removed": media_id}

    async def get_collection(self, collection_id: int, user_id: int) -> dict[str, Any] | None:
        """The collection, its members, and its items with every member's progress, the votes,
        ratings and comment count on each. Each item also carries the caller's own shared
        status/progress as user_status/progress."""
        await ensure_tables()
        conn = await Rimiru.shion()
        async with conn.pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT collection.id, collection.name, collection.collection_type,
                       collection.owner_id, collection.created_at, collection.emoji,
                       collection.color, member.role
                FROM shared_collections AS collection
                JOIN shared_collection_members AS member
                  ON member.collection_id = collection.id
                WHERE collection.id = $1 AND member.user_id = $2
                """,
                collection_id,
                user_id,
            )
            if not row:
                return None
            members = await connection.fetch(
                """
                SELECT member.user_id, users.username, member.role, member.joined_at
                FROM shared_collection_members AS member
                JOIN users ON users.id = member.user_id
                WHERE member.collection_id = $1
                ORDER BY member.role = 'owner' DESC, member.role = 'admin' DESC,
                         member.joined_at NULLS LAST, member.user_id
                """,
                collection_id,
            )
            items = await connection.fetch(
                """
                SELECT item.media_id, media.title, media.media_type, media.tmdb_id,
                       media.poster_path, media.release_date, media.status AS media_status,
                       item.added_by, adder.username AS added_by_username, item.added_at,
                       series.seasons, series.last_episode_to_air, series.next_episode_to_air,
                       (SELECT count(*) FROM shared_collection_comments c
                        WHERE c.collection_id = item.collection_id AND c.media_id = item.media_id) AS comment_count
                FROM shared_collection_items AS item
                JOIN media ON media.id = item.media_id
                LEFT JOIN series ON series.id = media.id
                LEFT JOIN users AS adder ON adder.id = item.added_by
                WHERE item.collection_id = $1
                ORDER BY item.added_at, media.title
                """,
                collection_id,
            )
            progress_rows = await connection.fetch(
                "SELECT media_id, user_id, status, progress, updated_at FROM shared_collection_progress WHERE collection_id = $1",
                collection_id,
            )
            vote_rows = await connection.fetch(
                "SELECT media_id, user_id FROM shared_collection_votes WHERE collection_id = $1",
                collection_id,
            )
            rating_rows = await connection.fetch(
                """
                SELECT r.media_id, r.user_id, users.username, r.rating, r.reaction
                FROM shared_collection_ratings r JOIN users ON users.id = r.user_id
                WHERE r.collection_id = $1
                """,
                collection_id,
            )

        progress = {(p["media_id"], p["user_id"]): p for p in progress_rows}
        votes: dict[int, list[int]] = {}
        for v in vote_rows:
            votes.setdefault(v["media_id"], []).append(v["user_id"])
        ratings: dict[int, list[dict]] = {}
        for r in rating_rows:
            ratings.setdefault(r["media_id"], []).append(
                {k: r[k] for k in ("user_id", "username", "rating", "reaction")}
            )

        result = dict(row)
        result["members"] = [dict(m) for m in members]
        result["items"] = []
        for item in items:
            is_series = item["media_type"] == "series"

            def counts_for(p, item=item):
                return episode_counts(item["seasons"], item["last_episode_to_air"], p) if is_series else None

            entry = {
                k: item[k]
                for k in (
                    "media_id", "title", "media_type", "tmdb_id", "poster_path", "release_date",
                    "media_status", "added_by", "added_by_username", "added_at", "comment_count",
                )
            }
            entry["next_episode_info"] = _loads(item["next_episode_to_air"])
            aired = counts_for(None)
            entry["episodes_aired"] = aired["aired"] if aired else None

            voters = votes.get(item["media_id"], [])
            entry["votes"] = len(voters)
            entry["my_vote"] = user_id in voters
            item_ratings = ratings.get(item["media_id"], [])
            scored = [r["rating"] for r in item_ratings if r["rating"]]
            entry["ratings"] = item_ratings
            entry["avg_rating"] = round(sum(scored) / len(scored), 1) if scored else None

            entry["members"] = []
            for member in members:
                p = progress.get((item["media_id"], member["user_id"]))
                member_progress = _loads(p["progress"]) if p else None
                if not p:
                    status = "watchlist"
                elif is_series and member_progress:
                    # Derived on read, so a show that comes back for another season moves
                    # finished viewers back to watching without a background job.
                    status = series_status(
                        item["media_status"], item["last_episode_to_air"], member_progress
                    )
                else:
                    status = p["status"]
                counts = counts_for(member_progress)
                entry["members"].append({
                    "user_id": member["user_id"],
                    "username": member["username"],
                    "status": status,
                    "progress": member_progress,
                    "episodes_watched": counts["watched"] if counts else None,
                    "updated_at": p["updated_at"] if p else None,
                })
                if member["user_id"] == user_id:
                    entry["user_status"] = status
                    entry["progress"] = member_progress
                    entry["episodes_watched"] = counts["watched"] if counts else None
            result["items"].append(entry)
        return result

    # ------------------------------------------------------------------ #
    #                         shared watch progress                      #
    # ------------------------------------------------------------------ #
    async def _item_context(self, connection, collection_id: int, media_id: int, user_id: int):
        """Collection + item rows for a progress change, checking membership on the way."""
        collection = await connection.fetchrow(
            "SELECT owner_id, name FROM shared_collections WHERE id = $1", collection_id
        )
        if not collection:
            raise ValueError("Collection does not exist")
        role = await require_member(connection, collection_id, user_id)
        item = await connection.fetchrow(
            """
            SELECT media.title, media.media_type, media.status AS media_status,
                   series.seasons, series.last_episode_to_air
            FROM shared_collection_items AS item
            JOIN media ON media.id = item.media_id
            LEFT JOIN series ON series.id = media.id
            WHERE item.collection_id = $1 AND item.media_id = $2
            """,
            collection_id,
            media_id,
        )
        if not item:
            raise ValueError("That media is not in this collection")
        return {**dict(collection), "role": role}, item

    async def _tally(self, connection, collection_id: int, media_id: int, item) -> dict:
        """How many members have finished an item, using the same rule get_collection shows."""
        members = await connection.fetch(
            """
            SELECT member.user_id, personal.status, personal.progress
            FROM shared_collection_members AS member
            LEFT JOIN shared_collection_progress AS personal
              ON personal.user_id = member.user_id
             AND personal.collection_id = member.collection_id
             AND personal.media_id = $2
            WHERE member.collection_id = $1
            """,
            collection_id,
            media_id,
        )

        def finished(m) -> bool:
            if m["status"] is None:
                return False
            if item["media_type"] == "series" and m["progress"]:
                return series_status(
                    item["media_status"], item["last_episode_to_air"], m["progress"]
                ) == "watched"
            return m["status"] == "watched"

        watched_count = sum(1 for m in members if finished(m))
        return {
            "completed": watched_count == len(members),
            "watched_count": watched_count,
            "total_count": len(members),
            "member_ids": [m["user_id"] for m in members],
        }

    async def mark_watched(
        self,
        collection_id: int,
        media_id: int,
        user_id: int,
        everyone: bool = False,
    ) -> dict[str, Any]:
        """Mark an item watched in the collection (not on anyone's personal list) and report the
        collection's resulting watch progress. A series is set to its latest aired episode."""
        await ensure_tables()
        conn = await Rimiru.shion()
        async with conn.pool.acquire() as connection:
            async with connection.transaction():
                collection, item = await self._item_context(connection, collection_id, media_id, user_id)
                if everyone and collection["role"] not in MANAGER_ROLES:
                    raise PermissionError("Only the owner or a co-owner can mark an item watched for everyone")

                last = _loads(item["last_episode_to_air"])
                progress = (
                    json.dumps({"season": last["season_number"], "episode": last["episode_number"]})
                    if item["media_type"] == "series" and last
                    else None
                )
                await connection.execute(
                    """
                    INSERT INTO shared_collection_progress (collection_id, media_id, user_id, status, progress)
                    SELECT $1, $2, member.user_id, 'watched', $4::jsonb
                    FROM shared_collection_members AS member
                    WHERE member.collection_id = $1 AND ($5 OR member.user_id = $3)
                    ON CONFLICT (collection_id, media_id, user_id) DO UPDATE
                    SET status = 'watched',
                        progress = COALESCE(EXCLUDED.progress, shared_collection_progress.progress),
                        updated_at = now()
                    """,
                    collection_id,
                    media_id,
                    user_id,
                    progress,
                    everyone,
                )
                tally = await self._tally(connection, collection_id, media_id, item)
                await log_activity(
                    connection, collection_id, user_id, "watched", media_id,
                    data={"everyone": everyone, "completed": tally["completed"]},
                )

        return {"title": item["title"], "collection_name": collection["name"], **tally}

    async def set_progress(
        self, collection_id: int, media_id: int, user_id: int, season: int, episode: int
    ) -> dict[str, Any]:
        """Record the caller's last watched episode of a series in this collection. Episodes past
        the end of a season roll over like they do on personal lists."""
        from dbmanager.MovieManager import MovieManager  # heavy import; only needed here

        await ensure_tables()
        conn = await Rimiru.shion()
        async with conn.pool.acquire() as connection:
            async with connection.transaction():
                collection, item = await self._item_context(connection, collection_id, media_id, user_id)
                if item["media_type"] != "series":
                    raise ValueError("Only series have episode progress")
                progress = MovieManager.normalize_progress(
                    SimpleNamespace(seasons=item["seasons"]), season, episode
                )
                if not progress:
                    raise ValueError("Season and episode are required")
                before = await connection.fetchval(
                    """
                    SELECT progress FROM shared_collection_progress
                    WHERE collection_id = $1 AND media_id = $2 AND user_id = $3
                    """,
                    collection_id,
                    media_id,
                    user_id,
                )
                status = series_status(item["media_status"], item["last_episode_to_air"], progress)
                await connection.execute(
                    """
                    INSERT INTO shared_collection_progress (collection_id, media_id, user_id, status, progress)
                    VALUES ($1, $2, $3, $4, $5::jsonb)
                    ON CONFLICT (collection_id, media_id, user_id) DO UPDATE
                    SET status = EXCLUDED.status, progress = EXCLUDED.progress, updated_at = now()
                    """,
                    collection_id,
                    media_id,
                    user_id,
                    status,
                    json.dumps(progress),
                )
                tally = await self._tally(connection, collection_id, media_id, item)
                if status == "watched":
                    await log_activity(
                        connection, collection_id, user_id, "finished", media_id,
                        data={"completed": tally["completed"]},
                    )
                else:
                    await log_activity(
                        connection, collection_id, user_id, "progress", media_id,
                        data={"from": _loads(before), "to": progress},
                    )

        return {
            "title": item["title"],
            "collection_name": collection["name"],
            "progress": progress,
            "user_status": status,
            **tally,
        }

    async def reset_progress(self, collection_id: int, media_id: int, user_id: int) -> dict:
        """Back to not started, for the caller only."""
        await ensure_tables()
        conn = await Rimiru.shion()
        async with conn.pool.acquire() as connection:
            await self._item_context(connection, collection_id, media_id, user_id)
            await connection.execute(
                """
                DELETE FROM shared_collection_progress
                WHERE collection_id = $1 AND media_id = $2 AND user_id = $3
                """,
                collection_id,
                media_id,
                user_id,
            )
        return {"status": "watchlist"}

    # ------------------------------------------------------------------ #
    #                               lookups                              #
    # ------------------------------------------------------------------ #
    async def get_user_collections(self, user_id: int) -> list[dict[str, Any]]:
        await ensure_tables()
        conn = await Rimiru.shion()
        async with conn.pool.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT collection.id, collection.name, collection.collection_type,
                       collection.emoji, collection.color, member.role,
                       (SELECT count(*) FROM shared_collection_members m
                        WHERE m.collection_id = collection.id) AS member_count
                FROM shared_collections AS collection
                JOIN shared_collection_members AS member
                  ON member.collection_id = collection.id
                WHERE member.user_id = $1
                ORDER BY collection.name
                """,
                user_id,
            )
        return [dict(row) for row in rows]

    async def get_pending_invites(self, user_id: int) -> list[dict[str, Any]]:
        """Unexpired pending invites addressed to a user, newest first."""
        conn = await Rimiru.shion()
        return await conn.select(
            table=(
                "shared_collection_invites AS invite "
                "JOIN shared_collections AS collection ON collection.id = invite.collection_id "
                "JOIN users AS inviter ON inviter.id = invite.inviter_id"
            ),
            columns=[
                "invite.id", "invite.collection_id", "collection.name AS collection_name",
                "collection.collection_type", "invite.inviter_id",
                "inviter.username AS inviter_username", "invite.expires_at",
            ],
            raw_where=(
                "invite.invitee_id = $1 AND invite.status = 'pending' "
                "AND (invite.expires_at IS NULL OR invite.expires_at > now())"
            ),
            raw_params=[user_id],
            order_by="invite.id DESC",
        )

    async def get_collection_id(self, user_id: int, name: str) -> int | None:
        """Resolve a collection name to its ID for a member."""
        collections = await self.get_user_collections(user_id)
        normalized_name = name.strip().casefold()
        for collection in collections:
            if collection["name"].casefold() == normalized_name:
                return collection["id"]
        return None


def _normalize_code(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


sharedCollectionManager = SharedCollectionManager()
