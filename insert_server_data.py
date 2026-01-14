from rimiru import Rimiru
from pathlib import Path
import json
class InsertServerDataMigration:
    def __init__(self):
        self.rimiru = None
        self.guild_data = []
    
    async def setup(self):
        self.rimiru = await Rimiru.shion()
        Path("old_migrations/data").mkdir(parents=True, exist_ok=True)
        for file in Path("old_migrations/data").glob("*.json"):
            print(f"Found data file: {file.name}")
            print(f"Guild ID: {file.stem}")
            self.guild_data.append(file.name)

    async def run(self):
        print("Starting server data insertion migration...")
        for filename in self.guild_data:
            print(f"Processing file: {filename}")
            with open(Path("old_migrations/data") / filename, 'r', encoding='utf-8') as f:
                data = json.load(f) 
            print(f"Loaded data for guild {filename}: {data.keys()}")


            

if __name__ == "__main__":
    migration = InsertServerDataMigration()
    import asyncio
    asyncio.run(migration.setup())
    asyncio.run(migration.run())
