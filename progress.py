"""Series progress maths shared by the API and the shared-collection manager (no DB access)."""

import json

FINISHED_STATUSES = {"ended", "canceled", "released"}


def _loads(value):
    return json.loads(value) if isinstance(value, str) else value


def episode_counts(seasons, last_aired, progress) -> dict | None:
    """{watched, aired}: episodes up to the last logged one vs. episodes aired so far,
    counted through the show's seasons (specials skipped). None when TMDB data is missing."""
    seasons, last_aired, progress = _loads(seasons), _loads(last_aired), _loads(progress)
    counts = {
        s["season_number"]: s.get("episode_count") or 0
        for s in seasons or []
        if s.get("season_number")
    }
    if not counts or not last_aired:
        return None
    before = lambda season: sum(c for n, c in counts.items() if n < season)
    aired = before(last_aired["season_number"]) + last_aired["episode_number"]
    if aired <= 0:
        return None
    watched = 0
    if progress and progress.get("season") and progress.get("episode"):
        watched = before(int(progress["season"])) + int(progress["episode"])
    return {"watched": min(watched, aired), "aired": aired}


def series_status(media_status, last_aired, progress) -> str:
    """'watched' once progress reaches the last aired episode of a show that won't get more,
    otherwise 'watching'. Same rule as MovieManager's SERIES_STATUS_SQL for personal lists."""
    last_aired, progress = _loads(last_aired), _loads(progress)
    if not progress or not last_aired or not progress.get("season") or not progress.get("episode"):
        return "watching"
    if (media_status or "").strip().lower() not in FINISHED_STATUSES:
        return "watching"
    reached = (int(progress["season"]), int(progress["episode"])) >= (
        int(last_aired["season_number"]),
        int(last_aired["episode_number"]),
    )
    return "watched" if reached else "watching"
