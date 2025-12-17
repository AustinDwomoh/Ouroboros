from dataclasses import dataclass
from typing import Optional

@dataclass
class User:
    """
    Docstring for User
    For now, Just trying to figure out whats going to go in the dataclass
    """
    id: int
    username: str

    #games scores but how though?
    #4 games
    #efootball this is server based, which means each server has its own game state
    # , RPS vs  bot, no scores kept for this one
    # Sporty(two types tecnically but lets collapse them), Server based, scores kept
    #  RPS vs other user server based, scores kept
    #and for all the dm ones are not kept, so we can ignore those
    #so each gamme has its own var and then they store dicts and use the server id as the key
    #and then the value is a dict with the scores


    #levels also same principle, server based, so we use the server id as the key and then the value is a dict with the levels
   #then there is the media one so how to go about this in the db
   # we will have a user_watchd_movies and then we will somehow get the ids of thos tables and or somthing


@dataclass
class Server:
    """
    Docstring for Server
    For now, Just trying to figure out whats going to go in the dataclass
    """
    id: int
    name: str 
    game_scores: dict
    levels: dict
   
    channels: Optional[str] = None #will list the names of the channels in the server



@dataclass
class Media:
    """
    Docstring for Media
    For now, Just trying to figure out whats going to go in the dataclass
    """
    id: int
    title: str
    type: str #movie or tv show
    episodes: Optional[int] = None #only for tv shows
    release_date: Optional[str] = None #only for movies
    user_watchd_movies: dict #this will be a dict with the user id as the key and then the value is a list of the movies they have watched