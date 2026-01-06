from settings import ErrorHandler, FONT_DIR
import discord,typing,asyncio
from discord import app_commands
from discord.ext import commands, tasks
from dbmanager import MovieManager
from models import Series, Movie
from constants import MediaType


errorHandler = ErrorHandler()


# ============================================================================ #
#                              PAGINATION VIEWS                                #
# ============================================================================ #

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
                media_data = await MovieManager.add_or_update_series(
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


# ============================================================================ #
#                              MOVIES COG                                      #
# ============================================================================ #

class Movies(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.loop_lock = asyncio.Lock()
        self.movie_title_cache = {} #{title: tmdb_id}
        
        
    async def cog_load(self):
        """Called when the cog is loaded - start background tasks."""
        print("[Movies Cog] Starting background updaters...")
        asyncio.create_task(MovieManager.start_background_updaters())
        print("[Movies Cog] Background updaters started!")

    # ============================================================================ #
    #                              ADD MEDIA COMMANDS                              #
    # ============================================================================ #

    @app_commands.command(name="add_movie", description="Add a movie to your watched list or watchlist")
    @app_commands.describe(
        title="The movie title to search for",
        watchlist="Add to watchlist instead of marking as watched (default: False)"
    )
    @app_commands.dm_only()
    async def add_movie(self, interaction: discord.Interaction, title: str,watchlist: bool = False):
        """Add a movie with automatic conflict resolution."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Search for media options
            media_options = await MovieManager.search_media_multiple("movie", title)
    
            
            if not media_options:
                await interaction.followup.send(f" No movies found for: `{title}`",ephemeral=True)
                return
            
            # If only one result with high similarity, auto-add
            if len(media_options) == 1:
                media = media_options[0]
                
                # Save directly
                media_data = await MovieManager.add_or_update_user_movie(interaction.user.id, title,tmdb_id=media['id'],watchlist=watchlist)
                
                if media_data:
                    status_text = "added to watchlist" if watchlist else "marked as watched"
                    embed = discord.Embed(
                        title=f"✅ Movie {status_text.title()}",
                        description=f"**{media['title']}** ({media.get('year', 'N/A')})",
                        color=discord.Color.green()
                    )
                    if media.get('poster_url'):
                        embed.set_thumbnail(url=media['poster_url'])
                    if media.get('overview'):
                        embed.add_field(name="Overview", value=media['overview'][:200], inline=False)
                    
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send("Failed to save movie", ephemeral=True)
                return
            
            # Multiple results - show selection
            embed = create_selection_embed(media_options, "movie", title)
            view = MediaSelectionView(media_options, "movie", interaction.user.id, title, watchlist=watchlist)
            
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            errorHandler.handle(e, context=f"add_movie({title})")
            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)

    @app_commands.command(name="add_series", description="Add a TV series to your watch list")
    @app_commands.describe(
        title="The series title to search for",
        season="Current season number (optional)",
        episode="Current episode number (optional)",
        watchlist="Add to watchlist instead of marking progress (default: False)"
    )
    @app_commands.dm_only()
    async def add_series(
        self, 
        interaction: discord.Interaction, 
        title: str,
        season: int = None,
        episode: int = None,
        watchlist: bool = False
        ):
        """Add a series with conflict resolution."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            media_options = await MovieManager.search_media_multiple("tv", title, limit=10)
            
            if not media_options:
                await interaction.followup.send( f"No series found for: `{title}`", ephemeral=True)
                return
            
            # Auto-add if single high-confidence result
            if len(media_options) == 1 or (
                len(media_options) > 1 and media_options[0]['similarity_score'] > 0.9
                ):
                media = media_options[0]
                
                media_data = await MovieManager.add_or_update_series(
                    interaction.user.id, 
                    title,
                    season=season,
                    episode=episode,
                    tmdb_id=media['id'],
                    watchlist=watchlist
                )
                
                if media_data:
                    status_text = "added to watchlist" if watchlist else "progress updated"
                    embed = discord.Embed(
                        title=f" Series {status_text.title()}",
                        description=f"**{media['title']}** ({media.get('year', 'N/A')})",
                        color=discord.Color.green()
                    )
                    if season and episode:
                        embed.add_field(name="Progress", value=f"S{season}E{episode}", inline=True)
                    if media.get('poster_url'):
                        embed.set_thumbnail(url=media['poster_url'])
                    
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send("Failed to save series", ephemeral=True)
                return
            
            # Multiple results - show selection
            embed = create_selection_embed(media_options, "series", title)
            view = MediaSelectionView(
                media_options, 
                "tv", 
                interaction.user.id, 
                title,
                season=season,
                episode=episode,
                watchlist=watchlist
            )
            
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            errorHandler.handle(e, context=f"add_series({title})")
            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)

    # ============================================================================ #
    #                           WATCHLIST COMMANDS                                 #
    # ============================================================================ #

    @app_commands.command(name="watchlist", description="View your watchlist for movies or series")
    @app_commands.describe(media_type="Type of media (movie or series)")
    @app_commands.dm_only()
    async def view_watchlist(
        self,
        interaction: discord.Interaction,
        media_type: str
         ):
        """View user's watchlist."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            media_type_obj = MediaType.find_media_type(media_type)
            watchlist_items = await MovieManager.get_watchlist(interaction.user.id, media_type_obj.value)
            
            if not watchlist_items:
                await interaction.followup.send(
                    f"Your {media_type} watchlist is empty!",
                    ephemeral=True
                )
                return
            
            embed = discord.Embed(
                title=f"Your {media_type.title()} Watchlist",
                description=f"You have {len(watchlist_items)} item(s) in your watchlist",
                color=discord.Color.blue()
            )
            
            for idx, item in enumerate(watchlist_items[:10]):  # Show first 10
                title = item.get('title', 'Unknown')
                year = item.get('year', 'N/A')
                embed.add_field(
                    name=f"{idx+1}. {title} ({year})",
                    value=item.get('overview', 'No description')[:100] + "...",
                    inline=False
                )
            
            if len(watchlist_items) > 10:
                embed.set_footer(text=f"+ {len(watchlist_items) - 10} more items")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            errorHandler.handle(e, context=f"view_watchlist({media_type})")
            await interaction.followup.send(f"Error: {str(e)}", ephemeral=True)

    @app_commands.command(name="incomplete", description="Check what media you haven't finished watching")
    @app_commands.dm_only()
    async def check_incomplete(self, interaction: discord.Interaction):
        """Check user's incomplete media."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            incomplete_media = await MovieManager.check_user_completion(interaction.user.id)
            
            if not incomplete_media:
                await interaction.followup.send(
                    "You're all caught up! No incomplete media found.",
                    ephemeral=True
                )
                return
            
            embed = discord.Embed(
                title="Your Incomplete Media",
                description=f"You have {len(incomplete_media)} item(s) to catch up on",
                color=discord.Color.orange()
            )
            
            for idx, media in enumerate(incomplete_media[:10]):  # Show first 10
                if isinstance(media, Movie):
                    embed.add_field(
                        name=f"{idx+1}. {media.title}",
                        value=f"Status: Not watched yet\nRelease: {media.release_date}",
                        inline=False
                    )
                elif isinstance(media, Series):
                    watched = media.watched_episodes if hasattr(media, 'watched_episodes') else 0
                    total = media.number_of_episodes if hasattr(media, 'number_of_episodes') else '?'
                    embed.add_field(
                        name=f"{idx+1}. {media.title}",
                        value=f"Progress: {watched}/{total} episodes\nStatus: {media.status}",
                        inline=False
                    )
            
            if len(incomplete_media) > 10:
                embed.set_footer(text=f"+ {len(incomplete_media) - 10} more items")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            errorHandler.handle(e, context="check_incomplete")
            await interaction.followup.send(f"Error: {str(e)}", ephemeral=True)

    # ============================================================================ #
    #                              DELETE COMMAND                                  #
    # ============================================================================ #

    @app_commands.command(name="delete_media", description="Remove a media entry from your list")
    @app_commands.describe(title="The title of the media to delete")
    @app_commands.dm_only()
    async def delete_media(
        self,
        interaction: discord.Interaction,
        title: str
        ):
        """Delete a media entry."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            media_id = self.movie_title_cache.get(title)
            if not media_id:
                await interaction.followup.send(
                    f" Media title not found in your list: `{title}`",
                    ephemeral=True
                )
                #we shoudlnt even get here
                return
            success = await  MovieManager.delete_user_media(interaction.user.id, media_id)
            
            if success:
                await interaction.followup.send(
                    f" Media deleted successfully!",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f" Failed to delete media",
                    ephemeral=True
                )
                
        except Exception as e:
            errorHandler.handle(e, context=f"delete_media({title})")
            await interaction.followup.send(f" Error: {str(e)}", ephemeral=True)

    # ============================================================================ #
    #                              SEARCH COMMANDS                                 #
    # ============================================================================ #

    @app_commands.command(name="search_anime", description="Search for anime on HiAnime")
    @app_commands.describe(query="Anime title to search for")
    @app_commands.dm_only()
    async def search_anime(
        self,
        interaction: discord.Interaction,
        query: str ):
        """Search for anime."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            results = await MovieManager.search_hianime(query)
            
            if not results or results.get("error"):
                await interaction.followup.send(
                    f"No anime found for: `{query}`",
                    ephemeral=True
                )
                return
            
            if len(results) == 0:
                await interaction.followup.send(
                    f"No results found",
                    ephemeral=True
                )
                return
            
            # Use paginator for results
            view = MediaSearchPaginator(results, interaction.user)
            await interaction.followup.send(
                embed=view.get_embed(),
                view=view,
                ephemeral=True
            )
            
        except Exception as e:
            errorHandler.handle(e, context=f"search_anime({query})")
            await interaction.followup.send(f"Error: {str(e)}", ephemeral=True)

        
   
    # ============================================================================ #
    #                                AUTOCOMPLETE                                  #
    # ============================================================================ #

    @view_watchlist.autocomplete("media_type")
    async def media_type_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> typing.List[app_commands.Choice[str]]:
        """Autocomplete for media types."""
        try:
            choices = ["movie", "series"]
            filtered = [
                app_commands.Choice(name=choice, value=choice)
                for choice in choices
                if current.lower() in choice.lower()
            ]
            return filtered
        except Exception:
            return []

    @delete_media.autocomplete("title")
    @add_movie.autocomplete("title")
    @add_series.autocomplete("title")
    async def title_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> typing.List[app_commands.Choice[str]]:
        """Autocomplete for media titles."""
        try:
            self.movie_title_cache = await MovieManager.fetch_media_names()
            filtered = [
                app_commands.Choice(name=title, value=title)
                for title in self.movie_title_cache.keys()
                if current.lower() in title.lower()
            ][:25]  # Discord limit
            return filtered
        except Exception:
            return []

async def setup(client):
    """Setup function to add the cog."""
    await client.add_cog(Movies(client))