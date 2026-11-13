"""Schema and helpers shared by SharedCollectionManager and SharedExtrasManager."""

import json

from rimiru import Rimiru

# Everything a shared collection keeps beyond its items and members. Idempotent; run on API
# startup and lazily by the bot. ON DELETE CASCADE so deleting a collection takes it all along.
SCHEMA = """
CREATE TABLE IF NOT EXISTS shared_collection_progress (
    collection_id BIGINT NOT NULL REFERENCES shared_collections(id) ON DELETE CASCADE,
    media_id INT NOT NULL REFERENCES media(id),
    user_id INT NOT NULL REFERENCES users(id),
    status VARCHAR(16) NOT NULL DEFAULT 'watching' CHECK (status IN ('watching', 'watched')),
    progress JSONB,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (collection_id, media_id, user_id)
);
ALTER TABLE shared_collections ADD COLUMN IF NOT EXISTS invite_code VARCHAR(12) UNIQUE;
ALTER TABLE shared_collections ADD COLUMN IF NOT EXISTS emoji VARCHAR(16);
ALTER TABLE shared_collections ADD COLUMN IF NOT EXISTS color VARCHAR(9);

-- 'admin' = co-owner: owner powers except roles, and the list can't be taken from the owner.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'shared_collection_members_role_v2') THEN
        ALTER TABLE shared_collection_members DROP CONSTRAINT IF EXISTS shared_collection_members_role_check;
        ALTER TABLE shared_collection_members ADD CONSTRAINT shared_collection_members_role_v2
            CHECK (role IN ('owner', 'admin', 'member'));
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS shared_collection_votes (
    collection_id BIGINT NOT NULL REFERENCES shared_collections(id) ON DELETE CASCADE,
    media_id INT NOT NULL REFERENCES media(id),
    user_id INT NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (collection_id, media_id, user_id)
);

CREATE TABLE IF NOT EXISTS shared_collection_ratings (
    collection_id BIGINT NOT NULL REFERENCES shared_collections(id) ON DELETE CASCADE,
    media_id INT NOT NULL REFERENCES media(id),
    user_id INT NOT NULL REFERENCES users(id),
    rating SMALLINT CHECK (rating BETWEEN 1 AND 5),
    reaction VARCHAR(16),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (collection_id, media_id, user_id)
);

CREATE TABLE IF NOT EXISTS shared_collection_comments (
    id BIGSERIAL PRIMARY KEY,
    collection_id BIGINT NOT NULL REFERENCES shared_collections(id) ON DELETE CASCADE,
    media_id INT NOT NULL REFERENCES media(id),
    user_id INT NOT NULL REFERENCES users(id),
    body TEXT NOT NULL CHECK (char_length(body) BETWEEN 1 AND 500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS shared_collection_comments_item
    ON shared_collection_comments (collection_id, media_id, id);

CREATE TABLE IF NOT EXISTS shared_collection_activity (
    id BIGSERIAL PRIMARY KEY,
    collection_id BIGINT NOT NULL REFERENCES shared_collections(id) ON DELETE CASCADE,
    user_id INT REFERENCES users(id),
    kind VARCHAR(24) NOT NULL,
    media_id INT REFERENCES media(id) ON DELETE SET NULL,
    target_user_id INT REFERENCES users(id),
    data JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS shared_collection_activity_recent
    ON shared_collection_activity (collection_id, id DESC);

CREATE TABLE IF NOT EXISTS shared_watch_parties (
    id BIGSERIAL PRIMARY KEY,
    collection_id BIGINT NOT NULL REFERENCES shared_collections(id) ON DELETE CASCADE,
    media_id INT NOT NULL REFERENCES media(id),
    created_by INT NOT NULL REFERENCES users(id),
    starts_at TIMESTAMPTZ NOT NULL,
    note VARCHAR(200),
    reminded_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS shared_watch_parties_upcoming ON shared_watch_parties (starts_at);

CREATE TABLE IF NOT EXISTS shared_watch_party_rsvps (
    party_id BIGINT NOT NULL REFERENCES shared_watch_parties(id) ON DELETE CASCADE,
    user_id INT NOT NULL REFERENCES users(id),
    going BOOLEAN NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (party_id, user_id)
);
"""

MANAGER_ROLES = {"owner", "admin"}

_ready = False


async def ensure_tables() -> None:
    global _ready
    if _ready:
        return
    conn = await Rimiru.shion()
    async with conn.pool.acquire() as connection:
        await connection.execute(SCHEMA)
    _ready = True


def loads(value):
    return json.loads(value) if isinstance(value, str) else value


async def require_member(connection, collection_id: int, user_id: int) -> str:
    """The user's role in the collection; PermissionError when they aren't in it."""
    role = await connection.fetchval(
        "SELECT role FROM shared_collection_members WHERE collection_id = $1 AND user_id = $2",
        collection_id,
        user_id,
    )
    if role is None:
        raise PermissionError("You are not a member of this collection")
    return role


async def require_item(connection, collection_id: int, media_id: int) -> str:
    title = await connection.fetchval(
        """
        SELECT media.title FROM shared_collection_items AS item
        JOIN media ON media.id = item.media_id
        WHERE item.collection_id = $1 AND item.media_id = $2
        """,
        collection_id,
        media_id,
    )
    if title is None:
        raise ValueError("That media is not in this collection")
    return title


# Progress logged by the same person on the same title within this window updates one feed
# entry ("logged S1 E3 → S1 E6") instead of adding one per episode.
PROGRESS_MERGE_MINUTES = 45


async def log_activity(
    connection,
    collection_id: int,
    user_id: int | None,
    kind: str,
    media_id: int | None = None,
    target_user_id: int | None = None,
    data: dict | None = None,
) -> None:
    """Append to a collection's activity feed. kinds: added, removed, progress, watched,
    finished, joined, left, rated, commented, party, nudge, renamed, role."""
    if kind == "progress":
        recent = await connection.fetchrow(
            f"""
            SELECT id, data FROM shared_collection_activity
            WHERE collection_id = $1 AND user_id = $2 AND media_id = $3 AND kind = 'progress'
              AND created_at > now() - interval '{PROGRESS_MERGE_MINUTES} minutes'
            ORDER BY id DESC LIMIT 1
            """,
            collection_id,
            user_id,
            media_id,
        )
        if recent:
            merged = {**(loads(recent["data"]) or {}), "to": (data or {}).get("to")}
            await connection.execute(
                "UPDATE shared_collection_activity SET data = $2::jsonb, created_at = now() WHERE id = $1",
                recent["id"],
                json.dumps(merged),
            )
            return
    await connection.execute(
        """
        INSERT INTO shared_collection_activity (collection_id, user_id, kind, media_id, target_user_id, data)
        VALUES ($1, $2, $3, $4, $5, $6::jsonb)
        """,
        collection_id,
        user_id,
        kind,
        media_id,
        target_user_id,
        json.dumps(data) if data is not None else None,
    )
