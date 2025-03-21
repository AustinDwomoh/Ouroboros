# ============================================================================ #
#                                    IMPORT                                    #
# ============================================================================ #
import discord, os
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from discord import File, app_commands
from discord.ext import commands
from dbmanager import Games
from tabulate import tabulate
from discord.ext import commands
from settings import ErrorHandler,IMGS_DIR



# ============================================================================ #
#                                LEADERBOARD UI                                #
# ============================================================================ #
class LeaderboardPaginationView(discord.ui.View):
    def __init__(self, data, sep=10, timeout=None):
        super().__init__(timeout=timeout)
        self.data = data
        self.sep = sep
        self.current_page = 1

    def create_embed(self, data, total_pages):
        embed = discord.Embed(
            title=f"Leaderboard Page {self.current_page} / {total_pages}"
        )
        table_data = [
            [idx, player_name, score]
            for idx, (player_name, score) in enumerate(
                data, start=(self.current_page - 1) * self.sep + 1
            )
        ]
        headers = ["Rank", "Player Name", "Pts"]
        table_output = tabulate(table_data, headers=headers, tablefmt="grid")
        embed.description = f"```\n{table_output}\n```"
        return embed

    def get_current_page_data(self):
        from_item = (self.current_page - 1) * self.sep
        until_item = from_item + self.sep
        return self.data[from_item:until_item]

    def get_total_pages(self):
        return (len(self.data) - 1) // self.sep + 1

    async def update_message(self, interaction):
        total_pages = self.get_total_pages()
        page_data = self.get_current_page_data()
        embed = self.create_embed(page_data, total_pages)
        if self.message:
            await self.message.edit(embed=embed, view=self)

    # ================================== BUTTONS ================================= #
    @discord.ui.button(label="|<", style=discord.ButtonStyle.green)
    async def first_page_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.current_page = 1
        await self.update_message(interaction)

    @discord.ui.button(label="<", style=discord.ButtonStyle.primary)
    async def prev_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if self.current_page > 1:
            self.current_page -= 1
        await self.update_message(interaction)

    @discord.ui.button(label=">", style=discord.ButtonStyle.primary)
    async def next_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if self.current_page < self.get_total_pages():
            self.current_page += 1
        await self.update_message(interaction)

    @discord.ui.button(label=">|", style=discord.ButtonStyle.green)
    async def last_page_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.current_page = self.get_total_pages()
        await self.update_message(interaction)

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
        self, interaction: discord.Interaction, game_type: str = None
    ):
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
            except Exception as e:
                await interaction.followup.send("No Leaderboard available.")
                errorHandler.handle_exception(e)
                return
        leaderboard_data = []
        for idx, (player_id, score) in enumerate(rows, start=1):
            member = interaction.guild.get_member(player_id)
            if member:
                leaderboard_data.append((member.display_name, score))
        pagination_view = LeaderboardPaginationView(
            data=leaderboard_data, sep=5, timeout=None
        )
        pagination_view.message = await interaction.followup.send(
            embed=pagination_view.create_embed(
                pagination_view.get_current_page_data(),
                pagination_view.get_total_pages(),
            ),
            view=pagination_view,
        )

    @leaderboard.autocomplete("game_type")
    async def game_type_autocomplete(
        self, interaction: discord.Interaction, current: str
    ):
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
        self, interaction: discord.Interaction, member: discord.Member = None
    ):
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
            banner_path = IMGS_DIR / "default.png"
            banner = Image.open(banner_path).convert("RGBA")
            blurred_banner = banner.filter(ImageFilter.GaussianBlur(10))
            overlay = Image.new("RGBA", blurred_banner.size, (0, 0, 0, 0))
            combined_image = Image.alpha_composite(blurred_banner, overlay)
            draw = ImageDraw.Draw(combined_image)
            try:
                font = ImageFont.truetype("arial.ttf", 40)
                bold_font = ImageFont.truetype("arialbd.ttf", 60)
            except IOError as e:
                errorHandler.handle_exception(e)
                return
            player_name = member.display_name
            pvp_text = f"PvP: {pvp_score}pts"
            pvb_text = f"PvB: {pvb_score}pts"
            sporty_text = f"Sporty: {sporty_score}pts"
            efootball_text = f"Efootball: {efootball_score}pts"
            rank_text = f"Rank: #{rank}"
            name_position = (200, 30)
            pvp_score_position = (50, 100)
            pvb_score_position = (50, 150)
            sporty_score_position = (50, 200)
            efootball_score_position = (300, 100)
            image_width, image_height = combined_image.size
            rank_position = (image_width - 350, image_height - 70)
            draw.text(name_position, player_name, font=bold_font, fill=(255, 255, 255, 255))
            draw.text(pvp_score_position, pvp_text, font=font, fill=(255, 255, 255, 255))
            draw.text(pvb_score_position, pvb_text, font=font, fill=(255, 255, 255, 255))
            draw.text(sporty_score_position, sporty_text, font=font, fill=(255, 255, 255, 255))
            draw.text(efootball_score_position,efootball_text,font=font,fill=(255, 255, 255, 255),)
            draw.text(rank_position, rank_text, font=bold_font, fill=(255, 255, 255, 255))
            image_path = f"{member.display_name}_rank.png"
            combined_image.save(image_path, format="PNG", quality=100)
            await interaction.followup.send(file=File(image_path))
            os.remove(image_path)


# ============================================================================ #
#                                     SETUP                                    #
# ============================================================================ #
async def setup(client):
    await client.add_cog(Leaderboard(client))
