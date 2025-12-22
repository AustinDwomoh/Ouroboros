from settings import ErrorHandler
from rimiru import Rimiru


error_handler = ErrorHandler()

# -------------------------------------------------------------
# STATE GETTERS / SETTERS
# -------------------------------------------------------------
async def get_server_state(guild_id: int):
    """Return 'on' or 'off' state for a guild."""
    conn = await Rimiru.shion()
    try:       
        val = await conn.select("servers", columns=["state"], filters={"guild_id": guild_id})
        return val['state'] or "off"
    except Exception as e:
        error_handler.handle(e, context="get_server_state")
        return "off"
  


async def set_server_state(guild_id: int, state: str):
    """Insert or update global on/off state for a guild."""
    conn = await Rimiru.shion()
    try:
        await conn.upsert("servers", {"guild_id": guild_id, "state": state}, conflict_column="guild_id")
    except Exception as e:
        error_handler.handle(e, context="set_server_state")
   


async def get_server_tourstate(guild_id: int):
    """Return 'on' or 'off' tournament state for a guild."""
    conn = await Rimiru.shion()
    try:
        val = await conn.select("servers", columns=["tourstate"], filters={"guild_id": guild_id})
        return val["tourstate"] or "off"
    except Exception as e:
        error_handler.handle(e, context="get_server_tourstate")
        return "off"
 


async def set_server_tourstate(guild_id: int, state: str):
    """Insert or update tournament on/off state for a guild."""
    conn = await Rimiru.shion()
    try:
        await conn.upsert("servers", {"guild_id": guild_id, "tourstate": state}, conflict_column="guild_id")
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
    conn = await Rimiru.shion()
    try:
        val = await conn.select("servers", columns=[role_column], filters={"guild_id": guild_id})
        return val[role_column] or "No_role"
    except Exception as e:
        error_handler.handle(e, context=f"get_role:{role_column}")
        return "No_role"



async def set_role(guild_id: int, role_column: str, role_value: str):
    """Insert or update a guild's stored role."""
    if role_column not in ("player_role", "tour_manager_role", "winner_role"):
        raise ValueError("Invalid role column")
    conn = await Rimiru.shion()
    try:
        return await conn.upsert("servers", {"guild_id": guild_id, role_column: role_value}, conflict_column="guild_id")
    except Exception as e:
        error_handler.handle(e, context=f"set_role:{role_column}")



# -------------------------------------------------------------
# CHANNEL MANAGEMENT
# -------------------------------------------------------------
async def set_channel_id(guild_id: int, channel_type: str, channel_id: int):
    """Set or update a specific channel ID in the serverstats table."""
    valid = ("welcome", "goodbye", "chat", "signup", "fixtures", "guidelines")
    if channel_type not in valid:
        raise ValueError(f"Invalid channel type: {channel_type}")
    column = f"{channel_type}_channel_id"
    conn = await Rimiru.shion()
    try:
       return await conn.upsert("servers", {"guild_id": guild_id, column: channel_id}, conflict_column="guild_id")
    except Exception as e:
        error_handler.handle(e, context=f"set_channel_id:{channel_type}")
 


async def get_greetings_channel_ids(guild_id: int):
    """Return welcome and goodbye channel IDs for a guild."""
    conn = await Rimiru.shion()
    try:
        row = await conn.select('servers', columns=["welcome_channel_id", "goodbye_channel_id"], filters={"guild_id": guild_id})
        if not row:
            return {"welcome": None, "goodbye": None}
       

        return {"welcome": row["welcome_channel_id"], "goodbye": row["goodbye_channel_id"]}
    except Exception as e:
        error_handler.handle(e, context="get_greetings_channel_ids")
        return {"welcome": None, "goodbye": None}



async def get_tour_channel_ids(guild_id: int):
    """Return all tournament-related channel IDs."""
    conn = await Rimiru.shion()
    try:
        row = await conn.select('servers', columns=["chat_channel_id", "signup_channel_id", "fixtures_channel_id", "guidelines_channel_id"], filters={"guild_id": guild_id})
        if not row:
            return {"chat": None, "signup": None, "fixtures": None, "guidelines": None}
        row = dict(row)
        return {
            "chat": row["chat_channel_id"],
            "signup": row["signup_channel_id"],
            "fixtures": row["fixtures_channel_id"],
            "guidelines": row["guidelines_channel_id"],
        }
    except Exception as e:
        error_handler.handle(e, context="get_tour_channel_ids")
        return {"chat": None, "signup": None, "fixtures": None, "guidelines": None}



# -------------------------------------------------------------
# GLOBAL OVERVIEW
# -------------------------------------------------------------
async def get_all_server_states():
    """Return mapping of all guilds and their active states."""
    conn = await Rimiru.shion()
    try:
        rows = await conn.select('servers', columns=["guild_id", "state"])
        return {r["guild_id"]: r["state"] for r in rows}
    except Exception as e:
        error_handler.handle(e, context="get_all_server_states")
        return {}



async def get_all_server_tourstates():
    """Return mapping of all guilds and their tournament states."""
    conn = await Rimiru.shion()
    try:
        rows = await conn.select('servers', columns=["guild_id", "tourstate"])
        return {r["guild_id"]: r["tourstate"] for r in rows}
    except Exception as e:
        error_handler.handle(e, context="get_all_server_tourstates")
        return {}

