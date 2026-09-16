from typing import Any

from rimiru import Rimiru


class SharedCollectionManager:
    """Database operations for shared watchlists and playlists."""

    async def create_collection(self, owner_id: int, name: str, collection_type: str) -> dict:
        if collection_type not in {"watchlist", "playlist"}:
            raise ValueError("Invalid collection type")

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

    async def invite(self, collection_id: int, inviter_id: int, invitee_id: int) -> dict:
        conn = await Rimiru.shion()
        async with conn.pool.acquire() as connection:
            owner = await connection.fetchval(
                "SELECT owner_id FROM shared_collections WHERE id = $1",
                collection_id,
            )
            if owner != inviter_id:
                raise PermissionError("Only the collection owner can invite users")
            if inviter_id == invitee_id:
                raise ValueError("The owner is already a member")

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
                    await connection.execute(
                        """
                        INSERT INTO shared_collection_members (collection_id, user_id)
                        VALUES ($1, $2)
                        ON CONFLICT (collection_id, user_id) DO NOTHING
                        """,
                        invite["collection_id"],
                        user_id,
                    )
                    await connection.execute(
                        """
                        INSERT INTO user_media (user_id, media_id, status)
                        SELECT $1, media_id, 'watchlist'
                        FROM shared_collection_items
                        WHERE collection_id = $2
                        ON CONFLICT (user_id, media_id) DO NOTHING
                        """,
                        user_id,
                        invite["collection_id"],
                    )
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

    async def add_item(self, collection_id: int, user_id: int, media_id: int) -> dict[str, Any]:
        """Add media to a collection and report who else should be notified about it."""
        conn = await Rimiru.shion()
        async with conn.pool.acquire() as connection:
            is_member = await connection.fetchval(
                """
                SELECT EXISTS(
                    SELECT 1 FROM shared_collection_members
                    WHERE collection_id = $1 AND user_id = $2
                )
                """,
                collection_id,
                user_id,
            )
            if not is_member:
                raise PermissionError("You are not a member of this collection")

            media = await connection.fetchrow(
                "SELECT title, media_type FROM media WHERE id = $1", media_id
            )
            if not media:
                raise ValueError("That media does not exist")
            collection_name = await connection.fetchval(
                "SELECT name FROM shared_collections WHERE id = $1", collection_id
            )

            async with connection.transaction():
                await connection.execute(
                    """
                    INSERT INTO shared_collection_items (collection_id, media_id, added_by)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (collection_id, media_id) DO NOTHING
                    """,
                    collection_id,
                    media_id,
                    user_id,
                )
                await connection.execute(
                    """
                    INSERT INTO user_media (user_id, media_id, status)
                    SELECT user_id, $2, 'watchlist'
                    FROM shared_collection_members
                    WHERE collection_id = $1
                    ON CONFLICT (user_id, media_id) DO NOTHING
                    """,
                    collection_id,
                    media_id,
                )
                members = await connection.fetch(
                    "SELECT user_id FROM shared_collection_members WHERE collection_id = $1",
                    collection_id,
                )

        return {
            "title": media["title"],
            "media_type": media["media_type"],
            "collection_name": collection_name,
            "member_ids": [member["user_id"] for member in members],
        }

    async def get_collection(self, collection_id: int, user_id: int) -> dict[str, Any] | None:
        conn = await Rimiru.shion()
        async with conn.pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT collection.*
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
            items = await connection.fetch(
                """
                SELECT item.media_id, media.title, media.media_type
                FROM shared_collection_items AS item
                JOIN media ON media.id = item.media_id
                WHERE item.collection_id = $1
                ORDER BY item.added_at, media.title
                """,
                collection_id,
            )
        result = dict(row)
        result["items"] = [dict(item) for item in items]
        return result

    async def mark_watched(
        self,
        collection_id: int,
        media_id: int,
        user_id: int,
        everyone: bool = False,
    ) -> dict[str, Any]:
        """Mark an item watched and report the collection's resulting watch progress."""
        conn = await Rimiru.shion()
        async with conn.pool.acquire() as connection:
            async with connection.transaction():
                collection = await connection.fetchrow(
                    "SELECT owner_id, name FROM shared_collections WHERE id = $1 FOR UPDATE",
                    collection_id,
                )
                if not collection:
                    raise ValueError("Collection does not exist")
                is_member = await connection.fetchval(
                    """
                    SELECT EXISTS(
                        SELECT 1 FROM shared_collection_members
                        WHERE collection_id = $1 AND user_id = $2
                    )
                    """,
                    collection_id,
                    user_id,
                )
                if not is_member:
                    raise PermissionError("You are not a member of this collection")
                if everyone and collection["owner_id"] != user_id:
                    raise PermissionError("Only the owner can mark an item watched for everyone")

                title = await connection.fetchval(
                    "SELECT title FROM media WHERE id = $1", media_id
                )
                if title is None:
                    raise ValueError("That media is not in this collection")

                if everyone:
                    await connection.execute(
                        """
                        UPDATE user_media AS personal
                        SET status = 'watched', last_updated = now()
                        FROM shared_collection_members AS member
                        WHERE member.collection_id = $1
                          AND personal.user_id = member.user_id
                          AND personal.media_id = $2
                        """,
                        collection_id,
                        media_id,
                    )
                else:
                    await connection.execute(
                        """
                        UPDATE user_media
                        SET status = 'watched', last_updated = now()
                        WHERE user_id = $1 AND media_id = $2
                        """,
                        user_id,
                        media_id,
                    )

                members = await connection.fetch(
                    """
                    SELECT member.user_id, personal.status
                    FROM shared_collection_members AS member
                    LEFT JOIN user_media AS personal
                      ON personal.user_id = member.user_id
                     AND personal.media_id = $2
                    WHERE member.collection_id = $1
                    """,
                    collection_id,
                    media_id,
                )
                total_count = len(members)
                watched_count = sum(1 for member in members if member["status"] == "watched")
                completed = watched_count == total_count

                if completed:
                    await connection.execute(
                        """
                        DELETE FROM shared_collection_items
                        WHERE collection_id = $1 AND media_id = $2
                        """,
                        collection_id,
                        media_id,
                    )

        return {
            "title": title,
            "collection_name": collection["name"],
            "completed": completed,
            "watched_count": watched_count,
            "total_count": total_count,
            "member_ids": [member["user_id"] for member in members],
        }

    async def get_user_collections(self, user_id: int) -> list[dict[str, Any]]:
        conn = await Rimiru.shion()
        async with conn.pool.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT collection.id, collection.name, collection.collection_type,
                       member.role
                FROM shared_collections AS collection
                JOIN shared_collection_members AS member
                  ON member.collection_id = collection.id
                WHERE member.user_id = $1
                ORDER BY collection.name
                """,
                user_id,
            )
        return [dict(row) for row in rows]

    async def get_collection_id(self, user_id: int, name: str) -> int | None:
        """Resolve a collection name to its ID for a member."""
        collections = await self.get_user_collections(user_id)
        normalized_name = name.strip().casefold()
        for collection in collections:
            if collection["name"].casefold() == normalized_name:
                return collection["id"]
        return None


sharedCollectionManager = SharedCollectionManager()