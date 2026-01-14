
from discord import Enum
import discord
from settings import ALLOWED_ID

class gameType(Enum):
    PVP = "pvp"
    PVB = "pvb"
    SPORTY = "sporty"
    EFOOTBALL = "efootball"

    @classmethod
    def get_game_types(cls):
        return [cls.PVP, cls.PVB, cls.SPORTY, cls.EFOOTBALL]
    
    @classmethod
    def find_game_type(cls, type_str: str):
        for gtype in cls:
            if gtype.value == type_str:
                return gtype
        return None


class FetchType(Enum):
    FETCH = "fetch"
    FETCHVAL = "fetchval"
    FETCHROW = "fetchrow"


class channelType(Enum):
    WELCOME = "welcome"
    GOODBYE = "goodbye"
    CHAT = "chat"
    SIGNUP = "signup"
    FIXTURES = "fixtures"
    GUIDELINES = "guidelines"

    @classmethod
    def get_channel_types(cls):
        return [
            cls.WELCOME,
            cls.GOODBYE,
            cls.CHAT,
            cls.SIGNUP,
            cls.FIXTURES,
            cls.GUIDELINES,
        ]
    
    @classmethod
    def find_channel_type(cls, type_str: str):
        for ctype in cls:
            if ctype.value == type_str:
                return ctype
        return None

class Status(Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    READY = "ready"
    WAITING = "waiting"

class WatchStatus(Enum):
    WATCHING = "watching"
    WATCHED = "watched"
    PAUSED = "paused"
    DROPPED = "dropped"
    PLANNED = "planned"
class MediaType(Enum):
    MOVIE = "movie"
    SERIES = "tv" 

    @classmethod
    def get_media_types(cls):
        return [cls.MOVIE, cls.SERIES]
    
    @classmethod
    def find_media_type(cls, type_str: str):
        mapping = {
            "movies": cls.MOVIE,
            "movie": cls.MOVIE,
            "tv": cls.SERIES,
            "series": cls.SERIES
        }
        result = mapping.get(type_str.lower())
        if result is None:
            raise ValueError(f"Unknown media type: {type_str}")
        return result
    
    @property
    def table_name(self):
        """Get the database table name"""
        tables = {
            MediaType.MOVIE: "movies",
            MediaType.SERIES: "series"
        }
        return tables[self]
class Roles(Enum):
    PLAYER = "player_role"
    TOUR_MANAGER = "tour_manager_role"
    WINNER = "winner_role"
    NONE = "No_role"

    @classmethod
    def get_roles(cls):
        return [cls.PLAYER, cls.TOUR_MANAGER, cls.WINNER]
    
    @classmethod
    def find_role(cls, role_str: str):
        for role in cls:
            if role.value == role_str:
                return role
        return None
    
    @classmethod
    def check_role_permission(cls, member: discord.Member, required_role_name: str=None) -> bool:
        """Check if a member has the required role or admin permissions."""
        if member.id in ALLOWED_ID:
            return True
        for role in member.roles:
            if (
                role.permissions.administrator
                or role.permissions.manage_roles
                or role.permissions.ban_members
                or role.permissions.kick_members
                or role.name == required_role_name 
                or member.id == member.guild.owner_id
            ):
                return True
        return False