from dataclasses import dataclass
from typing import Optional,List,Dict

@dataclass(frozen=True)
class User:
    id: int
    discord_id: str
    username: str
    efootball_score: Optional[Dict[str, int]] = None
    sporty_score: Optional[Dict[str, int]] = None
    rps_score: Optional[Dict[str, int]] = None
    levels: Optional[Dict[str, int]] = None
   


@dataclass
class Server:
    """
    Docstring for Server
    For now, Just trying to figure out whats going to go in the dataclass
    """
    id: int
    name: str 
    server_id: str
    game_scores: Dict
    levels: Dict
    channels: Optional[str] = None #will list the names of the channels in the server



@dataclass(frozen=True)
class Media:
    id: Optional[int] = None #set when the media is added to the database or being called from the database
    title: str
    tmbd_id: int = 0
    overview: Optional[str]
    genres: list[str]
    poster_url: Optional[str]
    status: Optional[str]
    homepage: Optional[str]
    release_date: Optional[str]


@dataclass(frozen=True)
class Series(Media):
    last_air_date: Optional[str]
    next_episode_date: Optional[str]
    next_episode_number: Optional[int]
    next_season_number: Optional[int]
    seasons: list[dict]
    last_episode: Optional[dict]

    @classmethod
    def build_series(cls, data: dict) -> "Series":
        """
        Builds a Series object from the provided data dictionary. This is used for creating a Series object from the data returned by the TMDB API.

       
        :param data: Json data returned by the TMDB API
        :return: series object
        :rtype: Series
        """
        return cls(
            tmdb_id=data.get("id"),
            title=data.get("title"),
            overview=data.get("overview"),
            genres=data.get("genres"),
            release_date=data.get("release_date"),
            poster_url=data.get("poster_url"),
            homepage=data.get("homepage"),
            status=data.get("status"),
            last_air_date=data.get("last_air_date"),
            next_episode_date=data.get("next_episode_date"),
            next_episode_number=data.get("next_episode_number"),
            next_season_number=data.get("next_season_number"),
            seasons=data.get("seasons"),
            last_episode=data.get("last_episode"),
        )
    
    @classmethod
    def build_series_from_dict(cls, data: dict) -> "Series":
        """
        Builds a Series object from the provided data dictionary. This is used for creating a Series object from the data stored in the database.
        
        :param data: Json data returned by the TMDB API
        :return: series object
        :rtype: Series
        """
        return cls(
            id=data.get("id"),
            tmdb_id=data.get("tmdb_id"),
            title=data.get("title"),
            overview=data.get("overview"),
            genres=data.get("genres"),
            release_date=data.get("release_date"),
            poster_url=data.get("poster_url"),
            homepage=data.get("homepage"),
            status=data.get("status"),
            last_air_date=data.get("last_air_date"),
            next_episode_date=data.get("next_episode_date"),
            next_episode_number=data.get("next_episode_number"),
            next_season_number=data.get("next_season_number"),
            seasons=data.get("seasons"),
            last_episode=data.get("last_episode"),
        )

@dataclass(frozen=True)
class Movie(Media):
    collection: Optional[dict] = None

    @classmethod
    def build_movie(cls, data: dict) -> "Movie":
        """
        Builds a Movie object from the provided data dictionary. This is used for creating a Movie object from the data returned by the TMDB API.
        
        :param cls: Description
        :param data: Json data returned by the TMDB API
        :return: movie object
        :rtype: Movie 
        """
        return cls(
            tmbd_id=data.get("id"),
            title=data.get("title"),
            overview=data.get("overview"),
            genres=data.get("genres"),
            release_date=data.get("release_date"),
            poster_url=data.get("poster_url"),
            homepage=data.get("homepage"),
            status=data.get("status"),
            collection=data.get("collection"),
        )

    @classmethod
    def build_movie_from_dict(cls, data: dict) -> "Movie":
        """
        Builds a Movie object from the provided data dictionary. This is used for creating a Movie object from the data stored in the database.
        
        :param data: Json data returned by the TMDB API
        :return: movie object
        :rtype: Movie 
        """
        return cls(
            id=data.get("id"),
            tmbd_id=data.get("tmdb_id"),
            title=data.get("title"),
            overview=data.get("overview"),
            genres=data.get("genres"),
            release_date=data.get("release_date"),
            poster_url=data.get("poster_url"),
            homepage=data.get("homepage"),
            status=data.get("status"),
            collection=data.get("collection"),
        )
@dataclass
class UserMedia:
    """
    Represents the relationship between a user and a piece of media (movie or series).
    The idea is to return a list of UserMedia objects for a given user, which can be used to display their media list.
    """
    user_id: int
    media_id: int
    media_type: str  # "movie" | "series"
    status: str      # watching | watched | paused | dropped | planned
    progress: Optional[dict] = None
    latest: Optional[dict] = None # latest episode or movie from the media list
    poster: Optional[str] = None
    last_updated: Optional[str] = None
