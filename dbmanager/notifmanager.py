from .pg_client import create_connection as _create_connection


def create_connection(db_path: str = "data/notifications_records.db"):
    # db_path ignored in Postgres-only mode
    return _create_connection()


# Function to create all static tables
def create_static_tables():
    """
    Creates static tables:
    - channels: Stores metadata about channels linked to guilds.
    """
    with create_connection() as conn:
        c = conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS channels (
                channel_id BIGINT PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                channel_name VARCHAR(255) NOT NULL
            );
            """
        )
        # platform_accounts is centralized; ensure it exists
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS platform_accounts (
                channel_id BIGINT NOT NULL REFERENCES channels(channel_id) ON DELETE CASCADE,
                platform_name TEXT NOT NULL,
                platform_id VARCHAR(255) NOT NULL,
                last_updated_content_id VARCHAR(255),
                PRIMARY KEY (channel_id, platform_name, platform_id)
            );
            """
        )
        conn.commit()


# Function to dynamically create platform-specific tables
def create_platform_table(platform_name, platform_column):
    # No dynamic per-platform tables in Postgres-only mode; platform_accounts is centralized.
    return


# Function to add or update a channel and link any platform accounts
def add_or_update_channel(
    channel_id, guild_id, channel_name, platform_name, platform_id):
    """
    Adds or updates a channel in the channels table, and links platform accounts if provided.
    """
    create_static_tables()
    with create_connection() as conn:
        c = conn.cursor()
        # Upsert channel
        c.execute(
            "INSERT INTO channels (channel_id, guild_id, channel_name) VALUES (%s,%s,%s) ON CONFLICT (channel_id) DO UPDATE SET guild_id = EXCLUDED.guild_id, channel_name = EXCLUDED.channel_name",
            (channel_id, guild_id, channel_name),
        )
        if platform_name and platform_id:
            add_platform_account(channel_id, platform_name, platform_id)
        conn.commit()


# Function to add a platform account ID for a specific channel
def add_platform_account(channel_id, platform_name, platform_id):
    """
    Adds a platform account ID (e.g., YouTube channel ID, Twitter handle) to the dynamic platform table for a specific channel.
    """
    if not platform_id:
        return
    with create_connection() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO platform_accounts (channel_id, platform_name, platform_id) VALUES (%s,%s,%s) ON CONFLICT (channel_id, platform_name, platform_id) DO UPDATE SET last_updated_content_id = EXCLUDED.last_updated_content_id",
            (channel_id, platform_name, platform_id),
        )
        conn.commit()


# Function to get platform IDs for a specific channel
def get_platform_ids_for_channel(channel_id, platform_name):
    """
    Retrieves the platform IDs (e.g., YouTube channel ID, Twitter handle) linked to a specific channel dynamically.
    """
    with create_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT platform_id FROM platform_accounts WHERE channel_id = %s AND platform_name = %s", (channel_id, platform_name))
        r = c.fetchone()
        return r[0] if r else None


# Ensure static tables are created
def get_channel_for_notification(guild_id, platform_name):
    """
    Retrieves a list of channel_ids that are subscribed to notifications for the given platform.
    Assumes that platform-specific tables exist and contain relevant platform IDs.
    """
    with create_connection() as conn:
        c = conn.cursor()
        c.execute(
            "SELECT c.channel_id FROM channels c JOIN platform_accounts p ON c.channel_id = p.channel_id WHERE c.guild_id = %s AND p.platform_name = %s",
            (guild_id, platform_name),
        )
        return [r[0] for r in c.fetchall()]


def update_last_updated_content(channel_id, platform_name, content_id):
    """
    Updates the last_updated_content_id for a specific channel in the platform table.
    """
    with create_connection() as conn:
        c = conn.cursor()
        c.execute(
            "UPDATE platform_accounts SET last_updated_content_id = %s WHERE channel_id = %s AND platform_name = %s",
            (content_id, channel_id, platform_name),
        )
        conn.commit()


def get_last_updated_content(channel_id, platform_name):
    """
    Retrieves the last updated video ID for a specific channel in the platform table.
    """
    with create_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT last_updated_content_id FROM platform_accounts WHERE channel_id = %s AND platform_name = %s", (channel_id, platform_name))
        r = c.fetchone()
        return r[0] if r else None


create_connection()
create_static_tables()
