# ============================================================================ #
#                                     NOTES                                    #
# ============================================================================ #
# This cog handles the leaderboard and rank commands for mini games.
# It fetches data from the database and displays it in an embed with pagination.
#Its been tested and both the leaderboard and rank commands are working as intended.

# ============================================================================ #
#                                    IMPORT                                    #
# ============================================================================ #
import discord
from discord import app_commands
from discord.ext import commands
from views.LeaderboardPage import LeaderboardPaginationView  
from settings import ErrorHandler
from io import BytesIO
from dbmanager import Games
from constants import gameType


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
            rows = None
            if game_type:
                game_type = gameType.find_game_type(game_type)  # since its a string we convert it
                # Fetch specific game type scores
                rows = await Games.get_leaderboard(interaction.guild.id, game_type)
            else:
                # Fetch overall leaderboard
                rows = await Games.get_leaderboard(interaction.guild.id)
            # Process rows into a list of (user_id, total_score)
            rows = [(row['user_id'], row['total_score']) for row in rows]
            if not rows:
                    await interaction.followup.send(f"No leaderboard available for {game_type.value}.")
                    return
            # Build leaderboard data with member info
            leaderboard_data = []
            for idx, (player_id, score) in enumerate(rows, start=1):
                member = interaction.guild.get_member(player_id)
                if member:
                    avatar = await member.display_avatar.read()
                    leaderboard_data.append((idx, member.display_name, score, 0, avatar))  # rank, username, score, placeholder, avatar bytes
            
            if not leaderboard_data:
                await interaction.followup.send("No active players found on the leaderboard.")
                return

            # Create pagination view
            pagination_view = LeaderboardPaginationView(
                data=leaderboard_data, sep=5, timeout=None,text="Score" 
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
            game_types = gameType.get_game_types()
            filtered_choices = [
                app_commands.Choice(name=game.value, value=game.value)
                for game in game_types
                if current.lower() in game.value.lower()
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
            
            scores = await Games.get_player_scores(guild_id, None, member.id)
            # Fetch overall leaderboard to determine rank
            rank = await Games.get_rank(guild_id, member.id)   
            if rank is None:
                await interaction.followup.send(f"{member.name} has no rank in this server.")
                return
      
            player_scores = {g.value: 0 for g in gameType}
            for row in scores:  # scores is list of {game_type, player_score}
                player_scores[row["game_type"]] = row["score"]

            pvp_text = f"PvP: {player_scores.get(gameType.PVP.value, 0)}pts"
            pvb_text = f"PvB: {player_scores.get(gameType.PVB.value, 0)}pts"
            sporty_text = f"Sporty: {player_scores.get(gameType.SPORTY.value, 0)}pts"
            efootball_text = f"Efootball: {player_scores.get(gameType.EFOOTBALL.value, 0)}pts"
           
            
            
            # Create rank display
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