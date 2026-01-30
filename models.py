from dataclasses import dataclass, field
import json
import random
from typing import Any, Optional,List,Dict
from constants import Status, WatchStatus, MediaType
from datetime import datetime, date

# ============================================================================ #
#                                     NOTES                                    #
# ============================================================================ #
# This module defines data models for users, servers, and media entities.
# The models include user scores, server details, and media information.
# These models facilitate structured data handling within the application.
# TODO: test models and ensure they meet application needs. Also consider expanding
# with additional fields or methods as necessary.
# ============================================================================ #

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
    game_scores: Dict[str, int]
    levels: Dict[str, int]
    channels: Optional[str] = None #will list the names of the channels in the server




@dataclass(frozen=True)
class Media:
    title: str
    tmdb_id: int
    id: Optional[int] = None
    overview: Optional[str] = None
    poster_path: Optional[str] = None
    status: Optional[str] = None
    homepage: Optional[str] = None
    release_date: Optional[date] = None
    
    @staticmethod
    def _parse_date(date_value) -> Optional[date]:
        """Parse date from string or date object"""
        if not date_value:
            return None
        if isinstance(date_value, date):
            return date_value
        try:
            return datetime.strptime(date_value, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None
    
    @property
    def poster_url(self) -> Optional[str]:
        if not self.poster_path:
            return None
        return f"https://image.tmdb.org/t/p/w500{self.poster_path}"


@dataclass(frozen=True)
class Episode:
    """Represents a single episode"""
    episode_number: int
    season_number: int
    name: str
    air_date: Optional[date] = None
    overview: Optional[str] = None
    still_path: Optional[str] = None
    
    @property
    def is_released(self) -> bool:
        if not self.air_date:
            return False
        return self.air_date <= date.today()
    
    @property
    def days_until_release(self) -> Optional[int]:
        if not self.air_date:
            return None
        return (self.air_date - date.today()).days
    
    def to_dict(self) -> dict:
        """Convert to dict for DB storage"""
        return {
            "episode_number": self.episode_number,
            "season_number": self.season_number,
            "name": self.name,
            "air_date": self.air_date.isoformat() if self.air_date else None,
            "overview": self.overview,
            "still_path": self.still_path,
        }
    
    @classmethod
    def from_dict(cls, data: Optional[dict]) -> Optional["Episode"]:
        """Build Episode from dict (from DB or API)"""
        #print("Building Episode from dict:", type(data))
        data = json.loads(data) if isinstance(data, str) else data
        if not data:
            return None
        return cls(
            episode_number=data["episode_number"],
            season_number=data["season_number"],
            name=data["name"],
            air_date=Media._parse_date(data.get("air_date")),
            overview=data.get("overview"),
            still_path=data.get("still_path"),
        )


@dataclass(frozen=True)
class Series(Media):
    first_air_date: Optional[date] = None
    last_air_date: Optional[date] = None
    number_of_episodes: Optional[int] = None
    number_of_seasons: Optional[int] = None
    last_episode_to_air: Optional[Episode] = None
    next_episode_to_air: Optional[Episode] = None
    in_production: Optional[bool] = None
    seasons: Optional[dict] = None

    @classmethod
    def from_api(cls, data: dict) -> "Series":
        """Build Series from TMDB API response"""
        last_ep_data = data.get("last_episode_to_air")
        last_episode = Episode.from_dict(last_ep_data)
        
        next_ep_data = data.get("next_episode_to_air")
        next_episode = Episode.from_dict(next_ep_data)
        
        return cls(
            title=data.get("name") or data.get("original_name"),
            tmdb_id=data["id"],
            overview=data.get("overview"),
            poster_path=data.get("poster_path"),
            status=data.get("status"),
            homepage=data.get("homepage"),
            release_date=cls._parse_date(data.get("first_air_date")),
            first_air_date=cls._parse_date(data.get("first_air_date")),
            last_air_date=cls._parse_date(data.get("last_air_date")),
            number_of_episodes=data.get("number_of_episodes"),
            number_of_seasons=data.get("number_of_seasons"),
            last_episode_to_air=last_episode,
            next_episode_to_air=next_episode,
            in_production=data.get("in_production"),
            seasons=data.get("seasons"),
        )
    
    @classmethod
    def from_db(cls, data: dict) -> "Series":
        """Build Series from database row"""
       # print("Building Series from DB:", data)
        last_episode = Episode.from_dict(data.get("last_episode_to_air"))
        next_episode = Episode.from_dict(data.get("next_episode_to_air"))
        return cls(
            id=data["id"],
            title=data["title"],
            tmdb_id=data["tmdb_id"],
            overview=data.get("overview"),
            poster_path=data.get("poster_path"),
            status=data.get("status"),
            homepage=data.get("homepage"),
            release_date=cls._parse_date(data.get("release_date")),
            first_air_date=cls._parse_date(data.get("first_air_date")),
            last_air_date=cls._parse_date(data.get("last_air_date")),
            number_of_episodes=data.get("number_of_episodes"),
            number_of_seasons=data.get("number_of_seasons"),
            last_episode_to_air=last_episode,
            next_episode_to_air=next_episode,
            in_production=data.get("in_production"),
            seasons=data.get("seasons"),
        )
    
    def to_db_dict(self) -> dict:
        """Convert to dict for DB insertion (for series table)"""
        return {
            "first_air_date": self.first_air_date,
            "last_air_date": self.last_air_date,
            "number_of_episodes": self.number_of_episodes,
            "number_of_seasons": self.number_of_seasons,
            "last_episode_to_air": self.last_episode_to_air.to_dict() if self.last_episode_to_air else None,
            "next_episode_to_air": self.next_episode_to_air.to_dict() if self.next_episode_to_air else None,
            "in_production": self.in_production,
            "seasons": self.seasons,
        }
    
    def to_media_dict(self) -> dict:
        """Convert to dict for DB insertion (for media table)"""
        return {
            "media_type": "series",
            "title": self.title,
            "tmdb_id": self.tmdb_id,
            "overview": self.overview,
            "poster_path": self.poster_path,
            "status": self.status,
            "homepage": self.homepage,
            "release_date": self.release_date,
        }
    
    @property
    def is_ended(self) -> bool:
        return self.status == "Ended"
    
    @property
    def has_new_episodes_coming(self) -> bool:
        return self.next_episode_to_air is not None
    
    @property
    def days_until_next_episode(self) -> Optional[int]:
        if not self.next_episode_to_air:
            return None
        return self.next_episode_to_air.days_until_release
    
    @property
    def should_alert_user(self) -> bool:
        """Check if user should be alerted (episode coming in next 7 days)"""
        days = self.days_until_next_episode
        if days is None:
            return False
        return 0 <= days <= 7
    
    @property
    def latest_release_info(self) -> str:
        if not self.last_episode_to_air:
            return "No episodes aired yet"
        ep = self.last_episode_to_air
        return f"S{ep.season_number}E{ep.episode_number}: {ep.name} (aired {ep.air_date})"
    
    @property
    def next_release_info(self) -> str:
        if self.is_ended:
            return "Series ended"
        if not self.next_episode_to_air:
            return "No upcoming episodes scheduled"
        
        ep = self.next_episode_to_air
        days = self.days_until_next_episode
        
        if days is None:
            return f"S{ep.season_number}E{ep.episode_number}: {ep.name} (TBA)"
        elif days < 0:
            return f"S{ep.season_number}E{ep.episode_number}: {ep.name} (aired {abs(days)} days ago)"
        elif days == 0:
            return f"S{ep.season_number}E{ep.episode_number}: {ep.name} (airs TODAY!)"
        else:
            return f"S{ep.season_number}E{ep.episode_number}: {ep.name} (in {days} days)"


@dataclass(frozen=True)
class Movie(Media):
    collection: Optional[dict] = None
    
    @classmethod
    def from_api(cls, data: dict) -> "Movie":
        return cls(
            title=data["title"],
            tmdb_id=data["id"],
            overview=data.get("overview"),
            poster_path=data.get("poster_path"),
            status=data.get("status"),
            homepage=data.get("homepage"),
            release_date=cls._parse_date(data.get("release_date")),
            collection=data.get("belongs_to_collection"),
        )
    
    @classmethod
    def from_db(cls, data: dict) -> "Movie":
        print("Building Movie from DB:", data)
        return cls(
            id=data["id"],
            title=data["title"],
            tmdb_id=data["tmdb_id"],
            overview=data.get("overview"),
            poster_path=data.get("poster_path"),
            status=data.get("status"),
            homepage=data.get("homepage"),
            release_date=cls._parse_date(data.get("release_date")),
            collection=data.get("collection"),
        )
    
    def to_db_dict(self) -> dict:
        """Convert to dict for DB insertion (for movies table)"""
        return {
            "collection": self.collection,
        }
    
    def to_media_dict(self) -> dict:
        """Convert to dict for DB insertion (for media table)"""
        return {
            "media_type": "movies",
            "title": self.title,
            "tmdb_id": self.tmdb_id,
            "overview": self.overview,
            "poster_path": self.poster_path,
            "status": self.status,
            "homepage": self.homepage,
            "release_date": self.release_date,
        }
    
    @property
    def is_released(self) -> bool:
        if not self.release_date:
            return False
        return self.release_date <= date.today()
    
    @property
    def days_until_release(self) -> Optional[int]:
        if not self.release_date:
            return None
        return (self.release_date - date.today()).days
    



@dataclass
class UserMedia:
    """
    Represents a user's relationship with a media item.
    Aligned with:
    - get_user_incomplete_media
    - get_user_media_by_id
    """

    # Core identifiers
    id: int
    media_type: MediaType
    title: str
    tmdb_id: int

    # Display info
    overview: Optional[str] = None
    poster_path: Optional[str] = None

    # Status info
    media_status: Optional[str] = None   # Airing, Ended, etc
    user_status: str = ""                # watching, watchlist, watched

    # Progress (authoritative, raw)
    progress: Optional[Dict[str, Any]] = None

    # Dates
    last_updated: Optional[datetime] = None

    last_episode_info: Optional[Dict[str, Any]] = None

    # Series-only
    next_episode_info: Optional[Dict[str, Any]] = None

    # -----------------------
    # Type helpers
    # -----------------------

    @property
    def is_movie(self) -> bool:
        return self.media_type == MediaType.MOVIE

    @property
    def is_series(self) -> bool:
        return self.media_type == MediaType.SERIES

    @property
    def is_completed(self) -> bool:
        """
        Movies: completed if watched
        Series: only completed if explicitly marked watched
        (no fake math)
        """
        return self.user_status.strip() == "watched"

    # -----------------------
    # Display helpers
    # -----------------------

    @property
    def poster_url(self) -> Optional[str]:
        if self.poster_path:
            return f"https://image.tmdb.org/t/p/w500{self.poster_path}"
        return None

    @property
    def next_episode_text(self) -> Optional[str]:
        if not self.next_episode_info:
            return None

        season = self.next_episode_info.get("season_number", "?")
        episode = self.next_episode_info.get("episode_number", "?")
        air_date = self.next_episode_info.get("air_date", "Unknown")
        name = self.next_episode_info.get("name")

        label = f"S{season}E{episode}"
        if name:
            label += f" — {name}"

        return f"{label}\nAirs: {air_date}"
    @property
    def last_episode_text(self) -> Optional[str]:
        if not self.last_episode_info:
            return None

        season = self.last_episode_info.get("season_number", "?")
        episode = self.last_episode_info.get("episode_number", "?")
        air_date = self.last_episode_info.get("air_date", "Unknown")
        name = self.last_episode_info.get("name")

        label = f"S{season}E{episode}"
        if name:
            label += f" — {name}"

        return f"{label}\nAired: {air_date}"
    @property
    def progress_text(self) -> Optional[str]:
        """
        Human-readable progress from JSONB.
        Assumes {season, episode} unless expanded later.
        """
        if not self.progress:
            return None

        season = self.progress.get("season")
        episode = self.progress.get("episode")

        if season and episode:
            return f"S{season}E{episode}"

        return None

    @property
    def color(self) -> int:
        return {
            "watching": 0x3498db,
            "watchlist": 0xf39c12,
            "watched": 0x2ecc71,
        }.get(self.user_status.strip(), 0x95a5a6)

    # -----------------------
    # Discord embed
    # -----------------------

    def to_embed_dict(self) -> Dict[str, Any]:
        data = {
            "title": f"{self.media_type.table_name.title()} • {self.title}",
            "thumbnail": self.poster_url,
            "color": self.color,
            "fields": []
        }

        if self.is_series:
            if self.progress_text:
                data["description"] = f"**Progress:** {self.progress_text}"
            else:
                data["description"] = "**Progress:** Not started"

            if self.next_episode_text:
                data["fields"].append({
                    "name": "Next Episode",
                    "value": self.next_episode_text,
                    "inline": False
                })
            else:
                data["fields"].append({
                    "name": "Next Episode",
                    "value": "No upcoming episodes scheduled",
                    "inline": False
                })
                data["fields"].append({
                    "name": "Latest Release",
                    "value": self.last_episode_text if self.last_episode_info else "No episodes aired yet",
                    "inline": False
                })

        else:
            data["description"] = "✓ Watched" if self.is_completed else "Not watched yet"

        if self.media_status:
            data["fields"].append({
                "name": "Status",
                "value": self.media_status,
                "inline": True
            })

        if self.overview:
            trimmed = self.overview[:200] + "..." if len(self.overview) > 200 else self.overview
            data["fields"].append({
                "name": " Overview",
                "value": trimmed,
                "inline": False
            })

        if self.last_updated:
            data["fields"].append({
                "name": " Last Activity",
                "value": self.last_updated.strftime("%b %d, %Y"),
                "inline": True
            })

        return data

    # -----------------------
    # Factory
    # -----------------------

    @classmethod
    def from_db(cls, row: Dict[str, Any]) -> "UserMedia":
       # print(type(row["next_episode_info"]), row["next_episode_info"])
        next_episode = None
        progress = None
        last_episode = None
        if isinstance(row.get("next_episode_info"), str):
            next_episode = json.loads(row["next_episode_info"]) if row["next_episode_info"] else None
        if isinstance(row.get("user_progress"), str):
            progress = json.loads(row["user_progress"]) if row["user_progress"] else None
        if isinstance(row.get("last_episode_info"), str):
            last_episode = json.loads(row["last_episode_info"]) if row["last_episode_info"] else None
       
        return cls(
            id=row["id"],
            media_type=MediaType.find_media_type(row["media_type"]),
            title=row["title"],
            tmdb_id=row["tmdb_id"],
            overview=row.get("overview"),
            poster_path=row.get("poster_path"),
            media_status=row.get("media_status") or row.get("status"),
            user_status=row.get("user_status", ""),
            progress=progress,
            last_episode_info=last_episode,
            last_updated=row.get("last_updated"),
            next_episode_info=next_episode,
        )



@dataclass
class Match:
    """Represents a single match between two players"""
    match_id: int
    players: List[int]
    guild_id: int
    winner: Optional[int] = None
    loser: Optional[int] = None
    status: Status = Status.PENDING
    results_submitted: bool = False
    ready_players: List[int] = field(default_factory=list)

    def is_ready(self) -> bool:
        """Check if all players are ready"""
        return len(self.ready_players) == len(self.players)

    def mark_ready(self, player_id: int) -> bool:
        """Mark a player as ready. Returns True if successful, False if already ready"""
        if player_id not in self.players:
            return False
        if player_id in self.ready_players:
            return False
        self.ready_players.append(player_id)
        if self.is_ready():
            self.status = Status.READY
        return True

    def get_opponent(self, player_id: int) -> Optional[int]:
        """Get the opponent of a given player"""
        return next((p for p in self.players if p != player_id), None)

    def record_result(self, winner_id: int, loser_id: int):
        """Record the match result"""
        self.winner = winner_id
        self.loser = loser_id
        self.status = Status.COMPLETED
        self.results_submitted = True


@dataclass
class Round:
    """Represents a tournament round with its matches and players"""
    round_number: int
    players: List[int] = field(default_factory=list)
    matches: List[Match] = field(default_factory=list)
    next_round_players: List[int] = field(default_factory=list)

    def create_matches(self, guild_id: int) -> List[int]:
        """
        Create matches from the current player list.
        Returns list of players who get a bye (odd player out).
        """
        self.matches.clear()
        random.shuffle(self.players)
        
        bye_players = []
        match_id = 1
        
        # Pair up players
        while len(self.players) >= 2:
            player1 = self.players.pop()
            player2 = self.players.pop()
            
            match = Match(
                match_id=match_id,
                players=[player1, player2],
                guild_id=guild_id
            )
            self.matches.append(match)
            match_id += 1
        
        # Handle odd player (gets a bye)
        if self.players:
            bye_players = self.players.copy()
            self.next_round_players.extend(bye_players)
        
        return bye_players

    def get_match_for_player(self, player_id: int) -> Optional[Match]:
        """Find the match a player is in"""
        return next((m for m in self.matches if player_id in m.players), None)

    def all_matches_completed(self) -> bool:
        """Check if all matches in the round are completed"""
        return all(m.status in [Status.COMPLETED, Status.CANCELLED] for m in self.matches)

    def get_winners(self) -> List[int]:
        """Get all winners from completed matches"""
        winners = []
        for match in self.matches:
            if match.status == Status.COMPLETED and match.winner:
                winners.append(match.winner)
        return winners

