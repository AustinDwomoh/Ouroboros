# ============================================================================ #
#                              PAGINATION VIEWS                                #
# ============================================================================ #

import discord
from settings import ErrorHandler
from dbmanager import MovieManager
errorHandler = ErrorHandler()

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
            errorHandler.handle(e, context="MediaSearchPaginator.get_embed")
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
        
        selected_id = interaction.data['values'][0]
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
            item.disabled = True
        
        await interaction.response.edit_message(
            content=f"✅ Selected: **{selected_title}**\n⏳ Saving to database...",
            view=self
        )
        
        # Save to database
        try:
            if self.media_type == "movie":
                media_data = await MovieManager.add_or_update_user_movie(
                    self.user_id, 
                    self.original_query,
                    tmdb_id=int(selected_id),
                    watchlist=self.watchlist
                )
            else:  # series/tv
                media_data = await MovieManager.add_or_update_user_series(
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
        errorHandler.handle(e, context="create_selection_embed")
        return discord.Embed(
            title="Error",
            description="An error occurred while creating the selection embed.",
            color=discord.Color.red(),
        )
