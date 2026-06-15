# ============================================================================ #
#                              PAGINATION VIEWS                                #
# ============================================================================ #

import discord
from handle import handler
from dbmanager.MovieManager import MovieManager
movieManager = MovieManager()
from models import UserMedia

class MediaSearchPaginator(discord.ui.View):
    """A Discord UI view with buttons for pagination."""

    def __init__(self, results, user: discord.User):
        super().__init__()
        self.results = results
        self.user = user
        self.index = 0
        self.previous_button.disabled = True if self.index == 0 else False
        self.next_button.disabled = len(results) <= 5

    def get_embed(self):
        """Generates an embed for the current 5 results."""
        try:
            embed = discord.Embed(title="Search Results", color=discord.Color.blue())

            for media in self.results[self.index : self.index + 5]:
                thumbnail_url = (
                    media["thumbnail"]
                    if media.get("thumbnail")
                    else "imgs/defualt.png"
                )
                embed.add_field(
                    name=f"{media['title']}",
                    value=f"[Watch Here]({media['link']}) || [Poster]({thumbnail_url})",
                    inline=False,
                )
            embed.set_footer(
                text=f"Page {self.index//5 + 1} of {((len(self.results) - 1) // 5) + 1}"
            )
            return embed
        except Exception as e:
            handler.error_handle(e, context="MediaSearchPaginator.get_embed")
            return discord.Embed(
                title="Error",
                description="An error occurred while generating the embed.",
                color=discord.Color.red(),
            )

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, disabled=True)
    async def previous_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user != self.user:
            return await interaction.response.send_message(
                "This is not your session!", ephemeral=True
            )

        self.index -= 5
        self.next_button.disabled = False

        if self.index == 0:
            self.previous_button.disabled = True

        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
    async def next_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user != self.user:
            return await interaction.response.send_message(
                "This is not your session!", ephemeral=True
            )

        self.index += 5
        self.previous_button.disabled = False

        if self.index + 5 >= len(self.results):
            self.next_button.disabled = True

        await interaction.response.edit_message(embed=self.get_embed(), view=self)


# ============================================================================ #
#                           MEDIA SELECTION VIEW                               #
# ============================================================================ #

class MediaSelectionView(discord.ui.View):
    """View that displays media options when there are conflicts."""
    
    def __init__(self, media_options: list, media_type: str, user_id: int, 
                 original_query: str, season=None, episode=None, watchlist=False):
        super().__init__(timeout=180)
        self.media_type = media_type
        self.user_id = user_id
        self.original_query = original_query
        self.season = season
        self.episode = episode
        self.watchlist = watchlist
        self.selected_media = None
        
        # Create select menu
        options = []
        for media in media_options[:25]:  # Discord limit
            label = media.get('title', 'Unknown')
            year = media.get('year', '')
            if year:
                label = f"{label} ({year})"
            
            if len(label) > 100:
                label = label[:97] + "..."
            
            desc = media.get('overview', 'No description')
            if len(desc) > 100:
                desc = desc[:97] + "..."
            
            options.append(
                discord.SelectOption(
                    label=label,
                    value=str(media['id']),
                    description=desc,
                    emoji="🎬" if media_type == "movie" else "📺" #cant use images here
                )
            )
        
        select = discord.ui.Select(
            placeholder=f"Select the correct {media_type}...",
            options=options,
            custom_id="media_select"
        )
        select.callback = self.select_callback
        self.add_item(select)
    
    async def select_callback(self, interaction: discord.Interaction):
        """Handle when user selects a media option."""
        
        selected_id = interaction.data['values'][0] #type: ignore
        selected_title = None   
        
        # Find selected media
        for item in self.children:
            if isinstance(item, discord.ui.Select):
                for option in item.options:
                    if option.value == selected_id:
                        selected_title = option.label
                        break
        
        self.selected_media = {
            'id': selected_id,
            'title': selected_title
        }
        
        # Disable selection
        for item in self.children:
            item.disabled = True #type: ignore
        
        await interaction.response.edit_message(
            content=f"✅ Selected: **{selected_title}**\n⏳ Saving to database...",
            view=self
        )
        
        # Save to database
        try:
            if self.media_type == "movie":
                media_data = await movieManager.add_or_update_user_movie(
                    self.user_id, 
                    self.original_query,
                    tmdb_id=int(selected_id),
                    watchlist=self.watchlist
                )
            else:  # series/tv
                media_data = await movieManager.add_or_update_user_series(
                    self.user_id, 
                    self.original_query,
                    season=self.season,
                    episode=self.episode,
                    tmdb_id=int(selected_id),
                    watchlist=self.watchlist
                )
            
            if media_data:
                await interaction.edit_original_response(
                    content=f"✅ **{selected_title}** saved successfully!",
                    view=self
                )
            else:
                await interaction.edit_original_response(
                    content=f"❌ Error saving: Could not save media data",
                    view=self
                )
        except Exception as e:
            await interaction.edit_original_response(
                content=f"❌ Error saving: {str(e)}",
                view=self
            )
        
        self.stop()


def create_selection_embed(media_options: list, media_type: str, query: str) -> discord.Embed:
    """Create an embed showing media options."""
    try:
        embed = discord.Embed(
            title=f"🔍 Multiple {media_type.title()}s Found",
            description=f"Found **{len(media_options)}** results for: `{query}`\n\nPlease select the correct one:",
            color=discord.Color.blue()
        )

        # Show poster of top result
        if media_options and media_options[0].get('poster_url'):
            embed.set_thumbnail(url=media_options[0]['poster_url'])

        # Show top 3 as fields
        for idx, media in enumerate(media_options[:3]):
            year_text = f" ({media.get('year', 'N/A')})" if media.get('year') else ""
            overview = media.get('overview', 'No description')
            if len(overview) > 150:
                overview = overview[:147] + "..."

            embed.add_field(
                name=f"{idx+1}. {media['title']}{year_text}",
                value=overview,
                inline=False
            )

        if len(media_options) > 3:
            embed.set_footer(text=f"+ {len(media_options) - 3} more in dropdown")

        return embed
    except Exception as e:
        handler.error_handle(e, context="create_selection_embed")
        return discord.Embed(
            title="Error",
            description="An error occurred while creating the selection embed.",
            color=discord.Color.red(),
        )


class WatchHistoryPaginationView(discord.ui.View):
    def __init__(self, data: list[UserMedia], sep: int = 10, timeout: int = 60):
        super().__init__(timeout=timeout)
        self.data = data  # parse once upfront
        self.sep = sep
        self.current_page = 1
        self.message = None

    # ── helpers ──────────────────────────────────────────────────────────

    def get_total_pages(self) -> int:
        return max(1, (len(self.data) - 1) // self.sep + 1)

    def get_current_page_data(self) -> list[UserMedia]:
        start = (self.current_page - 1) * self.sep
        return self.data[start : start + self.sep]

    # ── embed builder ────────────────────────────────────────────────────

    def build_embed(self) -> discord.Embed:
        page_data = self.get_current_page_data()
        total_pages = self.get_total_pages()

        embed = discord.Embed(
            title=f"Watch History — Page {self.current_page}/{total_pages}",
            color=discord.Color.blurple()
        )

        for item in page_data:
            # status badge
         
            # value line: progress for series, watched state for movies
            if item.is_series:
                value = f"Type: {item.user_status.strip()} \n Progress: {item.progress_text or 'Not started'}"
            else:
                value = f"Type: {item.user_status.strip()} \n Status:  {'Watched' if item.is_completed else 'Not watched'}"

            embed.add_field(
                name=f"{item.media_type.table_name.title()} • {item.title}",
                value=value,
                inline=False
            )

        embed.set_footer(text="Use the buttons below to navigate.")
        return embed

    # ── update helper ────────────────────────────────────────────────────

    async def update_message(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    # ── buttons ──────────────────────────────────────────────────────────

    @discord.ui.button(label="|<", style=discord.ButtonStyle.green)
    async def first_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = 1
        await self.update_message(interaction)

    @discord.ui.button(label="<", style=discord.ButtonStyle.primary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 1:
            self.current_page -= 1
        await self.update_message(interaction)

    @discord.ui.button(label=">", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.get_total_pages():
            self.current_page += 1
        await self.update_message(interaction)

    @discord.ui.button(label=">|", style=discord.ButtonStyle.green)
    async def last_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = self.get_total_pages()
        await self.update_message(interaction)