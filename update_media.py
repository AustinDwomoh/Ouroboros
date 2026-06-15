import asyncio
import argparse
from dbmanager.MovieManager import MovieManager

async def main(target: str):
    manager = MovieManager()
    
    if target in ("series", "all"):
        await manager.series_background_updater()
    if target in ("movies", "all"):
        await manager.movie_background_updater()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=["series", "movies", "all"], default="all")
    args = parser.parse_args()
    asyncio.run(main(args.target))