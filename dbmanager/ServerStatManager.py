import sqlite3
from settings import ErrorHandler

errorHandler = ErrorHandler()

def create_connection(db_path="data/serverstats.db"):
    return sqlite3.connect(db_path)

def setup_database():
    with create_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS serverstats (
                guild_id INTEGER PRIMARY KEY,
                welcome_channel_id INTEGER,
                goodbye_channel_id INTEGER,
                chat_channel_id INTEGER,
                signup_channel_id INTEGER,
                fixtures_channel_id INTEGER,
                guidelines_channel_id INTEGER,
                tourstate TEXT DEFAULT 'off',
                state TEXT DEFAULT 'off',
                player_role TEXT DEFAULT 'Tour Player',
                tour_manager_role TEXT DEFAULT 'Tour manager',
                winner_role TEXT DEFAULT '🥇Champ'
           
            )
        """
        )

        """ cursor.execute(f"PRAGMA table_info(serverstats)")
        columns = [row[1] for row in cursor.fetchall()]  # Get column names

        if "player_role" not in columns:
            cursor.execute(
                "ALTER TABLE serverstats ADD COLUMN player_role TEXT DEFAULT 'Tour Player'"
            )

        if "tour_manager_role" not in columns:
            cursor.execute(
                "ALTER TABLE serverstats ADD COLUMN tour_manager_role TEXT DEFAULT 'Tour manager'"
            )

        if "winner_role" not in columns:
            cursor.execute(
                "ALTER TABLE serverstats ADD COLUMN winner_role TEXT DEFAULT '🥇Champ'"
            ) """#not needed for now
        conn.commit()

def get_server_state(guild_id):
    setup_database()
    with create_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT state FROM serverstats WHERE guild_id = ?
        """,
            (guild_id,),
        )
        result = cursor.fetchone()
        return result[0] if result else "off"

def get_role(guild_id, role):
    setup_database()
    with create_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT {role} FROM serverstats WHERE guild_id = ?
        """,
            (guild_id,),
        )
        result = cursor.fetchone()
        return result[0] if result else "No_role"

def set_role(guild_id, role_column, role_value):
        """
        Sets or updates a role in the serverstats table.

        :param guild_id: The Discord guild ID.
        :param role_column: The column name (player_role, tour_manager_role, or winner_role).
        :param role_value: The role name or ID to be stored.
        """
        try:
            setup_database()
            with create_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                f"""
                INSERT INTO serverstats (guild_id, {role_column})
                VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET {role_column} = excluded.{role_column}
            """,
                (guild_id, role_value),
            )
            conn.commit()

        except Exception as e:
            errorHandler.handle_exception(f"Error setting role for guild {guild_id}: {e}")

def get_server_tourstate(guild_id):
    setup_database()
    with create_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
        """
        SELECT tourstate FROM serverstats WHERE guild_id = ?
    """,
        (guild_id,),
    )
    result = cursor.fetchone()
    return result[0] if result else "off"

def set_server_state(guild_id, state):
    try:
        setup_database()
        with create_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO serverstats (guild_id, state)
                VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET state = ?
            """,
                (guild_id, state, state),
            )
            conn.commit()
    except Exception as e:
        errorHandler.handle_exception(f"Error setting server state for guild {guild_id}: {e}")
     

def set_server_tourstate( guild_id, state):
    try:
        setup_database()
        with create_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
            """
            INSERT INTO serverstats (guild_id, tourstate)
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET tourstate = ?
        """,
            (guild_id, state, state),
        )
        conn.commit()
    except Exception as e:
        errorHandler.handle_exception(f"Error setting server state for guild {guild_id}: {e}")


def set_channel_id( guild_id, channel_type, channel_id):
    if channel_type not in (
        "welcome",
        "goodbye",
        "chat",
        "signup",
        "fixtures",
        "guidelines",
    ):
        raise ValueError("Invalid channel type. Must be 'welcome' or 'goodbye'.")

    column = f"{channel_type}_channel_id"
    try:
        setup_database()
        with create_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
            f"""
            INSERT INTO serverstats (guild_id, {column})
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET {column} = ?
        """,
            (guild_id, channel_id, channel_id),
        )
        conn.commit()
    except Exception as e:
        errorHandler.handle_exception(f"Error setting {channel_type} channel for guild {guild_id}: {e}")


def get_greetings_channel_ids( guild_id):
    try:
        setup_database()
        with create_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
            """
            SELECT welcome_channel_id, goodbye_channel_id FROM serverstats WHERE guild_id = ?
        """,
            (guild_id,),
        )
        result = cursor.fetchone()
        return (
            {"welcome": result[0], "goodbye": result[1]}
            if result
            else {"welcome": None, "goodbye": None}
        )
    except Exception as e:
        errorHandler.handle_exception(f"Error fetching channel IDs for guild {guild_id}: {e}")
    
        return {"welcome": None, "goodbye": None}

def get_tour_channel_ids( guild_id):
    try:
        setup_database()
        with create_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
            """
            SELECT chat_channel_id, signup_channel_id, fixtures_channel_id, guidelines_channel_id 
            FROM serverstats WHERE guild_id = ?
        """,
            (guild_id,),
        )
        result = cursor.fetchone()

        if result:
            return {
                "chat": result[0],
                "signup": result[1],
                "fixtures": result[2],
                "guidelines": result[3],
            }
        else:
            errorHandler.handle_exception(f"No tour channel IDs found for guild {guild_id}")
            return {
                "chat": None,
                "signup": None,
                "fixtures": None,
                "guidelines": None,
            }

    except Exception as e:
        errorHandler.handle_exception(f"Error fetching tour channel IDs for guild {guild_id}: {e}")
        return {"chat": None, "signup": None, "fixtures": None, "guidelines": None}

def get_all_server_states():
    """Retrieve the on/off state for all guilds."""
    try:
        setup_database()
        with create_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT guild_id, state FROM serverstats")
        return dict(cursor.fetchall())
    except Exception as e:
        errorHandler.handle_exception(f"Error retrieving all server states: {e}")
        return {}

def get_all_server_tourstates(self):
    """Retrieve the on/off tourstate for all guilds."""
    try:
        setup_database()
        with create_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT guild_id, tourstate FROM serverstats")
        return dict(cursor.fetchall())
    except Exception as e:
        errorHandler.handle_exception(f"Error retrieving all server tour states: {e}")
        return {}

