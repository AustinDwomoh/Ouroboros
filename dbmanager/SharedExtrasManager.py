"""The social side of shared collections: votes, ratings, comments, the activity feed, nudges
and watch parties. Membership and items live in SharedCollectionManager."""

from datetime import datetime, timedelta, timezone
from typing import Any

from dbmanager.shared_common import (
    MANAGER_ROLES,
    ensure_tables,
    loads,
    log_activity,
    require_item,
    require_member,
)
from rimiru import Rimiru

REACTIONS = {"🔥", "😂", "😭", "😱", "🥱", "❤️", "👏", "🤯"}
NUDGE_COOLDOWN = timedelta(hours=12)  # per nudger, target and title
PARTY_MAX_AHEAD = timedelta(days=60)


class SharedExtrasManager:
    # ------------------------------------------------------------------ #
    #                                votes                               #
    # ------------------------------------------------------------------ #
    async def vote(self, collection_id: int, media_id: int, user_id: int, up: bool) -> dict:
        """One vote per member per item; up=False takes it back."""
        await ensure_tables()
        conn = await Rimiru.shion()
        async with conn.pool.acquire() as connection:
            await require_member(connection, collection_id, user_id)
            await require_item(connection, collection_id, media_id)
            if up:
                await connection.execute(
                    """
                    INSERT INTO shared_collection_votes (collection_id, media_id, user_id)
                    VALUES ($1, $2, $3) ON CONFLICT DO NOTHING
                    """,
                    collection_id, media_id, user_id,
                )
            else:
                await connection.execute(
                    "DELETE FROM shared_collection_votes WHERE collection_id = $1 AND media_id = $2 AND user_id = $3",
                    collection_id, media_id, user_id,
                )
            votes = await connection.fetchval(
                "SELECT count(*) FROM shared_collection_votes WHERE collection_id = $1 AND media_id = $2",
                collection_id, media_id,
            )
        return {"votes": votes, "my_vote": up}

    # ------------------------------------------------------------------ #
    #                              ratings                               #
    # ------------------------------------------------------------------ #
    async def rate(
        self,
        collection_id: int,
        media_id: int,
        user_id: int,
        rating: int | None,
        reaction: str | None,
    ) -> dict:
        """A 1-5 rating and/or one reaction emoji. Both None removes the caller's rating."""
        if rating is not None and not 1 <= rating <= 5:
            raise ValueError("Rating must be 1 to 5")
        if reaction is not None and reaction not in REACTIONS:
            raise ValueError("Unknown reaction")
        await ensure_tables()
        conn = await Rimiru.shion()
        async with conn.pool.acquire() as connection:
            async with connection.transaction():
                await require_member(connection, collection_id, user_id)
                await require_item(connection, collection_id, media_id)
                if rating is None and reaction is None:
                    await connection.execute(
                        "DELETE FROM shared_collection_ratings WHERE collection_id = $1 AND media_id = $2 AND user_id = $3",
                        collection_id, media_id, user_id,
                    )
                else:
                    first = await connection.fetchval(
                        """
                        SELECT NOT EXISTS(SELECT 1 FROM shared_collection_ratings
                                          WHERE collection_id = $1 AND media_id = $2 AND user_id = $3)
                        """,
                        collection_id, media_id, user_id,
                    )
                    await connection.execute(
                        """
                        INSERT INTO shared_collection_ratings (collection_id, media_id, user_id, rating, reaction)
                        VALUES ($1, $2, $3, $4, $5)
                        ON CONFLICT (collection_id, media_id, user_id) DO UPDATE
                        SET rating = EXCLUDED.rating, reaction = EXCLUDED.reaction, updated_at = now()
                        """,
                        collection_id, media_id, user_id, rating, reaction,
                    )
                    if first:
                        await log_activity(
                            connection, collection_id, user_id, "rated", media_id,
                            data={"rating": rating, "reaction": reaction},
                        )
                avg = await connection.fetchval(
                    "SELECT round(avg(rating), 1) FROM shared_collection_ratings WHERE collection_id = $1 AND media_id = $2",
                    collection_id, media_id,
                )
        return {"rating": rating, "reaction": reaction, "avg_rating": float(avg) if avg is not None else None}

    # ------------------------------------------------------------------ #
    #                              comments                              #
    # ------------------------------------------------------------------ #
    async def comments(self, collection_id: int, media_id: int, user_id: int) -> list[dict]:
        await ensure_tables()
        conn = await Rimiru.shion()
        async with conn.pool.acquire() as connection:
            await require_member(connection, collection_id, user_id)
            rows = await connection.fetch(
                """
                SELECT c.id, c.user_id, users.username, c.body, c.created_at
                FROM shared_collection_comments c JOIN users ON users.id = c.user_id
                WHERE c.collection_id = $1 AND c.media_id = $2
                ORDER BY c.id
                LIMIT 200
                """,
                collection_id, media_id,
            )
        return [dict(r) for r in rows]

    async def add_comment(self, collection_id: int, media_id: int, user_id: int, body: str) -> dict:
        body = body.strip()
        if not body:
            raise ValueError("Write something first")
        if len(body) > 500:
            raise ValueError("Keep it under 500 characters")
        await ensure_tables()
        conn = await Rimiru.shion()
        async with conn.pool.acquire() as connection:
            async with connection.transaction():
                await require_member(connection, collection_id, user_id)
                await require_item(connection, collection_id, media_id)
                row = await connection.fetchrow(
                    """
                    INSERT INTO shared_collection_comments (collection_id, media_id, user_id, body)
                    VALUES ($1, $2, $3, $4)
                    RETURNING id, user_id, body, created_at
                    """,
                    collection_id, media_id, user_id, body,
                )
                await log_activity(
                    connection, collection_id, user_id, "commented", media_id,
                    data={"preview": body[:80]},
                )
        return dict(row)

    async def delete_comment(self, collection_id: int, comment_id: int, user_id: int) -> dict:
        """Your own comment, or any comment if you're the owner or a co-owner."""
        await ensure_tables()
        conn = await Rimiru.shion()
        async with conn.pool.acquire() as connection:
            role = await require_member(connection, collection_id, user_id)
            author = await connection.fetchval(
                "SELECT user_id FROM shared_collection_comments WHERE id = $1 AND collection_id = $2",
                comment_id, collection_id,
            )
            if author is None:
                raise ValueError("That comment doesn't exist")
            if author != user_id and role not in MANAGER_ROLES:
                raise PermissionError("You can only delete your own comments")
            await connection.execute("DELETE FROM shared_collection_comments WHERE id = $1", comment_id)
        return {"deleted": comment_id}

    # ------------------------------------------------------------------ #
    #                               activity                             #
    # ------------------------------------------------------------------ #
    async def activity(self, collection_id: int, user_id: int, limit: int = 30) -> list[dict]:
        await ensure_tables()
        conn = await Rimiru.shion()
        async with conn.pool.acquire() as connection:
            await require_member(connection, collection_id, user_id)
            rows = await connection.fetch(
                """
                SELECT a.id, a.kind, a.user_id, actor.username, a.media_id, media.title,
                       media.media_type, media.tmdb_id, a.target_user_id,
                       target.username AS target_username, a.data, a.created_at
                FROM shared_collection_activity a
                LEFT JOIN users actor ON actor.id = a.user_id
                LEFT JOIN users target ON target.id = a.target_user_id
                LEFT JOIN media ON media.id = a.media_id
                WHERE a.collection_id = $1
                ORDER BY a.id DESC
                LIMIT $2
                """,
                collection_id, max(1, min(limit, 100)),
            )
        return [{**dict(r), "data": loads(r["data"])} for r in rows]

    # ------------------------------------------------------------------ #
    #                                nudges                              #
    # ------------------------------------------------------------------ #
    async def nudge(self, collection_id: int, media_id: int, user_id: int, target_user_id: int) -> dict:
        """Poke a member who's behind on a title. Returns who to DM and what to say; the
        caller sends it. One nudge per person and title every 12 hours."""
        if target_user_id == user_id:
            raise ValueError("You can't nudge yourself")
        await ensure_tables()
        conn = await Rimiru.shion()
        async with conn.pool.acquire() as connection:
            async with connection.transaction():
                await require_member(connection, collection_id, user_id)
                await require_member(connection, collection_id, target_user_id)
                title = await require_item(connection, collection_id, media_id)
                recent = await connection.fetchval(
                    """
                    SELECT EXISTS(
                        SELECT 1 FROM shared_collection_activity
                        WHERE collection_id = $1 AND kind = 'nudge' AND user_id = $2
                          AND target_user_id = $3 AND media_id = $4 AND created_at > $5
                    )
                    """,
                    collection_id, user_id, target_user_id, media_id,
                    datetime.now(timezone.utc) - NUDGE_COOLDOWN,
                )
                if recent:
                    raise ValueError("You already nudged them about this today")
                names = await connection.fetchrow(
                    """
                    SELECT (SELECT username FROM users WHERE id = $1) AS nudger,
                           (SELECT name FROM shared_collections WHERE id = $2) AS collection_name
                    """,
                    user_id, collection_id,
                )
                await log_activity(
                    connection, collection_id, user_id, "nudge", media_id, target_user_id=target_user_id
                )
        return {
            "title": title,
            "collection_name": names["collection_name"],
            "nudger": names["nudger"],
            "target_user_id": target_user_id,
        }

    async def nudges_for(self, user_id: int, days: int = 7) -> list[dict]:
        """Recent nudges aimed at the user, for the app's Home tab."""
        await ensure_tables()
        conn = await Rimiru.shion()
        async with conn.pool.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT a.id, a.collection_id, c.name AS collection_name, a.user_id,
                       actor.username, a.media_id, media.title, media.media_type,
                       media.tmdb_id, a.created_at
                FROM shared_collection_activity a
                JOIN shared_collections c ON c.id = a.collection_id
                JOIN shared_collection_members m ON m.collection_id = a.collection_id AND m.user_id = $1
                LEFT JOIN users actor ON actor.id = a.user_id
                LEFT JOIN media ON media.id = a.media_id
                WHERE a.kind = 'nudge' AND a.target_user_id = $1
                  AND a.created_at > now() - make_interval(days => $2)
                ORDER BY a.id DESC
                LIMIT 10
                """,
                user_id, days,
            )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ #
    #                            watch parties                           #
    # ------------------------------------------------------------------ #
    _PARTY_SELECT = """
        SELECT p.id, p.collection_id, c.name AS collection_name, p.media_id, media.title,
               media.media_type, media.tmdb_id, media.poster_path, p.created_by,
               creator.username AS created_by_username, p.starts_at, p.note,
               COALESCE((
                   SELECT json_agg(json_build_object('user_id', r.user_id, 'username', u.username, 'going', r.going))
                   FROM shared_watch_party_rsvps r JOIN users u ON u.id = r.user_id
                   WHERE r.party_id = p.id
               ), '[]'::json) AS rsvps
        FROM shared_watch_parties p
        JOIN shared_collections c ON c.id = p.collection_id
        JOIN media ON media.id = p.media_id
        LEFT JOIN users creator ON creator.id = p.created_by
    """

    @staticmethod
    def _party(row) -> dict:
        return {**dict(row), "rsvps": loads(row["rsvps"]) or []}

    async def parties(self, collection_id: int, user_id: int) -> list[dict]:
        """Upcoming parties (and ones that started in the last 3 hours) for a collection."""
        await ensure_tables()
        conn = await Rimiru.shion()
        async with conn.pool.acquire() as connection:
            await require_member(connection, collection_id, user_id)
            rows = await connection.fetch(
                self._PARTY_SELECT
                + " WHERE p.collection_id = $1 AND p.starts_at > now() - interval '3 hours' ORDER BY p.starts_at",
                collection_id,
            )
        return [self._party(r) for r in rows]

    async def parties_for(self, user_id: int) -> list[dict]:
        """Upcoming parties in every collection the user is in, for Home."""
        await ensure_tables()
        conn = await Rimiru.shion()
        async with conn.pool.acquire() as connection:
            rows = await connection.fetch(
                self._PARTY_SELECT
                + """
                JOIN shared_collection_members m ON m.collection_id = p.collection_id AND m.user_id = $1
                WHERE p.starts_at > now() - interval '3 hours'
                ORDER BY p.starts_at
                LIMIT 10
                """,
                user_id,
            )
        return [self._party(r) for r in rows]

    async def create_party(
        self, collection_id: int, media_id: int, user_id: int, starts_at: datetime, note: str | None
    ) -> dict:
        if starts_at.tzinfo is None:
            raise ValueError("starts_at needs a timezone")
        now = datetime.now(timezone.utc)
        if starts_at < now - timedelta(minutes=5):
            raise ValueError("Pick a time in the future")
        if starts_at > now + PARTY_MAX_AHEAD:
            raise ValueError("Pick a time within the next two months")
        note = (note or "").strip()[:200] or None
        await ensure_tables()
        conn = await Rimiru.shion()
        async with conn.pool.acquire() as connection:
            async with connection.transaction():
                await require_member(connection, collection_id, user_id)
                await require_item(connection, collection_id, media_id)
                party_id = await connection.fetchval(
                    """
                    INSERT INTO shared_watch_parties (collection_id, media_id, created_by, starts_at, note)
                    VALUES ($1, $2, $3, $4, $5) RETURNING id
                    """,
                    collection_id, media_id, user_id, starts_at, note,
                )
                await connection.execute(
                    "INSERT INTO shared_watch_party_rsvps (party_id, user_id, going) VALUES ($1, $2, true)",
                    party_id, user_id,
                )
                await log_activity(
                    connection, collection_id, user_id, "party", media_id,
                    data={"party_id": party_id, "starts_at": starts_at.isoformat()},
                )
                row = await connection.fetchrow(self._PARTY_SELECT + " WHERE p.id = $1", party_id)
                members = await connection.fetch(
                    "SELECT user_id FROM shared_collection_members WHERE collection_id = $1", collection_id
                )
        return {**self._party(row), "member_ids": [m["user_id"] for m in members]}

    async def rsvp(self, party_id: int, user_id: int, going: bool) -> dict:
        await ensure_tables()
        conn = await Rimiru.shion()
        async with conn.pool.acquire() as connection:
            collection_id = await connection.fetchval(
                "SELECT collection_id FROM shared_watch_parties WHERE id = $1", party_id
            )
            if collection_id is None:
                raise ValueError("That watch party doesn't exist")
            await require_member(connection, collection_id, user_id)
            await connection.execute(
                """
                INSERT INTO shared_watch_party_rsvps (party_id, user_id, going) VALUES ($1, $2, $3)
                ON CONFLICT (party_id, user_id) DO UPDATE SET going = EXCLUDED.going, updated_at = now()
                """,
                party_id, user_id, going,
            )
            row = await connection.fetchrow(self._PARTY_SELECT + " WHERE p.id = $1", party_id)
        return self._party(row)

    async def cancel_party(self, party_id: int, user_id: int) -> dict:
        """Whoever planned it, or the owner / a co-owner."""
        await ensure_tables()
        conn = await Rimiru.shion()
        async with conn.pool.acquire() as connection:
            party = await connection.fetchrow(
                "SELECT collection_id, created_by FROM shared_watch_parties WHERE id = $1", party_id
            )
            if not party:
                raise ValueError("That watch party doesn't exist")
            role = await require_member(connection, party["collection_id"], user_id)
            if party["created_by"] != user_id and role not in MANAGER_ROLES:
                raise PermissionError("Only whoever planned it can cancel it")
            await connection.execute("DELETE FROM shared_watch_parties WHERE id = $1", party_id)
        return {"cancelled": party_id}

    async def due_reminders(self, within: timedelta = timedelta(hours=1)) -> list[dict[str, Any]]:
        """Parties starting within `within` that haven't been reminded about; marks them reminded.
        Everyone who said they're going, plus members who haven't answered, gets the reminder."""
        await ensure_tables()
        conn = await Rimiru.shion()
        async with conn.pool.acquire() as connection:
            async with connection.transaction():
                rows = await connection.fetch(
                    """
                    UPDATE shared_watch_parties p SET reminded_at = now()
                    FROM shared_collections c, media
                    WHERE c.id = p.collection_id AND media.id = p.media_id
                      AND p.reminded_at IS NULL
                      AND p.starts_at BETWEEN now() AND now() + $1::interval
                    RETURNING p.id, p.collection_id, c.name AS collection_name, media.title,
                              p.starts_at, p.note
                    """,
                    within,
                )
                out = []
                for r in rows:
                    recipients = await connection.fetch(
                        """
                        SELECT m.user_id FROM shared_collection_members m
                        LEFT JOIN shared_watch_party_rsvps r ON r.party_id = $1 AND r.user_id = m.user_id
                        WHERE m.collection_id = $2 AND (r.going IS NULL OR r.going)
                        """,
                        r["id"], r["collection_id"],
                    )
                    out.append({**dict(r), "user_ids": [x["user_id"] for x in recipients]})
        return out


sharedExtrasManager = SharedExtrasManager()
