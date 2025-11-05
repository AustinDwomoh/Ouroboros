from settings import create_async_pg_conn, ErrorHandler

error_handler = ErrorHandler()

# -------------------------------------------------------------
# STATE GETTERS / SETTERS
# -------------------------------------------------------------
async def get_server_state(guild_id: int):
    """Return 'on' or 'off' state for a guild."""
    conn = await create_async_pg_conn()
    try:
        val = await conn.fetchval(
            "SELECT state FROM serverstats WHERE guild_id=$1", guild_id
        )
        return val or "off"
    except Exception as e:
        error_handler.handle(e, context="get_server_state")
        return "off"
    finally:
        await conn.close()


async def set_server_state(guild_id: int, state: str):
    """Insert or update global on/off state for a guild."""
    conn = await create_async_pg_conn()
    try:
        await conn.execute("""
            INSERT INTO serverstats (guild_id, state)
            VALUES ($1, $2)
            ON CONFLICT (guild_id)
            DO UPDATE SET state = EXCLUDED.state, updated_at = now();
        """, guild_id, state)
    except Exception as e:
        error_handler.handle(e, context="set_server_state")
    finally:
        await conn.close()


async def get_server_tourstate(guild_id: int):
    """Return 'on' or 'off' tournament state for a guild."""
    conn = await create_async_pg_conn()
    try:
        val = await conn.fetchval(
            "SELECT tourstate FROM serverstats WHERE guild_id=$1", guild_id
        )
        return val or "off"
    except Exception as e:
        error_handler.handle(e, context="get_server_tourstate")
        return "off"
    finally:
        await conn.close()


async def set_server_tourstate(guild_id: int, state: str):
    """Insert or update tournament on/off state for a guild."""
    conn = await create_async_pg_conn()
    try:
        await conn.execute("""
            INSERT INTO serverstats (guild_id, tourstate)
            VALUES ($1, $2)
            ON CONFLICT (guild_id)
            DO UPDATE SET tourstate = EXCLUDED.tourstate, updated_at = now();
        """, guild_id, state)
    except Exception as e:
        error_handler.handle(e, context="set_server_tourstate")
    finally:
        await conn.close()


# -------------------------------------------------------------
# ROLE MANAGEMENT
# -------------------------------------------------------------
async def get_role(guild_id: int, role_column: str):
    """Return a specific role (player_role, tour_manager_role, or winner_role)."""
    if role_column not in ("player_role", "tour_manager_role", "winner_role"):
        raise ValueError("Invalid role column")
    conn = await create_async_pg_conn()
    try:
        query = f"SELECT {role_column} FROM serverstats WHERE guild_id=$1"
        val = await conn.fetchval(query, guild_id)
        return val or "No_role"
    except Exception as e:
        error_handler.handle(e, context=f"get_role:{role_column}")
        return "No_role"
    finally:
        await conn.close()


async def set_role(guild_id: int, role_column: str, role_value: str):
    """Insert or update a guild's stored role."""
    if role_column not in ("player_role", "tour_manager_role", "winner_role"):
        raise ValueError("Invalid role column")
    conn = await create_async_pg_conn()
    try:
        await conn.execute(f"""
            INSERT INTO serverstats (guild_id, {role_column})
            VALUES ($1, $2)
            ON CONFLICT (guild_id)
            DO UPDATE SET {role_column} = EXCLUDED.{role_column},
                          updated_at = now();
        """, guild_id, role_value)
    except Exception as e:
        error_handler.handle(e, context=f"set_role:{role_column}")
    finally:
        await conn.close()


# -------------------------------------------------------------
# CHANNEL MANAGEMENT
# -------------------------------------------------------------
async def set_channel_id(guild_id: int, channel_type: str, channel_id: int):
    """Set or update a specific channel ID in the serverstats table."""
    valid = ("welcome", "goodbye", "chat", "signup", "fixtures", "guidelines")
    if channel_type not in valid:
        raise ValueError(f"Invalid channel type: {channel_type}")
    column = f"{channel_type}_channel_id"
    conn = await create_async_pg_conn()
    try:
        await conn.execute(f"""
            INSERT INTO serverstats (guild_id, {column})
            VALUES ($1, $2)
            ON CONFLICT (guild_id)
            DO UPDATE SET {column} = EXCLUDED.{column},
                          updated_at = now();
        """, guild_id, channel_id)
    except Exception as e:
        error_handler.handle(e, context=f"set_channel_id:{channel_type}")
    finally:
        await conn.close()


async def get_greetings_channel_ids(guild_id: int):
    """Return welcome and goodbye channel IDs for a guild."""
    conn = await create_async_pg_conn()
    try:
        row = await conn.fetchrow("""
            SELECT welcome_channel_id, goodbye_channel_id
            FROM serverstats WHERE guild_id=$1
        """, guild_id)
        if not row:
            return {"welcome": None, "goodbye": None}
        return {"welcome": row["welcome_channel_id"], "goodbye": row["goodbye_channel_id"]}
    except Exception as e:
        error_handler.handle(e, context="get_greetings_channel_ids")
        return {"welcome": None, "goodbye": None}
    finally:
        await conn.close()


async def get_tour_channel_ids(guild_id: int):
    """Return all tournament-related channel IDs."""
    conn = await create_async_pg_conn()
    try:
        row = await conn.fetchrow("""
            SELECT chat_channel_id, signup_channel_id, fixtures_channel_id, guidelines_channel_id
            FROM serverstats WHERE guild_id=$1
        """, guild_id)
        if not row:
            return {"chat": None, "signup": None, "fixtures": None, "guidelines": None}
        return {
            "chat": row["chat_channel_id"],
            "signup": row["signup_channel_id"],
            "fixtures": row["fixtures_channel_id"],
            "guidelines": row["guidelines_channel_id"],
        }
    except Exception as e:
        error_handler.handle(e, context="get_tour_channel_ids")
        return {"chat": None, "signup": None, "fixtures": None, "guidelines": None}
    finally:
        await conn.close()


# -------------------------------------------------------------
# GLOBAL OVERVIEW
# -------------------------------------------------------------
async def get_all_server_states():
    """Return mapping of all guilds and their active states."""
    conn = await create_async_pg_conn()
    try:
        rows = await conn.fetch("SELECT guild_id, state FROM serverstats")
        return {r["guild_id"]: r["state"] for r in rows}
    except Exception as e:
        error_handler.handle(e, context="get_all_server_states")
        return {}
    finally:
        await conn.close()


async def get_all_server_tourstates():
    """Return mapping of all guilds and their tournament states."""
    conn = await create_async_pg_conn()
    try:
        rows = await conn.fetch("SELECT guild_id, tourstate FROM serverstats")
        return {r["guild_id"]: r["tourstate"] for r in rows}
    except Exception as e:
        error_handler.handle(e, context="get_all_server_tourstates")
        return {}
    finally:
        await conn.close()
