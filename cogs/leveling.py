import discord, os, requests
from discord import app_commands
from discord.ext import commands
from dbmanager import LevelinManager
from settings import ErrorHandler,IMGS_DIR
from tabulate import tabulate
from PIL import Image, ImageDraw, ImageFont


class LeaderboardPaginationView(discord.ui.View):
    def __init__(self, data, sep=5, timeout=None):
        super().__init__(timeout=timeout)
        self.data = data
        self.sep = sep
        self.current_page = 1

    def create_embed(self, data, total_pages):
        embed = discord.Embed(
            title=f"Leaderboard Page {self.current_page} / {total_pages}"
        )
        headers = ["Rank", "Username", "Level", "XP"]
        rows = [
            [idx, player_name, level, xp]
            for idx, (player_name, level, xp) in enumerate(
                data, start=(self.current_page - 1) * self.sep + 1
            )
        ]
        table_output = tabulate(rows, headers=headers, tablefmt="grid")
        if len(table_output) > 1994:
            table_output = table_output[:1990] + "\n..."
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
        await self.message.edit(embed=embed, view=self)

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


class Levelling(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return  # Ignore bot messages
        guild_id = message.guild.id
        user_id = message.author.id
        # Fetch the user's XP and level, or initialize them
        user_data = LevelinManager.get_user_level(guild_id, user_id)
        if user_data:
            xp, level = user_data
        else:
            xp, level = 0, 1
            LevelinManager.insert_or_update_user(guild_id, user_id, xp, level)
        # Add XP and check for level up
        xp += 5  # Customize the XP per message

        def level_up_xp(level, base_xp=100, growth_factor=1.15):
            """
            Calculate the XP needed to level up, with a progressive increase.
            """
            return int(base_xp * (growth_factor ** (level - 1)))

        while xp >= level_up_xp(level):
            xp -= level_up_xp(level)  # Deduct XP required for current level
            level += 1
            await message.channel.send(
                f"Congrats {message.author.mention}, you've leveled up to **{level}**!"
            )
        LevelinManager.insert_or_update_user(guild_id, user_id, xp, level)

    @app_commands.command(name="level_self", description="Check your level")
    @app_commands.guild_only()
    async def level_self(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user_data = LevelinManager.get_user_level(
            interaction.guild.id, interaction.user.id
        )
        if not user_data:
            await interaction.followup.send(
                f"{interaction.user.mention}, you have no recorded level data yet."
            )
            return
        xp, level = user_data
        xp_needed = level * 100  # XP required for the next level
        progress = xp / xp_needed  # Progress towards the next level
        rank = LevelinManager.get_rank(
            interaction.guild.id, interaction.user.id
        )  # Get the user's rank
        avatar_bytes = requests.get(
            str(interaction.user.display_avatar.url), stream=True
        ).raw
        avatar = Image.open(avatar_bytes).convert("RGBA")
        avatar = avatar.resize((220, 220))  # Increase avatar size
        mask = Image.new("L", avatar.size, 0)  # Apply circular mask
        draw = ImageDraw.Draw(mask)
        draw.ellipse([(0, 0), avatar.size], fill=255)
        avatar.putalpha(mask)
        background = Image.new("RGBA", (934, 282), (30, 30, 30, 255))
        draw = ImageDraw.Draw(background)
        font_main = ImageFont.truetype(
            "arial.ttf", 30
        )  # Increase font size for main text
        font_title = ImageFont.truetype("arial.ttf", 40)  # Increase font size for title
        background.paste(
            avatar, (20, 20), avatar
        )  # Draw avatar onto background # Paste with transparenc
        draw.text(
            (270, 150), f"{interaction.user.name}", font=font_title, fill="white"
        )  # Gold color for the name
        draw.text(
            (700, 20), f"Rank #{rank} | Level {level}", font=font_main, fill="blue"
        )  # Rank and Level
        draw.text(
            (700, 150), f"{xp}/{xp_needed}", font=font_main, fill="white"
        )  # Draw text information
        bar_x, bar_y = 270, 200  # Draw progress bar
        bar_width, bar_height = 600, 30
        draw.rounded_rectangle(
            [bar_x, bar_y, bar_x + bar_width, bar_y + bar_height],
            radius=10,
            fill="#000000",
        )  # Background for the bar
        draw.rounded_rectangle(
            [bar_x, bar_y, bar_x + int(bar_width * progress), bar_y + bar_height],
            radius=10,
            fill="#FFFFFF",
        )  # Progress
        output_path = IMGS_DIR / "level_card.png"  # Save and send
        background.save(output_path)
        await interaction.followup.send(file=discord.File(output_path))
        try:
            os.remove(output_path)
        except FileNotFoundError as e:
            errorHandler = ErrorHandler()
            ErrorHandler.handle_exception(e)
            pass

    @app_commands.command(
        name="level_server", description="Check the server leaderboard."
    )
    @app_commands.guild_only()
    async def level_server(self, interaction: discord.Interaction):
        await interaction.response.defer()
        top_users = LevelinManager.fetch_top_users(interaction.guild.id)
        table_data = [
            (interaction.guild.get_member(user_id).display_name, level, xp)
            for user_id, level, xp in top_users
            if interaction.guild.get_member(user_id)
        ]
        pagination_view = LeaderboardPaginationView(
            data=table_data, sep=5, timeout=None
        )
        pagination_view.message = await interaction.followup.send(
            embed=pagination_view.create_embed(
                pagination_view.get_current_page_data(),
                pagination_view.get_total_pages(),
            ),
            view=pagination_view,
        )


async def setup(client):
    await client.add_cog(Levelling(client))
