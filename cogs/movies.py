from settings import ErrorHandler
import discord,typing,asyncio
from discord import app_commands
from discord.ext import commands
from dbmanager.MovieManager import MovieManager
from views.movieView import MediaSelectionView, create_selection_embed
from constants import MediaType

errorHandler = ErrorHandler()

movieManager = MovieManager()



# ============================================================================ #
#                              MOVIES COG                                      #
# ============================================================================ #

class Movies(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.loop_lock = asyncio.Lock()
        self.movie_title_cache = {} #{title: tmdb_id}
        
        

    # ============================================================================ #
    #                              ADD MEDIA COMMANDS                              #
    # ============================================================================ #

    @app_commands.command(name="add_to_watchlist", description="Add a movie or series to your watchlist")
    @app_commands.describe(
        title="The title to search for",
        media_type="Type of media: movie or series"
    )
    @app_commands.dm_only()
    async def add_to_watchlist(self, interaction: discord.Interaction, title: str,media_type: str):
        """Add media to watchlist."""
        await interaction.response.defer(ephemeral=True)
        try:
            if media_type.lower() == "movie":
                await self.add_movie_template(interaction, title, watchlist=True)
            elif media_type.lower() == "series":
                await self.add_series_template(interaction, title, watchlist=True)
        except Exception as e:
            errorHandler.handle(e, context=f"add_to_watchlist({title}, {media_type})")
            await interaction.followup.send(f" Error: Adding to watchlist failed.", ephemeral=True)
      

    @app_commands.command(name="add_movie", description="Add a movie to your watched list or watchlist")
    @app_commands.describe(
        title="The movie title to search for",
        
    )
    @app_commands.dm_only()
    async def add_movie(self, interaction: discord.Interaction, title: str):
        """Add a movie with automatic conflict resolution."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            await self.add_movie_template(interaction, title, watchlist=False)
        except Exception as e:
            errorHandler.handle(e, context=f"add_movie({title})")
            await interaction.followup.send(f"Error: Saving movie failed.", ephemeral=True)


    @app_commands.command(name="add_series", description="Add a TV series to your watch list")
    @app_commands.describe(
        title="The series title to search for",
        season="Current season number",
        episode="Current episode number",
    )
    @app_commands.dm_only()
    async def add_series(self, interaction: discord.Interaction, title: str,season: int,episode: int):
        """Add a series with conflict resolution."""
        await interaction.response.defer(ephemeral=True)
        
        try: 
            await self.add_series_template(interaction, title, season, episode, watchlist=False)       
        except Exception as e:
            errorHandler.handle(e, context=f"add_series({title})")
            await interaction.followup.send(f" Error: Adding series failed.", ephemeral=True)

    #cover up functions
    async def add_series_template(
        self, 
        interaction: discord.Interaction, 
        title: str,
        season: int=None,
        episode: int=None,
        watchlist: bool = False
        ):
        """Add a series with conflict resolution."""    
        try:
            if self.movie_title_cache.get(title):
                media_options = [{
                    'id': self.movie_title_cache[title]["id"],
                    'title': title,
                    'tmdb_id': self.movie_title_cache[title]["tmdb_id"]
                
                }]
            else:
                media_options = await movieManager.search_media_multiple("tv", title)
            
            if not media_options:
                await interaction.followup.send( f"No series found for: `{title}`", ephemeral=True)
                return
            
            # Auto-add if single high-confidence result
            if len(media_options) > 1 :
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
                await interaction.followup.send(embed=embed, view=view)
                return
            else:
                media = media_options[0]
                if "tmdb_id" in media: #since there are times the api will return only one page and an accrute one so tmdb_id will be there but as id
                    tmbd_id = media['tmdb_id']
                else:
                    tmbd_id = media['id']

                media_data = await movieManager.add_or_update_user_series( interaction.user.id,  title, season=season, episode=episode, tmdb_id=tmbd_id, watchlist=watchlist
                    )
              
                
                if media_data:
                    status_text = "added to watchlist" if watchlist else "progress updated"
                    embed = discord.Embed(
                        title=f" Series {status_text.title()}",
                        description=f"**{media_data.title}** Status: ({media_data.status})",
                        color=discord.Color.blue()
                    )
                    if season and episode:
                        embed.add_field(name="Progress", value=f"S{season}E{episode}", inline=True)
                   
                    embed.set_thumbnail(url=media_data.poster_url)
                  
                    embed.add_field(name="Overview", value=media_data.overview[:200], inline=False)
                    embed.add_field(name="Latest Release Info", value=str(media_data.latest_release_info), inline=True)
                    embed.add_field(name="Next Episode", value=str(media_data.next_release_info), inline=True)
                    
                    await interaction.followup.send(embed=embed)
                else:
                    await interaction.followup.send("Failed to save series", ephemeral=True)
                return
            
            
        except Exception as e:
            errorHandler.handle(e, context=f"add_series({title})")
            await interaction.followup.send(f" Error: Adding series failed.", ephemeral=True)


    async def add_movie_template(self, interaction: discord.Interaction, title: str,watchlist: bool = False):
        """Add a movie with automatic conflict resolution."""
    
        
        try:
            # Search for media options 
            if self.movie_title_cache.get(title):
                media_options = [{
                    'id': self.movie_title_cache[title]["id"],
                    'title': title,
                    'tmdb_id': self.movie_title_cache[title]["tmdb_id"]
                }]
            else:
                media_options = await movieManager.search_media_multiple("movie", title)
    
            
            if not media_options:
                await interaction.followup.send(f" No movies found for: `{title}`",ephemeral=True)
                return
            if len(media_options) > 1:
                embed = create_selection_embed(media_options, "movie", title)
                view = MediaSelectionView(media_options, "movie", interaction.user.id, title, watchlist=watchlist)
                await interaction.followup.send(embed=embed, view=view)
                return
            else:
                media = media_options[0]
                if "tmdb_id" in media: #since there are times the api will return only one page and an accrute one so tmdb_id will be there but as id
                    tmdb_id = media['tmdb_id']
                else:
                    tmdb_id = media['id']

                media_data = await movieManager.add_or_update_user_movie(interaction.user.id, title, tmdb_id=tmdb_id, watchlist=watchlist)

                if media_data:
                    status_text = "added to watchlist" if watchlist else "marked as watched"
                    embed = discord.Embed(
                        title=f"Movie {status_text.title()}",
                        description=f"**{media_data.title}** (Status: {media_data.status})",
                        color=discord.Color.green()
                    )
                    embed.set_thumbnail(url=media_data.poster_url)
                    embed.add_field(name="Release Date", value=str(media_data.release_date), inline=True)
                    embed.add_field(name="Overview", value=media_data.overview[:200], inline=False)
                    
                    await interaction.followup.send(embed=embed)
                else:
                    await interaction.followup.send("Failed to save movie", ephemeral=True)
                return
        except Exception as e:
            errorHandler.handle(e, context=f"add_movie({title})")
            await interaction.followup.send(f"Error: Saving movie failed.", ephemeral=True)

    # ============================================================================ #
    #                           WATCHLIST COMMANDS                                 #
    # ============================================================================ #

    @app_commands.command(name="watchlist", description="View your watchlist for movies or series. Shows up to 10 items.")
    @app_commands.describe(media_type="Type of media: movie or series")
    @app_commands.dm_only()
    async def view_watchlist(
        self,
        interaction: discord.Interaction,media_type: str = None
         ):
        """View user's watchlist."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            watchlist_items = await movieManager.get_watchlist(interaction.user.id)
            
            if not watchlist_items:
                await interaction.followup.send(
                    f"Your watchlist is empty!"
                )
                return
            
            
            embed = discord.Embed(
            title=f"Your Watchlist",
            description=f"You have {len(watchlist_items)} item(s) in your watchlist",
            color=discord.Color.blue()
            )
            if media_type:
                watchlist_items = [item for item in watchlist_items if item.get("media_type") == media_type]
                embed.title = f"Your {media_type.title()} Watchlist"
                embed.description = f"You have {len(watchlist_items)} {media_type.value}(s) in your watchlist"
                if not watchlist_items:
                    await interaction.followup.send(
                        f"Your {media_type} watchlist is empty!"
                    )
                    return
            
            for idx, item in enumerate(watchlist_items[:10]):
                title = item.get("title") or "Unknown title"

                release_date = item.get("release_date")
                release_date = release_date if release_date else "Unknown date"
                embed.add_field(
                    name=f"{idx + 1}. {title}({item.get('media_type','N/A')})",
                    value=release_date,
                    inline=False
                )

                if len(watchlist_items) > 10:
                    embed.set_footer(text=f"+ {len(watchlist_items) - 10} more items")
                
                await interaction.followup.send(embed=embed)
            
        except Exception as e:
            errorHandler.handle(e, context=f"view_watchlist()")
            await interaction.followup.send(f"Error: Failed to retrieve watchlist.", ephemeral=True)

    @app_commands.command(name="incomplete", description="Check what media you haven't finished watching")
    @app_commands.describe(media_type="Type of media: movie or series")
    @app_commands.dm_only()
    async def check_incomplete(self, interaction: discord.Interaction, media_type: str = None):
        """Check user's incomplete media."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            incomplete_media = await movieManager.check_user_completion(interaction.user.id)
           
          
            if not incomplete_media:
                await interaction.followup.send(
                    "You're all caught up! No incomplete media found.",
                    ephemeral=True
                )
                return
            if media_type:
                media_type = MediaType.find_media_type(media_type)
                incomplete_media = [
                    media for media in incomplete_media
                    if media.media_type == media_type
                ]
            embed = discord.Embed(
                title="Your Incomplete Media",
                description=f"You have {len(incomplete_media)} item(s) to catch up on",
                color=discord.Color.orange()
            )

            for idx, media in enumerate(incomplete_media[:10], start=1):
                parts = []

                # Progress / status line
                if media.is_series:
                    if media.progress_text:
                        parts.append(f"**Progress:** {media.progress_text}")
                    else:
                        parts.append("**Progress:** Not started")

                    if media.next_episode_text:
                        parts.append(f"**Next:** {media.next_episode_text}")
                else:
                    parts.append("✓ Watched" if media.is_completed else "Not watched yet")

                # Media status (Airing / Ended)
                if media.media_status:
                    parts.append(f"**Status:** {media.media_status}")

                # Overview (trimmed)
                if media.overview:
                    trimmed = media.overview[:120] + "..." if len(media.overview) > 120 else media.overview
                    parts.append(trimmed)

                embed.add_field(
                    name=f"{idx}. {media.media_type.table_name.title()} • {media.title}",
                    value="\n".join(parts),
                    inline=False
                )

            # Footer if truncated
            if len(incomplete_media) > 10:
                embed.set_footer(text=f"+ {len(incomplete_media) - 10} more items")

            await interaction.followup.send(embed=embed)

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
            success = await movieManager.delete_user_media(interaction.user.id, media_id["id"])
            
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

 
        
    @app_commands.command(name="search_media", description="Search for movies or series")
    @app_commands.dm_only()
    async def search_media(
        self,
        interaction: discord.Interaction,
        title: str
        ):
        """Search for movies or series."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            results = await movieManager.fetch_user_media(interaction.user.id, self.movie_title_cache.get(title)["id"])
            
            if not results:
                await interaction.followup.send( f"No results found for: `{title}`", ephemeral=True )
                return
            

            embed_data = results.to_embed_dict()
            send_embed = discord.Embed(
                title=embed_data["title"],
                description=embed_data["description"],
                color=discord.Color(embed_data["color"])
            )
            # Add all the fields
            for field in embed_data.get("fields", []):
                send_embed.add_field(
                    name=field["name"],
                    value=field["value"],
                    inline=field.get("inline", False)
                )
            # Add thumbnail if present
            if embed_data.get("thumbnail"):
                send_embed.set_thumbnail(url=embed_data["thumbnail"])
            await interaction.followup.send(embed=send_embed)
            
        except Exception as e:
            errorHandler.handle(e, context=f"search_media({title})")
            await interaction.followup.send(f"Error: Finding media", ephemeral=True)
    # ============================================================================ #
    #                                AUTOCOMPLETE                                  #
    # ============================================================================ #

    @add_to_watchlist.autocomplete("media_type")
    @view_watchlist.autocomplete("media_type")
    @check_incomplete.autocomplete("media_type")
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
            return [app_commands.Choice(name="movie", value="movie"), app_commands.Choice(name="series", value="series")]
        
    @add_movie.autocomplete("title")
    @add_series.autocomplete("title")
    @search_media.autocomplete("title")
    @add_to_watchlist.autocomplete("title")
    @delete_media.autocomplete("title")
    async def title_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> typing.List[app_commands.Choice[str]]:
        """Autocomplete for media titles."""
        try:
            self.movie_title_cache = await movieManager.fetch_media_names()
    
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