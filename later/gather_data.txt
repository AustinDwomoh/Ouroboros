import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Set
import discord
from discord.ext import commands
import asyncio
from settings import ErrorHandler
class DataMigrationManager:
    """Handles data migration from old Ouroboros database to new version"""
    
    def __init__(self, db_path: str = "data/serverstats.db"):
        self.db_path = db_path
        self.user_ids: Set[int] = set()
        self.output_dir = Path("dolo")
        self.output_dir.mkdir(exist_ok=True)
        
    def run_migration(self):
        """Main migration process"""
        print("Starting Ouroboros data migration...")
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get all server records
            cursor.execute("SELECT * FROM serverstats")
            records = cursor.fetchall()
            
            # Process each guild
            for record in records:
                self._process_guild(record)
            
            # Save user media data (shared across guilds)
            self._save_user_media()
            
            # Save collected user IDs
            self._save_user_ids()
            
            conn.close()
            print("✓ Migration completed successfully!")
            
        except Exception as e:
            print(f"✗ Migration failed: {e}")
            raise
    
    def _process_guild(self, record: tuple):
        """Process a single guild's data"""
        guild_data_dict = self._parse_guild_data(record)
        guild_id = guild_data_dict.get("guild_id")
        
        if not guild_id:
            print("⚠ No Guild ID found, skipping record...")
            return
        
        print(f"📊 Gathering data for Guild ID: {guild_id}")
        
        # Gather all guild-specific data
        guild_data_dict["notification_channel_id"] = self._get_notification_channel(guild_id)
        guild_data_dict["levels"] = self._get_levels(guild_id)
        guild_data_dict["efootball_scores"] = self._get_game_scores(guild_id)
        
        # Save guild data to JSON
        output_file = self.output_dir / f"guild_data_{guild_id}.json"
        with open(output_file, "w") as f:
            json.dump(guild_data_dict, f, indent=4)
        
        print(f"  ✓ Saved data for guild {guild_id}")
    
    def _parse_guild_data(self, record: tuple) -> Dict:
        """Convert database record into structured guild data dictionary"""
        template = {
            "guild_id": None,
            "welcome_channel_id": 0,
            "goodbye_channel_id": 0,
            "chat_channel_id": 0,
            "signup_channel_id": 0,
            "fixtures_channel_id": 0,
            "tourstate": False,
            "state": False,
            "player_role": "",
            "tour_manager_role": "",  # Fixed typo: "manger" -> "manager"
            "winner_role": "",
        }
        
        # Map incoming data to template keys
        keys = list(template.keys())
        data = {}
        
        for i, key in enumerate(keys):
            if i < len(record):
                data[key] = record[i]
            else:
                data[key] = template[key]
        
        return data
    
    def _get_notification_channel(self, guild_id: int) -> Optional[int]:
        """Get notification channel ID for a guild"""
        try:
            conn = sqlite3.connect("data/notifications_records.db")
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT channel_id FROM channels WHERE guild_id = ?",
                (guild_id,)
            )
            
            result = cursor.fetchone()
            channel_id = result[0] if result else None
            
            conn.close()
            return channel_id
            
        except sqlite3.Error as e:
            print(f"  ⚠ Error fetching notification channel for guild {guild_id}: {e}")
            return None
    
    def _get_levels(self, guild_id: int) -> Dict[int, Dict]:
        """Get leveling data for a guild"""
        levels = {}
        
        try:
            conn = sqlite3.connect("data/leveling.db")
            cursor = conn.cursor()
            
            cursor.execute(f"SELECT * FROM levels_{guild_id}")
            rows = cursor.fetchall()
            
            for row in rows:
                user_id = row[0]
                level = row[1]
                xp = row[2]
                
                self.user_ids.add(user_id)
                levels[user_id] = {"level": level, "xp": xp}
            
            conn.close()
            print(f"  ✓ Loaded {len(levels)} user levels")
            
        except sqlite3.OperationalError as e:
            print(f"  ⚠ No levels table for guild {guild_id}: {e}")
        
        return levels
    
    def _get_game_scores(self, guild_id: int) -> Dict[int, int]:
        """Get eFootball game scores for a guild"""
        scores = {}
        
        try:
            conn = sqlite3.connect("data/game_records.db")
            cursor = conn.cursor()
            
            cursor.execute(f"SELECT * FROM efootball_scores_{guild_id}")
            rows = cursor.fetchall()
            
            for row in rows:
                user_id = row[0]
                score = row[1]
                
                self.user_ids.add(user_id)
                scores[user_id] = score
            
            conn.close()
            print(f"  ✓ Loaded {len(scores)} eFootball scores")
            
        except sqlite3.OperationalError as e:
            print(f"  ⚠ No eFootball table for guild {guild_id}: {e}")
        
        return scores
    
    def _get_user_media(self) -> List[Dict]:
        """Get user media data (movies, series, watchlist)"""
        media_list = []
        user_id = '755872891601551511'  # Consider making this configurable
        
        try:
            conn = sqlite3.connect("data/mediarecords.db")
            cursor = conn.cursor()
            
            # Get movies
            media_list.extend(self._get_media_from_table(cursor, f"{user_id}_Movies", "movie"))
            
            # Get series
            media_list.extend(self._get_series_from_table(cursor, f"{user_id}_Series"))
            
            # Get movie watchlist
            media_list.extend(self._get_media_from_table(cursor, f"{user_id}_watch_list_Movies", "watchlist_movie"))
            
            # Get series watchlist
            media_list.extend(self._get_media_from_table(cursor, f"{user_id}_watch_list_Series", "watchlist_series"))
            
            conn.close()
            print(f"✓ Loaded {len(media_list)} media items")
            
        except sqlite3.Error as e:
            print(f"⚠ Error loading media data: {e}")
        
        return media_list
    
    def _get_media_from_table(self, cursor, table_name: str, media_type: str) -> List[Dict]:
        """Helper to get media from a specific table"""
        media_list = []
        
        try:
            cursor.execute(f'SELECT title FROM "{table_name}"')
            records = cursor.fetchall()
            
            for record in records:
                media_list.append({
                    "title": record[0],
                    "type": media_type
                })
        except sqlite3.OperationalError:
            print(f"  ⚠ Table {table_name} not found")
        
        return media_list
    
    def _get_series_from_table(self, cursor, table_name: str) -> List[Dict]:
        """Helper to get series data with season and episode info"""
        series_list = []
        
        try:
            cursor.execute(f'SELECT title, season, episode FROM "{table_name}"')
            records = cursor.fetchall()
            
            for record in records:
                series_list.append({
                    "title": record[0],
                    "season": record[1],
                    "episode": record[2],
                    "type": "series"
                })
        except sqlite3.OperationalError:
            print(f"  ⚠ Table {table_name} not found")
        
        return series_list
    
    def _save_user_media(self):
        """Save user media data to JSON"""
        media_data = self._get_user_media()
        output_file = self.output_dir / "user_media.json"
        
        with open(output_file, "w") as f:
            json.dump(media_data, f, indent=4)
        
        print(f"✓ Saved user media data")
    
    def _save_user_ids(self):
        """Save collected user IDs to JSON"""
        output_file = self.output_dir / "user_ids.json"
        
        with open(output_file, "w") as f:
            json.dump(list(self.user_ids), f, indent=4)
        
        print(f"✓ Saved {len(self.user_ids)} unique user IDs")


class NotificationManager:
    """Handles sending notifications to users about the update"""
    
    RELEASE_DATE = "February 1st, 2026"
    DOWNTIME_DATES = "Thursday, Friday, and Saturday (January 29-31, 2026)"
    
    @staticmethod
    def create_announcement_embed() -> discord.Embed:
        """Create the announcement embed for Ouroboros 2.0"""
        embed = discord.Embed(
            title="🎉 Ouroboros 2.0 is Coming Soon!",
            description=(
                "Dear Ouroboros Users,\n\n"
                "We are excited to announce that **Ouroboros 2.0** will be launching soon "
                "with a host of new features and improvements to enhance your experience.\n\n"
                "Thank you for your continued support!\n\n"
                "— *Inphinithy*"
            ),
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow()
        )
        
        # Release information
        embed.add_field(
            name="📅 Release Date",
            value=(
                f"**{NotificationManager.RELEASE_DATE}**\n\n"
                f"⚠️ **Scheduled Downtime:** {NotificationManager.DOWNTIME_DATES}\n"
                "During this period, the bot will be offline for migration and testing."
            ),
            inline=False
        )
        
        # Data migration info
        embed.add_field(
            name="💾 Data Migration",
            value=(
                "All your data will be safely transferred to the new version:\n"
                "• ✅ User levels and XP\n"
                "• ✅ eFootball scores from game servers\n"
                "• ✅ Server configurations\n"
                "• ✅ Media tracking data"
            ),
            inline=False
        )
        
        # We want your feedback
        embed.add_field(
            name="💡 Share Your Ideas",
            value=(
                "We'd love to hear from you! Use the `/suggest` command to share:\n"
                "• Feature requests\n"
                "• Improvements you'd like to see\n"
                "• Any feedback about the bot\n\n"
                "Your input helps shape Ouroboros 2.0!"
            ),
            inline=False
        )
        
        # Deprecated features
        embed.add_field(
            name="🔄 Changes in Version 2.0",
            value=(
                "**Removed Features:**\n"
                "• ❌ All fintech commands\n"
                "• ❌ Most channel management commands (except `/hi` and `/help`)\n"
                "• ❌ YouTube and X (Twitter) notification watchers\n\n"
                "**Improved Features:**\n"
                "• ✨ Redesigned media commands for easier use\n"
                "• ✨ Better user interface and experience\n"
                "• ✨ Enhanced performance and reliability"
            ),
            inline=False
        )
        
        # New feature proposal
        embed.add_field(
            name="🏆 Proposed Feature: Global Rankings",
            value=(
                "We're considering a **global ranking system** for:\n"
                "• Game scores across all servers\n"
                "• Level rankings worldwide\n\n"
                "This will only be implemented if the majority of our 2000+ users agree. "
                "Share your thoughts using `/suggest`!"
            ),
            inline=False
        )
        
        embed.set_footer(text="Ouroboros Bot | Thank you for being part of our community!")
        
        return embed
    
    @staticmethod
    async def notify_users(bot: commands.Bot, user_ids_file: str = "dolo/user_ids.json"):
        """Send notification to all users"""
        try:
            print("📢 Starting user notifications...")
            with open(user_ids_file, "r") as f:
                user_ids = json.load(f)
            user_ids = set(user_ids)  # Ensure uniqueness
            #user_ids = ["755872891601551511"] 
        except FileNotFoundError:
            print(f"⚠ User IDs file not found: {user_ids_file}")
            return
        
        embed = NotificationManager.create_announcement_embed()
        
        success_count = 0
        failed_count = 0
        
        print(f"📨 Sending notifications to {len(user_ids)} users...")
        
        for user_id in user_ids:
            try:
                user = await bot.fetch_user(int(user_id))
                await user.send(embed=embed)
                success_count += 1
                
                # Rate limiting - be nice to Discord API
                if success_count % 10 == 0:
                    print(f"  ✓ Sent {success_count}/{len(user_ids)} notifications")
                    await asyncio.sleep(1)  # Small delay every 10 messages
                    
            except discord.Forbidden:
                failed_count += 1
                print(f"  ⚠ User {user_id} has DMs disabled")
            except discord.NotFound:
                failed_count += 1
                print(f"  ⚠ User {user_id} not found")
            except Exception as e:
                failed_count += 1
                print(f"  ✗ Failed to notify user {user_id}: {e}")
        
            

        msg = f"\n✓ Notification complete!\n" +f"  • Successful: {success_count}" + f"  • Failed: {failed_count}"
        ErrorHandler().handle(msg,"Update state")
        


def main():
    """Run the data migration"""
    migrator = DataMigrationManager("data/serverstats.db")
    migrator.run_migration()
    """Notify users about the update"""
    # Note: To run the notification, you need to have a running Discord bot instance.
   # NotificationManager.notify_users(bot=None)  # Replace 'None' with your bot instance


if __name__ == "__main__":
    main()