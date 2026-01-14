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
            try:
                print(f"Found data file: {file.name}")
                print(f"Guild ID: {file.stem}")
                if file.name == "user_ids.json":
                    print("Skipping user_ids.json")
                    continue
                self.guild_data.append(file.name)
            except Exception as e:
                print(f"Error processing file {file.name}: {e}")
                continue
        

    async def run(self):
        await self.setup()
        print("Starting server data insertion migration...")
        for filename in self.guild_data:
            print(f"Processing file: {filename}")
            with open(Path("old_migrations/data") / filename, 'r', encoding='utf-8') as f:
                data = json.load(f) 
            print(f"Loaded data for guild {filename}: {data.keys()}")
            #print(type(data["guild_id"]))
            data_to_insert = {
              "guild_id": data["guild_id"],
                "welcome_channel_id": data.get("welcome_channel_id") if data.get("welcome_channel_id") not in (None, "Null") else None,
                "goodbye_channel_id": data.get("goodbye_channel_id") if data.get("goodbye_channel_id") not in (None, "Null") else None,
                "chat_channel_id": data.get("chat_channel_id") if data.get("chat_channel_id") not in (None, "Null") else None,
                "signup_channel_id": data.get("signup_channel_id") if data.get("signup_channel_id") not in (None, "Null") else None,
                "fixtures_channel_id": data.get("fixtures_channel_id") if data.get("fixtures_channel_id") not in (None, "Null") else None,
                "tourstate": data.get("tourstate") if data.get("tourstate") not in (None, "Null") else None,
                "state": data.get("state"),
                "player_role": data.get("player_role"),
                "tour_manager_role": data.get("tour_manager_role"),
                "winner_role": data.get("winner_role")
            }
            await self.rimiru.upsert("servers", data_to_insert, conflict_column="guild_id")
            levels = data.get("levels", {})
            for user_id, level_value in levels.items():
                await self.rimiru.upsert("levels", {"user_id": int(user_id),"guild_id": data["guild_id"],"level": int(level_value.get("level")),"xp":int(level_value.get("xp"))},conflict_column="user_id, guild_id")

            game_scores = data.get("efootball_scores", {})
            for player_id, score in game_scores.items():
                await self.rimiru.upsert("game_scores", {"user_id": int(player_id),"guild_id": data["guild_id"],"score":int(score),"game_type": "efootball"},conflict_column="user_id, guild_id,game_type")
            

if __name__ == "__main__":
    migration = InsertServerDataMigration()
    import asyncio
    #asyncio.run(migration.setup())
    asyncio.run(migration.run())
