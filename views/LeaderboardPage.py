from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import discord
import aiohttp
from settings import FONT_DIR
from functools import lru_cache

class LeaderboardPaginationView(discord.ui.View):
    def __init__(self, data, sep=5, timeout=180, text=None):
        super().__init__(timeout=timeout)
        self.data = data
        self.sep = sep
        self.current_page = 1
        self.message = None
        self.text = text
        self._avatar_cache = {}  # Cache downloaded avatars
        
    async def on_timeout(self):
        """Disable buttons when view times out"""
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass

    @staticmethod
    @lru_cache(maxsize=1)
    def _get_font(size=24):
        """Cache font loading"""
        try:
            return ImageFont.truetype(str(FONT_DIR / "OpenSans-Bold.ttf"), size)
        except:
            return ImageFont.load_default()

    @staticmethod
    def circular_crop(im):
        """Create circular avatar with antialiasing"""
        size = im.size
        mask = Image.new('L', size, 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0) + size, fill=255)
        output = Image.new("RGBA", size, (0, 0, 0, 0))
        output.paste(im, (0, 0), mask)
        return output

    @staticmethod
    def truncate_name(name, max_length=18):
        """Truncate long names with ellipsis"""
        return name if len(name) <= max_length else name[:max_length - 3] + "..."

    async def _download_avatar(self, avatar_url):
        """Async avatar download with caching"""
        if avatar_url in self._avatar_cache:
            return self._avatar_cache[avatar_url]
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(avatar_url) as resp:
                    if resp.status == 200:
                        avatar_bytes = await resp.read()
                        self._avatar_cache[avatar_url] = avatar_bytes
                        return avatar_bytes
        except:
            pass
        
        # Return default avatar if download fails
        return None

    def generate_leaderboard_image(self, data):
        """Generate leaderboard image from data"""
        # Config
        ROW_HEIGHT = 80
        IMAGE_WIDTH = 800
        MARGIN = 10
        AVATAR_SIZE = 50
        FONT_SIZE = 24
        
        # Colors
        BACKGROUND = (44, 47, 51)
        TEXT_COLOR = (255, 255, 255)
        DIVIDER = (60, 60, 60)
        RANK_COLORS = {
            1: (255, 215, 0),    # Gold
            2: (192, 192, 192),  # Silver
            3: (205, 127, 50),   # Bronze
        }

        image_height = len(data) * (ROW_HEIGHT + MARGIN) + MARGIN
        img = Image.new("RGB", (IMAGE_WIDTH, image_height), color=BACKGROUND)
        draw = ImageDraw.Draw(img)
        font = self._get_font(FONT_SIZE)

        for i, (rank, username, level, xp, avatar_bytes) in enumerate(data):
            top = MARGIN + i * (ROW_HEIGHT + MARGIN)
            left = MARGIN

            # Draw avatar
            if avatar_bytes:
                try:
                    avatar_img = Image.open(BytesIO(avatar_bytes)).convert("RGBA")
                    avatar_img = avatar_img.resize((AVATAR_SIZE, AVATAR_SIZE), Image.Resampling.LANCZOS)
                    avatar_img = self.circular_crop(avatar_img)
                    img.paste(avatar_img, (left, top), avatar_img)
                except:
                    pass  # Skip if avatar processing fails

            # Truncate username
            username_trunc = self.truncate_name(username)

            # Rank color (gold/silver/bronze for top 3)
            rank_color = RANK_COLORS.get(rank, TEXT_COLOR)

            # Draw rank
            rank_text = f"#{rank}"
            text_x = left + AVATAR_SIZE + MARGIN
            text_y = top + 10
            draw.text((text_x, text_y), rank_text, font=font, fill=rank_color)

            # Draw username
            rank_width = draw.textlength(rank_text, font=font)
            name_x = text_x + rank_width + 8
            draw.text((name_x, text_y), f"• {username_trunc}", font=font, fill=TEXT_COLOR)

            # Right side: Level and XP
            level_label = self.text or "Level"
            level_text = f"{level_label} {level}"
            xp_text = f"XP {xp:,}" if xp != 0 else ""

            level_width = draw.textlength(level_text, font=font)
            xp_width = draw.textlength(xp_text, font=font)
            right_width = max(level_width, xp_width)

            right_x = IMAGE_WIDTH - MARGIN - right_width
            level_y = top + 5
            xp_y = level_y + FONT_SIZE + 2

            draw.text((right_x, level_y), level_text, font=font, fill=TEXT_COLOR)
            if xp_text:
                draw.text((right_x, xp_y), xp_text, font=font, fill=TEXT_COLOR)

            # Divider line
            if i < len(data) - 1:  # Don't draw after last item
                line_y = top + ROW_HEIGHT + 2
                draw.line(
                    [(MARGIN, line_y), (IMAGE_WIDTH - MARGIN, line_y)],
                    fill=DIVIDER,
                    width=1
                )

        return img

    def get_current_page_data(self):
        """Get data slice for current page"""
        start = (self.current_page - 1) * self.sep
        end = start + self.sep
        return self.data[start:end]

    def get_total_pages(self):
        """Calculate total number of pages"""
        return max(1, (len(self.data) - 1) // self.sep + 1)

    def _update_buttons(self):
        """Enable/disable buttons based on current page"""
        total_pages = self.get_total_pages()
        
        # Disable first/prev on page 1
        self.children[0].disabled = self.current_page == 1
        self.children[1].disabled = self.current_page == 1
        
        # Disable next/last on final page
        self.children[2].disabled = self.current_page >= total_pages
        self.children[3].disabled = self.current_page >= total_pages

    async def update_message(self, interaction: discord.Interaction):
        """Update the message with new page"""
        await interaction.response.defer()
        
        total_pages = self.get_total_pages()
        page_data = self.get_current_page_data()

        # Generate image
        img = self.generate_leaderboard_image(page_data)
        
        # Convert to bytes
        buffer = BytesIO()
        img.save(buffer, format="PNG", optimize=True)
        buffer.seek(0)

        # Create Discord file
        file = discord.File(buffer, filename="leaderboard.png")

        # Create embed
        embed = discord.Embed(
            title=f"🏆 Leaderboard (Page {self.current_page}/{total_pages})",
            color=discord.Color.gold()
        )
        embed.set_image(url="attachment://leaderboard.png")
        embed.set_footer(text=f"Showing {len(page_data)} of {len(self.data)} entries")

        # Update button states
        self._update_buttons()

        await self.message.edit(embed=embed, attachments=[file], view=self)

    @discord.ui.button(label="⏮️", style=discord.ButtonStyle.secondary)
    async def first_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Jump to first page"""
        self.current_page = 1
        await self.update_message(interaction)

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.primary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to previous page"""
        self.current_page = max(1, self.current_page - 1)
        await self.update_message(interaction)

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to next page"""
        self.current_page = min(self.get_total_pages(), self.current_page + 1)
        await self.update_message(interaction)

    @discord.ui.button(label="⏭️", style=discord.ButtonStyle.secondary)
    async def last_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Jump to last page"""
        self.current_page = self.get_total_pages()
        await self.update_message(interaction)