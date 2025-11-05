from settings import create_async_pg_conn, ErrorHandler

error_handler = ErrorHandler()

# -------------------------------------------------------------
# CHANNEL MANAGEMENT
# -------------------------------------------------------------
async def add_or_update_channel(channel_id: int, guild_id: int, channel_name: str):
    """
    Upsert a channel into the `channels` table.
    """
    conn = await create_async_pg_conn()
    try:
        await conn.execute("""
            INSERT INTO channels (channel_id, guild_id, channel_name)
            VALUES ($1, $2, $3)
            ON CONFLICT (channel_id)
            DO UPDATE SET guild_id = EXCLUDED.guild_id,
                          channel_name = EXCLUDED.channel_name,
                          updated_at = now();
        """, channel_id, guild_id, channel_name)
    except Exception as e:
        error_handler.handle(e, context="add_or_update_channel")
    finally:
        await conn.close()


# -------------------------------------------------------------
# PLATFORM ACCOUNT MANAGEMENT
# -------------------------------------------------------------
async def add_platform_account(channel_id: int, platform_name: str, platform_id: str):
    """
    Link a platform account (e.g. YouTube, Twitter) to a Discord channel.
    """
    if not platform_id:
        return
    conn = await create_async_pg_conn()
    try:
        await conn.execute("""
            INSERT INTO platform_accounts (channel_id, platform_name, platform_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (channel_id, platform_name, platform_id)
            DO NOTHING;
        """, channel_id, platform_name.lower(), platform_id)
    except Exception as e:
        error_handler.handle(e, context="add_platform_account")
    finally:
        await conn.close()


async def update_last_updated_content(channel_id: int, platform_name: str, content_id: str):
    """
    Update the last known content ID (e.g. latest YouTube video or Tweet) for a channel+platform.
    """
    conn = await create_async_pg_conn()
    try:
        await conn.execute("""
            UPDATE platform_accounts
            SET last_updated_content_id = $1,
                updated_at = now()
            WHERE channel_id = $2 AND platform_name = $3;
        """, content_id, channel_id, platform_name.lower())
    except Exception as e:
        error_handler.handle(e, context="update_last_updated_content")
    finally:
        await conn.close()


async def get_last_updated_content(channel_id: int, platform_name: str):
    """
    Retrieve the last known content ID for a channel/platform combination.
    """
    conn = await create_async_pg_conn()
    try:
        value = await conn.fetchval("""
            SELECT last_updated_content_id
            FROM platform_accounts
            WHERE channel_id = $1 AND platform_name = $2;
        """, channel_id, platform_name.lower())
        return value
    except Exception as e:
        error_handler.handle(e, context="get_last_updated_content")
        return None
    finally:
        await conn.close()


# -------------------------------------------------------------
# LOOKUPS
# -------------------------------------------------------------
async def get_platform_ids_for_channel(channel_id: int, platform_name: str):
    """Return all external platform IDs linked to a given Discord channel."""
    conn = await create_async_pg_conn()
    try:
        rows = await conn.fetch("""
            SELECT platform_id
            FROM platform_accounts
            WHERE channel_id = $1 AND platform_name = $2;
        """, channel_id, platform_name.lower())
        return [r["platform_id"] for r in rows]
    except Exception as e:
        error_handler.handle(e, context="get_platform_ids_for_channel")
        return []
    finally:
        await conn.close()


async def get_channels_for_notification(guild_id: int, platform_name: str):
    """
    Return all channel IDs in a guild that are subscribed to a given platform.
    """
    conn = await create_async_pg_conn()
    try:
        rows = await conn.fetch("""
            SELECT c.channel_id
            FROM channels c
            JOIN platform_accounts p ON c.channel_id = p.channel_id
            WHERE c.guild_id = $1 AND p.platform_name = $2;
        """, guild_id, platform_name.lower())
        return [r["channel_id"] for r in rows]
    except Exception as e:
        error_handler.handle(e, context="get_channels_for_notification")
        return []
    finally:
        await conn.close()
#TODO add a “global notification audit” helper that lists all registered platforms and channels across all guilds (for admin/debug dashboards