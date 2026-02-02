from settings import ErrorHandler
from rimiru import Rimiru
from constants import Roles,channelType

error_handler = ErrorHandler()

# -------------------------------------------------------------
# STATE GETTERS / SETTERS
# -------------------------------------------------------------
async def get_server_state(guild_id: int):
    """Return 'on' or 'off' state for a guild."""
    conn = await Rimiru.shion()
    try:       
        val = await conn.select("servers", columns=["state"], filters={"guild_id": guild_id})
        if not val:
            return "off"
        return val[0]['state'] or "off"
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
        val = await conn.selectOne("servers", columns=["tourstate"], filters={"guild_id": guild_id})
        return val.get("tourstate") if val else "off"
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



# -------------------------------------------------------------
# ROLE MANAGEMENT
# -------------------------------------------------------------
async def get_role(guild_id: int, role: Roles) -> str:
    """Return a specific role (player_role, tour_manager_role, or winner_role)."""
    if role not in Roles.get_roles():
        raise ValueError("Invalid role column")
    conn = await Rimiru.shion()
    try:
        val = await conn.selectOne("servers", columns=[role.value], filters={"guild_id": guild_id})
        return val.get(role.value) if val else Roles.NONE.value
    except Exception as e:
        error_handler.handle(e, context=f"get_role:{role.value}")
        return Roles.NONE.value



async def set_role(guild_id: int, role: Roles, role_value: str):
    """Insert or update a guild's stored role."""
    if role not in Roles.get_roles():
        raise ValueError("Invalid role column")
    conn = await Rimiru.shion()
    try:
        return await conn.upsert("servers", {"guild_id": guild_id, role.value: role_value}, conflict_column="guild_id")
    except Exception as e:
        error_handler.handle(e, context=f"set_role:{role.value}")



# -------------------------------------------------------------
# CHANNEL MANAGEMENT
# -------------------------------------------------------------
async def set_channel_id(guild_id: int, channel: channelType, channel_id: int):
    """Set or update a specific channel ID in the serverstats table."""
    if channel not in channelType.get_channel_types():
        raise ValueError(f"Invalid channel type: {channel}")
    column = f"{channel.value}_channel_id"
    conn = await Rimiru.shion()
    try:
        await conn.upsert("servers", {"guild_id": guild_id, column: channel_id}, conflict_column="guild_id")

    except Exception as e:
        error_handler.handle(e, context=f"set_channel_id:{channel.value}")
 


async def get_greetings_channel_ids(guild_id: int):
    """Return welcome and goodbye channel IDs for a guild."""
    conn = await Rimiru.shion()
    try:
        row = await conn.select('servers', 
        columns=["welcome_channel_id", "goodbye_channel_id"], filters={"guild_id": guild_id})
        row = row[0] if row else None
        if not row:
            return {
                channelType.WELCOME.value: None, 
                channelType.GOODBYE.value: None}
       

        return {
            channelType.WELCOME.value: row["welcome_channel_id"], 
            channelType.GOODBYE.value: row["goodbye_channel_id"]
            }
    except Exception as e:
        error_handler.handle(e, context="get_greetings_channel_ids")
        return {channelType.WELCOME.value: None, 
                channelType.GOODBYE.value: None}



async def get_tour_channel_ids(guild_id: int):
    """Return all tournament-related channel IDs."""
    conn = await Rimiru.shion()
    try:
        row = await conn.selectOne('servers', columns=["chat_channel_id", "signup_channel_id", "fixtures_channel_id"], filters={"guild_id": guild_id})
        if not row:
            return {
                    channelType.CHAT.value: None, 
                    channelType.SIGNUP.value: None, 
                    channelType.FIXTURES.value: None, 
                    }
        row = dict(row)
        return {
            channelType.CHAT.value: row["chat_channel_id"],
            channelType.SIGNUP.value: row["signup_channel_id"],
            channelType.FIXTURES.value: row["fixtures_channel_id"],
        }
    except Exception as e:
        error_handler.handle(e, context="get_tour_channel_ids")
        return {
            channelType.CHAT.value: None, 
            channelType.SIGNUP.value: None, 
            channelType.FIXTURES.value: None, 
        }

async def get_tournament_servers():
    """Return a list of guild IDs with tournament state 'on'."""
    conn = await Rimiru.shion()
    try:
        rows = await conn.select('servers', columns=["guild_id","signup_channel_id","chat_channel_id","fixtures_channel_id"], filters={"tourstate": "on"})
        return {r["guild_id"]: {channelType.SIGNUP: r["signup_channel_id"], channelType.CHAT: r["chat_channel_id"], channelType.FIXTURES: r["fixtures_channel_id"]} for r in rows}
    except Exception as e:
        error_handler.handle(e, context="get_tournament_servers")
        return []

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


