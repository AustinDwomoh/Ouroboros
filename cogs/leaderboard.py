# ============================================================================ #
#                                    IMPORT                                    #
# ============================================================================ #
import discord
from discord import app_commands
from discord.ext import commands
from cogs.leveling import LeaderboardPaginationView  
from settings import ErrorHandler
from io import BytesIO
from dbmanager.Games import get_leaderboard, get_player_scores
from settings import create_async_pg_conn


# ============================================================================ #
#                              LEADERBOARD COG                                 #
# ============================================================================ #
class Leaderboard(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.error_handler = ErrorHandler()

    # ============================ Leaderboard COMMAND =========================== #
    @app_commands.command(name="leaderboard", description="Mini Game Rankings")
    @app_commands.describe(
        game_type="Choose the type of game: 'pvp', 'sporty', 'pvb', 'efootball'"
    )
    @app_commands.guild_only()
    async def leaderboard(
        self, interaction: discord.Interaction, game_type: str = None
    ):
        """Show the leaderboard for the current guild with pagination or a specific game type."""
        await interaction.response.defer()
        
        try:
            if game_type:
                # Fetch specific game type scores
                rows = await get_player_scores(interaction.guild.id, game_type)
                if not rows:
                    await interaction.followup.send(f"No leaderboard available for {game_type}.")
                    return
                # Convert to tuple format (player_id, score)
                rows = [(row['player_id'], row['player_score']) for row in rows]
            else:
                # Fetch overall leaderboard
                rows = await get_leaderboard(interaction.guild.id)
                if not rows:
                    await interaction.followup.send("No leaderboard available.")
                    return
                # Convert to tuple format (player_id, total_score)
                rows = [(row['player_id'], row['total_score']) for row in rows]
            
            # Build leaderboard data with member info
            leaderboard_data = []
            for idx, (player_id, score) in enumerate(rows, start=1):
                member = interaction.guild.get_member(player_id)
                if member:
                    avatar_url = member.display_avatar.url
                    leaderboard_data.append((idx, member.display_name, score, 0, avatar_url))
            
            if not leaderboard_data:
                await interaction.followup.send("No active players found on the leaderboard.")
                return

            # Create pagination view
            pagination_view = LeaderboardPaginationView(
                data=leaderboard_data, sep=5, timeout=None
            )
            
            # Generate the first page's image
            page_data = pagination_view.get_current_page_data()
            img = pagination_view.generate_leaderboard_image(page_data)
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            buffer.seek(0)

            # Prepare discord file
            discord_file = discord.File(buffer, filename="leaderboard.png")

            # Create embed
            embed = discord.Embed(
                title=f"🏆 Leaderboard Page {pagination_view.current_page}/{pagination_view.get_total_pages()}",
                color=discord.Color.gold()
            )
            embed.set_image(url="attachment://leaderboard.png")
            embed.set_footer(text="Use the buttons below to navigate pages.")

            # Send initial message and store it
            pagination_view.message = await interaction.followup.send(
                embed=embed,
                file=discord_file,
                view=pagination_view
            )
            
        except Exception as e:
            self.error_handler.handle(e, context="leaderboard_command")
            await interaction.followup.send("An error occurred while fetching the leaderboard.")

    @leaderboard.autocomplete("game_type")
    async def game_type_autocomplete(
        self, interaction: discord.Interaction, current: str
    ):
        """Autocomplete for game types."""
        try:
            current = current.strip() if current else ""
            game_types = ["pvp", "sporty", "pvb", "efootball"]
            filtered_choices = [
                app_commands.Choice(name=game, value=game)
                for game in game_types
                if current.lower() in game.lower()
            ]
            if filtered_choices:
                await interaction.response.autocomplete(filtered_choices)
            else:
                await interaction.response.autocomplete(
                    [app_commands.Choice(name="No matches found", value="none")]
                )
        except discord.errors.NotFound:
            pass
        except Exception as e:
            self.error_handler.handle(e, context="leaderboard_autocomplete")

    # ================================ RANK SCRIPT =============================== #
    async def fetch_player_score(self, guild_id: int, game_type: str, player_id: int):
        """Fetch the player score from a specific game type."""
        try:
            conn = await create_async_pg_conn()
            try:
                row = await conn.fetchrow("""
                    SELECT player_score
                    FROM game_scores
                    WHERE guild_id = $1 AND game_type = $2 AND player_id = $3
                """, guild_id, game_type, player_id)
                return row['player_score'] if row else 0
            finally:
                await conn.close()
        except Exception as e:
            self.error_handler.handle(e, context=f"fetch_player_score_{game_type}")
            return 0

    @app_commands.guild_only()
    @app_commands.command(name="rank", description="Rank with score in mini games")
    async def rank(
        self, interaction: discord.Interaction, member: discord.Member = None
    ):
        """Show the rank of a member in the current guild."""
        await interaction.response.defer()
        
        if member is None:
            member = interaction.user
        
        guild_id = interaction.guild.id
        
        try:
            # Fetch scores for each game type
            pvp_score = await self.fetch_player_score(guild_id, "pvp", member.id)
            pvb_score = await self.fetch_player_score(guild_id, "pvb", member.id)
            sporty_score = await self.fetch_player_score(guild_id, "sporty", member.id)
            efootball_score = await self.fetch_player_score(guild_id, "efootball", member.id)
            
            # Fetch overall leaderboard to determine rank
            leaderboard = await get_leaderboard(guild_id)
            
            rank = 'None'
            if leaderboard:
                for index, row in enumerate(leaderboard, start=1):
                    if row['player_id'] == member.id:
                        rank = index
                        break
            
            # Create rank display
            pvp_text = f"PvP: {pvp_score}pts"
            pvb_text = f"PvB: {pvb_score}pts"
            sporty_text = f"Sporty: {sporty_score}pts"
            efootball_text = f"Efootball: {efootball_score}pts"
        
            embed = discord.Embed(
                title=f"🏆Rank #{rank}",
                description=(
                    f"Congratulations **{member.name}**!\n"
                    f"You are **Rank #{rank}**.\n\n"
                    f"With:\n"
                    f"{pvp_text}\n"
                    f"{pvb_text}\n"
                    f"{sporty_text}\n"
                    f"{efootball_text}"
                ),
                color=discord.Color.purple()
            )
            embed.set_thumbnail(url=str(member.display_avatar.url))
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            self.error_handler.handle(e, context="rank_command")
            await interaction.followup.send("An error occurred while fetching rank information.")


# ============================================================================ #
#                                     SETUP                                    #
# ============================================================================ #
async def setup(client):
    await client.add_cog(Leaderboard(client))