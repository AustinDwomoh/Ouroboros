
from discord import Enum


class gameType(Enum):
    pvp = "pvp"
    pvb = "pvb"
    sporty = "sporty"
    efootball = "efootball"

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