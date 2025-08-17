import sqlite3


# Function to establish a database connection
def create_connection():
    """
    Establishes a connection to the SQLite database.
    """
    conn = sqlite3.connect("data/notifications_records.db")
    return conn


# Function to create all static tables
def create_static_tables():
    """
    Creates static tables:
    - channels: Stores metadata about channels linked to guilds.
    """
    try:
        with create_connection() as conn:
            c = conn.cursor()

            # Channels table: Stores channels linked to guilds
            c.execute(
                """ 
            CREATE TABLE IF NOT EXISTS channels (
                channel_id BIGINT PRIMARY KEY,        
                guild_id BIGINT NOT NULL,             
                channel_name VARCHAR(255) NOT NULL   
            );
            """
            )

            conn.commit()
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")


# Function to dynamically create platform-specific tables
def create_platform_table(platform_name, platform_column):
    """
    Dynamically creates a table for the platform with platform_column as the unique platform ID.
    """
    try:
        with create_connection() as conn:
            c = conn.cursor()

            # Dynamically create table for the platform
            table_name = f"{platform_name}_accounts"
            c.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    channel_id BIGINT NOT NULL,          
                    {platform_column} VARCHAR(255) NOT NULL,  
                    last_updated_content_id VARCHAR(255),  -- Column to track the last updated video ID
                    PRIMARY KEY (channel_id, {platform_column}),
                    FOREIGN KEY (channel_id) REFERENCES channels(channel_id) ON DELETE CASCADE
                );
            """
            )
            conn.commit()
    except sqlite3.Error as e:
        print(f"An error occurred while creating {platform_name} table: {e}")


# Function to add or update a channel and link any platform accounts
def add_or_update_channel(
    channel_id, guild_id, channel_name, platform_name, platform_id):
    """
    Adds or updates a channel in the channels table, and links platform accounts if provided.
    """
    create_static_tables()
    add_platform_account(channel_id, platform_name, platform_id)
    with create_connection() as conn:
        c = conn.cursor()

        # Check if the channel exists in the channels table
        c.execute(
            "SELECT channel_name FROM channels WHERE channel_id = :channel_id",
            {"channel_id": channel_id},
        )
        result = c.fetchone()
        if result:
            # Update the channel if it exists
            c.execute(
                "UPDATE channels SET channel_name = :channel_name WHERE channel_id = :channel_id",
                {"channel_name": channel_name, "channel_id": channel_id},
            )
        else:
            # Insert the new channel if it doesn't exist
            c.execute(
                "INSERT INTO channels (channel_id, guild_id, channel_name) VALUES (:channel_id, :guild_id, :channel_name)",
                {
                    "channel_id": channel_id,
                    "guild_id": guild_id,
                    "channel_name": channel_name,
                },
            )

        conn.commit()


# Function to add a platform account ID for a specific channel
def add_platform_account(channel_id, platform_name, platform_id):
    """
    Adds a platform account ID (e.g., YouTube channel ID, Twitter handle) to the dynamic platform table for a specific channel.
    """
    try:
        if not platform_id:
            print(f"Error: No {platform_name} ID provided for channel {channel_id}.")
            return
        with create_connection() as conn:
            c = conn.cursor()

            # Dynamically create the platform table if it doesn't exist
            platform_column = f"{platform_name}_id"
            create_platform_table(platform_name, platform_column)

            # Insert the platform account ID
            table_name = f"{platform_name}_accounts"
            c.execute(
                f"""
                INSERT INTO {table_name} (channel_id, {platform_column}) 
                VALUES (:channel_id, :platform_id)
            """,
                {"channel_id": channel_id, "platform_id": platform_id},
            )
            conn.commit()
    except sqlite3.Error as e:
        print(f"An error occurred while adding {platform_name} account: {e}")


# Function to get platform IDs for a specific channel
def get_platform_ids_for_channel(channel_id, platform_name):
    """
    Retrieves the platform IDs (e.g., YouTube channel ID, Twitter handle) linked to a specific channel dynamically.
    """
    try:
        with create_connection() as conn:
            c = conn.cursor()

            # Dynamically retrieve platform ID(s)
            platform_column = f"{platform_name}_id"
            table_name = f"{platform_name}_accounts"
            c.execute(
                f"SELECT {platform_column} FROM {table_name} WHERE channel_id = :channel_id",
                {"channel_id": channel_id},
            )
            result = c.fetchone()

            if result:
                return result[0]
            else:
                return None
    except sqlite3.Error as e:
        print(f"An error occurred while retrieving {platform_name} account: {e}")
        return None


# Ensure static tables are created
def get_channel_for_notification(guild_id, platform_name):
    """
    Retrieves a list of channel_ids that are subscribed to notifications for the given platform.
    Assumes that platform-specific tables exist and contain relevant platform IDs.
    """
    try:
        with create_connection() as conn:
            c = conn.cursor()

            # Dynamically create the platform column name based on platform_name
            platform_column = f"{platform_name}_id"
            table_name = f"{platform_name}_accounts"

            # Retrieve the channel_ids associated with the given platform and guild_id
            c.execute(
                f"""
            SELECT c.channel_id
            FROM channels c
            JOIN {table_name} p ON c.channel_id = p.channel_id
            WHERE c.guild_id = :guild_id
            """,
                {"guild_id": guild_id},
            )

            result = c.fetchall()
            return [
                channel_id[0] for channel_id in result
            ]  # Return a list of channel_ids

    except sqlite3.Error as e:

        return []


def update_last_updated_content(channel_id, platform_name, content_id):
    """
    Updates the last_updated_content_id for a specific channel in the platform table.
    """
    try:
        with create_connection() as conn:
            c = conn.cursor()

            # Update the last updated video ID
            platform_column = f"{platform_name}_id"
            table_name = f"{platform_name}_accounts"
            c.execute(
                f"""
                UPDATE {table_name}
                SET last_updated_content_id = :content_id
                WHERE channel_id = :channel_id
            """,
                {"channel_id": channel_id, "content_id": content_id},
            )
            conn.commit()
            print(f"Last updated video ID for {platform_name} updated successfully.")
    except sqlite3.Error as e:
        print(f"An error occurred while updating the last updated content ID: {e}")


def get_last_updated_content(channel_id, platform_name):
    """
    Retrieves the last updated video ID for a specific channel in the platform table.
    """
    try:
        with create_connection() as conn:
            c = conn.cursor()

            # Determine the platform-specific table and column name
            platform_column = f"{platform_name}_id"
            table_name = f"{platform_name}_accounts"

            # Query to fetch the last updated video ID for the given channel
            c.execute(
                f"""
                SELECT last_updated_content_id 
                FROM {table_name} 
                WHERE channel_id = :channel_id
            """,
                {"channel_id": channel_id},
            )

            # Fetch the result
            result = c.fetchone()

            if result:
                # Return the video ID if it exists
                return result[0]
            else:
                print(
                    f"No record found for channel ID {channel_id} on platform {platform_name}."
                )
                return None
    except sqlite3.Error as e:
        print(f"An error occurred while retrieving the last updated video ID: {e}")
        return None


create_connection()
create_static_tables()
