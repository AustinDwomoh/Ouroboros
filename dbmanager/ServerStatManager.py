import sqlite3
import logging


class ServerStatManager:
    def __init__(self, db_path="data/serverstats.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        self.setup_database()

    def setup_database(self):
        self.cursor.execute(
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

        self.cursor.execute(f"PRAGMA table_info(serverstats)")
        columns = [row[1] for row in self.cursor.fetchall()]  # Get column names

        if "player_role" not in columns:
            self.cursor.execute(
                "ALTER TABLE serverstats ADD COLUMN player_role TEXT DEFAULT 'Tour Player'"
            )

        if "tour_manager_role" not in columns:
            self.cursor.execute(
                "ALTER TABLE serverstats ADD COLUMN tour_manager_role TEXT DEFAULT 'Tour manager'"
            )

        if "winner_role" not in columns:
            self.cursor.execute(
                "ALTER TABLE serverstats ADD COLUMN winner_role TEXT DEFAULT '🥇Champ'"
            )
        self.conn.commit()

    def get_server_state(self, guild_id):
        self.cursor.execute(
            """
            SELECT state FROM serverstats WHERE guild_id = ?
        """,
            (guild_id,),
        )
        result = self.cursor.fetchone()
        return result[0] if result else "off"

    def get_role(self, guild_id, role):
        self.cursor.execute(
            f"""
            SELECT {role} FROM serverstats WHERE guild_id = ?
        """,
            (guild_id,),
        )
        result = self.cursor.fetchone()
        return result[0] if result else "No_role"

    def set_role(self, guild_id, role_column, role_value):
        """
        Sets or updates a role in the serverstats table.

        :param guild_id: The Discord guild ID.
        :param role_column: The column name (player_role, tour_manager_role, or winner_role).
        :param role_value: The role name or ID to be stored.
        """
        try:
            self.cursor.execute(
                f"""
                INSERT INTO serverstats (guild_id, {role_column})
                VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET {role_column} = excluded.{role_column}
            """,
                (guild_id, role_value),
            )
            self.conn.commit()

        except Exception as e:
            logging.error(f"Error setting role for guild {guild_id}: {e}")

    def get_server_tourstate(self, guild_id):
        self.cursor.execute(
            """
            SELECT tourstate FROM serverstats WHERE guild_id = ?
        """,
            (guild_id,),
        )
        result = self.cursor.fetchone()
        return result[0] if result else "off"

    def set_server_state(self, guild_id, state):
        try:
            self.cursor.execute(
                """
                INSERT INTO serverstats (guild_id, state)
                VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET state = ?
            """,
                (guild_id, state, state),
            )
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error setting server state for guild {guild_id}: {e}")

    def set_server_tourstate(self, guild_id, state):
        try:
            self.cursor.execute(
                """
                INSERT INTO serverstats (guild_id, tourstate)
                VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET tourstate = ?
            """,
                (guild_id, state, state),
            )
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error setting server state for guild {guild_id}: {e}")

    def set_channel_id(self, guild_id, channel_type, channel_id):
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
            self.cursor.execute(
                f"""
                INSERT INTO serverstats (guild_id, {column})
                VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET {column} = ?
            """,
                (guild_id, channel_id, channel_id),
            )
            self.conn.commit()
        except Exception as e:
            logging.error(
                f"Error setting {channel_type} channel for guild {guild_id}: {e}"
            )

    def get_greetings_channel_ids(self, guild_id):
        try:
            self.cursor.execute(
                """
                SELECT welcome_channel_id, goodbye_channel_id FROM serverstats WHERE guild_id = ?
            """,
                (guild_id,),
            )
            result = self.cursor.fetchone()
            return (
                {"welcome": result[0], "goodbye": result[1]}
                if result
                else {"welcome": None, "goodbye": None}
            )
        except Exception as e:
            logging.error(f"Error fetching channel IDs for guild {guild_id}: {e}")
            return {"welcome": None, "goodbye": None}

    def get_tour_channel_ids(self, guild_id):
        try:
            self.cursor.execute(
                """
                SELECT chat_channel_id, signup_channel_id, fixtures_channel_id, guidelines_channel_id 
                FROM serverstats WHERE guild_id = ?
            """,
                (guild_id,),
            )
            result = self.cursor.fetchone()

            if result:
                return {
                    "chat": result[0],
                    "signup": result[1],
                    "fixtures": result[2],
                    "guidelines": result[3],
                }
            else:
                logging.warning(f"No tour channel IDs found for guild {guild_id}")
                return {
                    "chat": None,
                    "signup": None,
                    "fixtures": None,
                    "guidelines": None,
                }

        except Exception as e:
            logging.error(f"Error fetching tour channel IDs for guild {guild_id}: {e}")
            return {"chat": None, "signup": None, "fixtures": None, "guidelines": None}

    def get_all_server_states(self):
        """Retrieve the on/off state for all guilds."""
        try:
            self.cursor.execute("SELECT guild_id, state FROM serverstats")
            return dict(self.cursor.fetchall())
        except Exception as e:
            logging.error(f"Error retrieving all server states: {e}")
            return {}

    def get_all_server_tourstates(self):
        """Retrieve the on/off tourstate for all guilds."""
        try:
            self.cursor.execute("SELECT guild_id, tourstate FROM serverstats")
            return dict(self.cursor.fetchall())
        except Exception as e:
            logging.error(f"Error retrieving all server tour states: {e}")
            return {}

    def close(self):
        self.conn.close()
