import discord, requests
from discord import app_commands
from discord.ext import commands
from dbmanager import LevelinManager
from settings import FONT_DIR
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

class LeaderboardPaginationView(discord.ui.View):
    def __init__(self, data, sep=5, timeout=None):
        super().__init__(timeout=timeout)
        self.data = data
        self.sep = sep
        self.current_page = 1
        self.message = None   # don’t forget to store the message
    def circular_crop(self,im):
        size = im.size
        mask = Image.new('L', size, 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0) + size, fill=255)
        output = Image.new("RGBA", size, (0, 0, 0, 0))
        output.paste(im, (0, 0), mask)
        return output

    def truncate_name(self,name, max_length=18):
        if len(name) <= max_length:
            return name
        return name[:max_length - 3] + "..."

    def generate_leaderboard_image(self,data):
        # Config
        row_height = 80
        image_width = 800
        margin = 10
        avatar_size = 50
        font_size = 24
        divider_color = (60, 60, 60)
        background_color = (44, 47, 51)
        text_color = (255, 255, 255)
        rank_colors = {
            1: (255, 215, 0),       # Gold
            2: (192, 192, 192),     # Silver
            3: (205, 127, 50),      # Bronze
        }

        image_height = len(data) * (row_height + margin) + margin
        img = Image.new("RGB", (image_width, image_height), color=background_color) 
        
        draw = ImageDraw.Draw(img)
        
        try:
            font = ImageFont.truetype(FONT_DIR/"OpenSans-Bold.ttf", font_size)
        except:
            font = ImageFont.load_default()
        
        for i, (rank, username, level, xp, avatar_url) in enumerate(data):
            top = margin + i * (row_height + margin)
            left = margin

            # Download avatar
            response = requests.get(avatar_url)
            avatar_img = Image.open(BytesIO(response.content)).convert("RGBA")
            avatar_img = avatar_img.resize((avatar_size, avatar_size))
            avatar_img = self.circular_crop(avatar_img)
            img.paste(avatar_img, (left, top), avatar_img)

            # Truncate name
            username_trunc = self.truncate_name(username)

            # Rank color
            rank_color = rank_colors.get(rank, (255, 255, 255))

            # Draw rank number
            rank_text = f"#{rank}"
            text_x_left = left + avatar_size + margin
            text_y = top + 10
            draw.text((text_x_left, text_y), rank_text, font=font, fill=rank_color)

            # Draw name next to rank
            rank_text_width = draw.textlength(rank_text, font=font)
            name_x = text_x_left + rank_text_width + 8
            draw.text((name_x, text_y), f"• {username_trunc}", font=font, fill=text_color)

            # Right side: Level and XP stacked
            level_text = f"Level {level}"
            xp_text = f"XP {xp:,}" if xp != 0 else ""
 

            level_width = draw.textlength(level_text, font=font)
            xp_width = draw.textlength(xp_text, font=font)
            right_text_width = max(level_width, xp_width)

            right_x = image_width - margin - right_text_width
            level_y = top + 5
            xp_y = level_y + font_size + 2

            draw.text((right_x, level_y), level_text, font=font, fill=text_color)
            draw.text((right_x, xp_y), xp_text, font=font, fill=text_color)

            # Divider
            line_top = top + row_height + 2
            draw.line(
                [(margin, line_top), (image_width - margin, line_top)],
                fill=divider_color,
                width=1
            )

        
        return img
    
    def create_embed(self, total_pages):
        embed = discord.Embed(
            title=f"🏆 Leaderboard Page {self.current_page}/{total_pages}",
            color=discord.Color.gold()
        )
        embed.set_image(url="attachment://leaderboard.png")
        embed.set_footer(text="Use the buttons below to navigate pages.")
        return embed

    def get_current_page_data(self):
        from_item = (self.current_page - 1) * self.sep
        until_item = from_item + self.sep
        data_slice = self.data[from_item:until_item]
        # Already contains rank in position 0
        return data_slice


    def get_total_pages(self):
        return (len(self.data) - 1) // self.sep + 1

    async def update_message(self, interaction):
        total_pages = self.get_total_pages()
        page_data = self.get_current_page_data()

        # Generate the image
        img = self.generate_leaderboard_image(page_data)
        
        # Save image to memory
        from io import BytesIO
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)

        # Prepare discord file
        discord_file = discord.File(buffer, filename="leaderboard.png")

        # Create embed
        embed = discord.Embed(
            title=f"🏆 Leaderboard Page {self.current_page}/{total_pages}",
            color=discord.Color.gold()
        )
        embed.set_image(url="attachment://leaderboard.png")
        embed.set_footer(text="Use the buttons below to navigate pages.")

        await self.message.edit(embed=embed, view=self, attachments=[discord_file])
        await interaction.response.defer()


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
            embed = discord.Embed(
            title="🎉 Level Up!",
            description=(
                f"Congratulations **{message.author.mention}**!\n You reached **Level {level}**.\n\n "
            ),
            color=discord.Color.purple()  # pick your color
            )
            embed.set_thumbnail(url=str(message.author.display_avatar.url))
            
            await message.channel.send(embed=embed)
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
        rank = LevelinManager.get_rank(interaction.guild.id, interaction.user.id)  # Get the user's rank
        
        embed = discord.Embed(
            title="🎉 Current Lvl!",
            description=(
                f"Congratulations **{interaction.user.name}**!\n You are **Rank #{rank} | Level {level}**.\n\n continue chatting to level up more! "
            ),
            color=discord.Color.purple()  # pick your color
        )
        embed.set_thumbnail(url=str(interaction.user.display_avatar.url))
        await interaction.followup.send(embed=embed)
        

    @app_commands.command(
        name="level_server", description="Check the server leaderboard."
    )
    @app_commands.guild_only()
    async def level_server(self, interaction: discord.Interaction):
        await interaction.response.defer()

        # Fetch leaderboard data
        top_users = LevelinManager.fetch_top_users(interaction.guild.id)

        table_data = []
        for idx, (user_id, level, xp) in enumerate(top_users,start=1):
            member = interaction.guild.get_member(user_id)
            if member:
                avatar_url = member.display_avatar.url
                table_data.append(
                    (idx,member.display_name, level, xp, avatar_url)
                )

        # Create pagination view
        pagination_view = LeaderboardPaginationView(
            data=table_data,
            sep=5,
            timeout=None
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


async def setup(client):
    await client.add_cog(Levelling(client))
