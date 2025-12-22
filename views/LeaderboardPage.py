from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import discord,requests
from settings import FONT_DIR
class LeaderboardPaginationView(discord.ui.View):
    def __init__(self, data, sep=5, timeout=None,text=None):
        super().__init__(timeout=timeout)
        self.data = data
        self.sep = sep
        self.current_page = 1
        self.message = None   # don’t forget to store the message
        self.text = text
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
        #level/score and xp/points
        for i, (rank, username, level, xp, avatar) in enumerate(data):
            top = margin + i * (row_height + margin)
            left = margin

            # Download avatar
           
            avatar_img = Image.open(BytesIO(avatar)).convert("RGBA")
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
            level_text = f"Level" if not self.text else self.text + f" {level}" 
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
