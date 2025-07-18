# ============================================================================ #
#                                    IMPORT                                    #
# ============================================================================ #
import discord,sqlite3
from discord import  app_commands
from discord.ext import commands
from dbmanager import Games
from cogs.leveling import LeaderboardPaginationView  
from discord.ext import commands
from settings import ErrorHandler
from io import BytesIO


# ============================================================================ #
#                                LEADERBOARD UI                                #
# ============================================================================ #

errorHandler =ErrorHandler()
# ============================================================================ #
#                              LEADERBOARD COG                                 #
# ============================================================================ #
class Leaderboard(commands.Cog):
    def __init__(self, client):
        self.client = client

    # ============================ Leaderboard COMMAND =========================== #
    @app_commands.command(name="leaderboard", description="Mini Game Rankings")
    @app_commands.describe(
        game_type="Choose the type of game: 'pvp', 'sporty', 'pvb', 'efootball'"
    )
    @app_commands.guild_only()
    async def leaderboard(
        self, interaction: discord.Interaction, game_type: str = None):
        """Show the leaderboard for the current guild with pagination or a specific game type."""
        await interaction.response.defer()
        with Games.create_connection() as conn:
            c = conn.cursor()
            try:
                if game_type:
                    table_name = f"{game_type}_scores_{interaction.guild.id}"
                    c.execute(
                        f"SELECT player_id, player_score FROM {table_name} ORDER BY player_score DESC"
                    )
                else:
                    table_name = f"leaderboard_{interaction.guild.id}"
                    c.execute(
                        f"SELECT player_id, total_score FROM {table_name} ORDER BY total_score DESC"
                    )
                rows = c.fetchall()
            except sqlite3.OperationalError as e:
                await interaction.followup.send("No Leaderboard available.")
                errorHandler.handle_exception(e)
                return
        leaderboard_data = []
        for idx, (player_id, score) in enumerate(rows, start=1):
            member = interaction.guild.get_member(player_id)
            if member:
                avatar_url = member.display_avatar.url
                leaderboard_data.append((idx,member.display_name, score, 0,avatar_url))

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

    @leaderboard.autocomplete("game_type")
    async def game_type_autocomplete(self, interaction: discord.Interaction, current: str):
        # List of possible game types/
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
        except discord.errors.NotFound as e:
            errorHandler.handle_exception(e)
        except Exception as e:
            errorHandler.handle_exception(e)

    # ================================ RANK SCRIPT =============================== #
    async def fetch_player_score(self, cursor, table_name, player_id):
        """Fetch the player score from a specific table."""
        try:
            cursor.execute(
                f"SELECT player_score FROM {table_name} WHERE player_id = :player_id",
                {"player_id": player_id},
            )
            score_row = cursor.fetchone()
            return score_row[0] if score_row else 0
        except Games.sqlite3.OperationalError as e:
            errorHandler.handle_exception(e)
            return 0

    @app_commands.guild_only()
    @app_commands.command(name="rank", description="Rank with score in mini games")
    async def rank(
        self, interaction: discord.Interaction, member: discord.Member = None):
        """Show the rank of a member in the current guild."""

        await interaction.response.defer()
        if member is None:
            member = interaction.user
        guild_id = interaction.guild.id
        pvp_table_name = f"pvp_scores_{guild_id}"
        pvb_table_name = f"pvb_scores_{guild_id}"
        sporty_table_name = f"sporty_scores_{guild_id}"
        efootball_table_name = f"efootball_scores_{guild_id}"
        leaderboard_table_name = f"leaderboard_{interaction.guild.id}"

        with Games.create_connection() as conn:
            c = conn.cursor()
            pvp_score = await self.fetch_player_score(c, pvp_table_name, member.id)
            pvb_score = await self.fetch_player_score(c, pvb_table_name, member.id)
            sporty_score = await self.fetch_player_score(
                c, sporty_table_name, member.id
            )
            efootball_score = await self.fetch_player_score(
                c, efootball_table_name, member.id
            )
            try:
                c.execute(
                    f"SELECT player_id, total_score FROM {leaderboard_table_name} ORDER BY total_score DESC"
                )
                rows = c.fetchall()
                player_position = None
                for index, row in enumerate(rows, start=1):
                    if row[0] == member.id:
                        player_position = index
                        break
                rank = player_position
            except Games.sqlite3.OperationalError as e:
                errorHandler.handle_exception(e)
                rank = 0
            # banner making code
            pvp_text = f"PvP: {pvp_score}pts"
            pvb_text = f"PvB: {pvb_score}pts"
            sporty_text = f"Sporty: {sporty_score}pts"
            efootball_text = f"Efootball: {efootball_score}pts"
        
            embed = discord.Embed(
                title=f"🏆Rank #{rank} ",
                description=(
                    f"Congratulations **{interaction.user.name}**!\n You are **Rank #{rank}**.\n\n With \n {pvp_text}  \n {pvb_text} \n {sporty_text} \n {efootball_text}"
                ),
                color=discord.Color.purple()  # pick your color
                )
            embed.set_thumbnail(url=str(interaction.user.display_avatar.url))
            await interaction.followup.send(embed=embed)
            

# ============================================================================ #
#                                     SETUP                                    #
# ============================================================================ #
async def setup(client):
    await client.add_cog(Leaderboard(client))
