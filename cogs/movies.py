from settings import ErrorHandler  # for Dir
import discord, typing
from discord import app_commands
from discord.ext import commands, tasks
from dbmanager import MoviesManager
from tabulate import tabulate
from datetime import date,datetime


errorHandler = ErrorHandler()

class MediaListPaginationView(discord.ui.View):
    def __init__(self, data, media_type, sep=10, timeout=60, watchlist=False):
        super().__init__(timeout=timeout)
        self.data = data
        self.sep = sep
        self.media_type = media_type  # "movie" or "series"
        self.current_page = 1
        self.watch_list = watchlist

    def create_embed(self, data, total_pages):
        embed = discord.Embed(
            title=f"{self.media_type.capitalize()} Page {self.current_page} / {total_pages}"
        )
        table_data = []  # List to hold table rows
        headers = []  # Headers for the table

        # Define headers based on media type
        if self.watch_list:
            headers = ["No.", "Title", "Details", "Date"]
            for idx, item in enumerate(
                data, start=(self.current_page - 1) * self.sep + 1
            ):
                try:
                    if isinstance(item, dict):
                        table_data.append(
                            [str(idx), item["title"], item["extra"], item["date"]]
                        )
                    elif isinstance(item, tuple):
                        table_data.append([str(idx), item[1], item[2], item[3]])
                except IndexError as e:
                    continue

            # Generate the table with Tabulate
            rendered_table = tabulate(table_data, headers=headers, tablefmt="grid")

            # Handle empty data
            if not data:
                embed.description = "No results available for this page."
            else:
                embed.description = f"```\n{rendered_table}\n```"  # Use triple backticks to display the table in code block format

        else:
            if self.media_type == "movie":
                headers = ["No.", "Title", "Date"]
            elif self.media_type == "series":
                headers = ["No.", "Title", "Details", "Date"]
            for idx, item in enumerate(
                data, start=(self.current_page - 1) * self.sep + 1
            ):
                try:
                    if self.media_type == "movie":
                        if isinstance(item, dict):
                            table_data.append([str(idx), item["title"], item["date"]])
                        elif isinstance(item, tuple):
                            table_data.append([str(idx), item[1], item[2]])
                    elif self.media_type == "series":
                        if isinstance(item, dict):
                            table_data.append(
                                [
                                    str(idx),
                                    item["title"],
                                    f"S{item['season']} E{item['episode']}",
                                    item["date"],
                                ]
                            )
                        elif isinstance(item, tuple):
                            table_data.append(
                                [str(idx), item[1], f"S{item[2]} E{item[3]}", item[4]]
                            )
                except IndexError as e:
                    continue

            # Generate the table with Tabulate
            rendered_table = tabulate(table_data, headers=headers, tablefmt="grid")

            # Handle empty data
            if not data:
                embed.description = "No results available for this page."
            else:
                embed.description = f"```\n{rendered_table}\n```"  # Use triple backticks to display the table in code block format

        return embed

    def get_current_page_data(self):
        from_item = (self.current_page - 1) * self.sep
        until_item = from_item + self.sep
        return self.data[from_item:until_item]

    def get_total_pages(self):
        return (len(self.data) - 1) // self.sep + 1

    async def update_message(self, interaction: discord.Interaction):
        total_pages = self.get_total_pages()
        page_data = self.get_current_page_data()
        embed = self.create_embed(page_data, total_pages)

        await interaction.response.edit_message(embed=embed, view=self)

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


class MediaSearchPaginator(discord.ui.View):
    """A Discord UI view with buttons for pagination."""

    def __init__(self, results, user: discord.User):
        super().__init__()
        self.results = results
        self.user = user
        self.index = 0

        # Disable 'Previous' button at start
        self.previous_button.disabled = True if self.index == 0 else False

        # Disable 'Next' button if fewer than 5 results
        self.next_button.disabled = len(results) <= 5

    def get_embed(self):
        """Generates an embed for the current 5 results."""
        embed = discord.Embed(title="Search Results", color=discord.Color.blue())

        for media in self.results[
            self.index : self.index + 5
        ]:  # Show 5 results per page
            thumbnail_url = (
                media["thumbnail"]
                if media.get("thumbnail")
                else "https://example.com/default-thumbnail.jpg"
            )
            embed.add_field(
                name=f"🎥 {media['title']}",
                value=f"[Watch Here]({media['link']}) || " f"[Poster]({thumbnail_url})",
                inline=False,
            )
        embed.set_footer(
            text=f"Page {self.index//5 + 1} of {(len(self.results) // 5) + 1}"
        )
        return embed

    @discord.ui.button(
        label="⬅ Previous", style=discord.ButtonStyle.secondary, disabled=True
    )
    async def previous_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Handles 'Previous' button click."""
        if interaction.user != self.user:
            return await interaction.response.send_message(
                "This is not your session!", ephemeral=True
            )

        self.index -= 5
        self.next_button.disabled = False  # Enable 'Next' button

        if self.index == 0:
            self.previous_button.disabled = True  # Disable if at start

        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="Next ➡", style=discord.ButtonStyle.primary)
    async def next_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Handles 'Next' button click."""
        if interaction.user != self.user:
            return await interaction.response.send_message(
                "This is not your session!", ephemeral=True
            )

        self.index += 5
        self.previous_button.disabled = False  # Enable 'Previous' button

        if self.index + 5 >= len(self.results):
            self.next_button.disabled = True  # Disable if at last page

        await interaction.response.edit_message(embed=self.get_embed(), view=self)


class Movies(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.media_reminder_loop.start()

    # ================================= DM CHECK ================================= #

    async def is_dm(self, interaction: discord.Interaction) -> bool:
        """Check if the interaction is happening in a DM."""
        return isinstance(interaction.channel, discord.DMChannel)

    # ============================================================================ #
    #                           DATABSE UPDATE COMMAND                             #
    # ============================================================================ #
    @app_commands.command(
        name="delete_media", description="Must be invoked delete a record"
    )
    @app_commands.describe(
        title="If you just need to delete your record leave empty or specify title"
    )
    @app_commands.describe(media_type="Movie or series")
    async def delete_media(
        self,
        interaction: discord.Interaction,
        title: str = None,
        media_type: str = None,):
        """Command for movie recording state management, only usable in DMs."""
        # Check if the command is invoked in a DM
        try:
            await interaction.response.defer()
            if not await self.is_dm(interaction):
                await interaction.response.send_message(
                    "This command can only be used in DMs!", ephemeral=True
                )
                return
            if media_type:
                await MoviesManager.delete_media(
                    interaction.user.id, title=title, media_type=media_type
                )
                await interaction.followup.send(
                    f"Your series '{title}' has been deleted."
                )

            else:
                if await MoviesManager.delete_user_database(interaction.user.id):
                    await interaction.followup.send(
                        "Your media record has been deleted."
                    )
                else:
                    await interaction.followup.send("No records found to delete")
        except Exception as e:
            embed = errorHandler.help_embed()
            errorHandler.handle_exception(e)
            await interaction.followup.send(embed=embed)
            

    # ============================================================================ #
    #                               INSERT MEDIA  CMD                              #
    # ============================================================================ #
    @app_commands.command(
        name="add_media",
        description="Add or update movies.All data entered must match the initial inputs especially titles ",
    )
    @app_commands.describe(
        title="If movie add the descritption if a part or a version of the moive"
    )
    @app_commands.describe(season="If not in seasons 0")
    @app_commands.describe(episode="If not in episodes 0")
    async def add_media(
        self,
        interaction: discord.Interaction,
        title: str,
        media_type: str,
        season: str,
        episode: str,
    ):
        try:
            await interaction.response.defer()
            if not await self.is_dm(interaction):
                await interaction.response.send_message(
                    "This command can only be used in DMs!", ephemeral=True
                )
                return

            try:
                season = int(season)
                episode = int(episode)
            except ValueError:
                await interaction.followup.send("Season and episode must be valid numbers.")
                return
            date_watched = date.today()
            title = title.lower()  # Standardize title for storage
            if media_type.lower() == "series":
                next_release_date = await MoviesManager.add_or_update_series(
                    interaction.user.id,
                    title=title,
                    season=season,
                    episode=episode,
                    date=date_watched,
                )
                await MoviesManager.delete_from_watchlist(
                    interaction.user.id, title=title, media_type=media_type
                )
                embed = discord.Embed(
                title="Series Updated",
                description=f"Your series **{title}** has been added/updated.\n S{season}|| E{episode}\n📅 Watched on: {date_watched}",
                color=discord.Color.blue(),
            )
                if next_release_date:
                    embed.add_field(
                    name="Next Expected Release",
                    value=f"{next_release_date}",
                    inline=False,
                )
                
                await interaction.followup.send(embed=embed)
            elif media_type.lower() == "movie":
                await MoviesManager.add_or_update_movie(
                    interaction.user.id, title=title, date=date_watched
                )
                await MoviesManager.delete_from_watchlist(
                    interaction.user.id, title=title, media_type=media_type
                )

                embed = discord.Embed(
                title="Movie Updated",
                description=f"Your movie **{title}** has been added/updated.\n📅 Watched on: {date_watched}",
                color=discord.Color.green(),
            )
                await interaction.followup.send(embed=embed)
        except Exception as e:
            embed = errorHandler.help_embed()
            errorHandler.handle_exception(e)
            await interaction.followup.send(embed=embed)
    # ============================================================================ #
    #                               LOOK UP MEDIA CMD                              #
    # ============================================================================ #
    @app_commands.command(
        name="search_saved_media", description="Search for a movie or series by title"
    )
    @app_commands.describe(title="Title of the movie or series to search")
    async def search_saved_media(
        self, interaction: discord.Interaction, title: str, media_type: str
    ):
        """Search for movies or series based on a partial title match."""
        try:
            await interaction.response.defer()
            if not await self.is_dm(interaction):
                await interaction.followup.send(
                    "This command can only be used in DMs!", ephemeral=True
                )
                return
            matching_records = await MoviesManager.search_media(
                interaction.user.id, title.lower(), media_type
            )

            if not matching_records:  # No results found
                await interaction.followup.send("No matching movies or series found.")
                return

            # If records are found, proceed to create pagination
            pagination_view = MediaListPaginationView(
                matching_records, media_type=media_type
            )
            embed = pagination_view.create_embed(
                pagination_view.get_current_page_data(), pagination_view.get_total_pages()
            )
            # Send the embed with pagination view
            pagination_view.message = await interaction.followup.send(
                embed=embed, view=pagination_view
            )
        except Exception as e:
            embed = errorHandler.help_embed()
            errorHandler.handle_exception(e)
            await interaction.followup.send(embed=embed)

            
    @app_commands.command(name="all_media", description="List Of all movies or series")
    @app_commands.describe(media_type="movie or series")
    async def all_media(self, interaction: discord.Interaction, media_type: str):
        """All movies and series"""
        if not await self.is_dm(interaction):
            await interaction.response.send_message(
                "This command can only be used in DMs!", ephemeral=True
            )
            return
        await interaction.response.defer()
        data = await MoviesManager.view_media(interaction.user.id, media_type)
        pagination_view = MediaListPaginationView(data, media_type=media_type)
        await interaction.followup.send(
            embed=pagination_view.create_embed(
                pagination_view.get_current_page_data(),
                pagination_view.get_total_pages(),
            ),
            view=pagination_view,
        )
        # Fetch the message object after it is sent
        pagination_view.message = await interaction.original_response()

    # ============================================================================ #
    #                                WACTH_LIST CMDS                               #
    # ============================================================================ #
    @app_commands.command(
        name="watch_list", description="List Of all watchlist movies or series"
    )
    @app_commands.describe(media_type="movie or series")
    async def watch_list(self, interaction: discord.Interaction, media_type: str):
        """This function shows the uers wacthlist based on movie typ"""
        await interaction.response.defer()
        if not await self.is_dm(interaction):
            await interaction.followup.send(
                "This command can only be used in DMs!", ephemeral=True
            )
            return
        data = await MoviesManager.view_watch_list(interaction.user.id, media_type)
        pagination_view = MediaListPaginationView(
            data, media_type=media_type, watchlist=True
        )
        await interaction.followup.send(
            embed=pagination_view.create_embed(
                pagination_view.get_current_page_data(),
                pagination_view.get_total_pages(),
            ),
            view=pagination_view,
        )
        # Fetch the message object after it is sent
        pagination_view.message = await interaction.original_response()

    @app_commands.command(
        name="update_watchlist", description="Add or update the watchlist"
    )
    @app_commands.describe(media_type="movie or series")
    @app_commands.describe(title="Media title")
    @app_commands.describe(extra="Any additional details (optional)")
    async def update_watchlist(
        self,
        interaction: discord.Interaction,
        title: str,
        media_type: str,
        extra: str = None,
    ):
        """Command to add or update a movie/series in the user's watchlist"""

        await interaction.response.defer(
            thinking=True
        )  # Ensure proper response handling
        if not await self.is_dm(interaction):
            await interaction.followup.send(
                "This command can only be used in DMs!", ephemeral=True
            )
            return
        if media_type == "series":
            media_type = "tv"
        try:
            date_added = date.today()
            title = title.lower()  # Standardize title formatting
            # Ensure MoviesManager has the method defined properly
            if not hasattr(MoviesManager, "add_or_update_watch_list"):
                raise AttributeError(
                    "MoviesManager is missing method 'add_or_update_watch_list'"
                )

            await MoviesManager.add_or_update_watch_list(
                interaction.user.id,
                title=title,
                date=date_added,
                extra=extra,
                media_type=media_type,
            )
            await interaction.followup.send(
                f"Your {media_type} '{title}' has been added/updated."
            )
        except Exception as e:
            await interaction.followup.send(f"Error updating watchlist: {e}")
            errorHandler.handle_exception(e)


    # ============================================================================ #
    #                                   API CALLS                                  #
    # ============================================================================ #
    @app_commands.command(
        name="search_anime",
        description="This command only looks the anime up on hanime only",
    )
    @app_commands.describe(media_name="name of the anime you are looking for")
    async def search_anime(self, interaction: discord.Interaction, media_name: str):
        await interaction.response.defer(thinking=True)
        if not await self.is_dm(interaction):
            await interaction.followup.send("This command can only be used in DMs!",ephemeral=True)
            return
        tv_data = await MoviesManager.search_hianime(media_name)
        if not tv_data:
            await interaction.followup.send("No anime found for that name.", ephemeral=True)
            return
        view = MediaSearchPaginator(tv_data, interaction.user)
        await interaction.followup.send(embed=view.get_embed(), view=view)

    @app_commands.command(name="search_movie_or_series",description="The more refined the name is the more refined the search will be",)
    @app_commands.describe(media_name="what you are looking for")
    async def search_movie_or_series(self, interaction: discord.Interaction, media_name: str, media_type: str):
        if media_type == "series":
            media_type = "tv"
        await interaction.response.defer(thinking=True)
        if not await self.is_dm(interaction):
            await interaction.followup.send(
                "This command can only be used in DMs!", ephemeral=True
            )
            return
        media_data = await MoviesManager.get_media_details(media_type, media_name)
        if not media_data:
            await interaction.followup.send(
                f"No data found for {media_name}.", ephemeral=True
            )
            return
        if media_type == "tv":
            for result in media_data.values():
                embed = discord.Embed(
                    title=result["title"],
                    description=(
                        result["overview"][:500] + "..."
                        if len(result["overview"]) > 500
                        else result["overview"]
                    ),  # Limit description size
                    color=discord.Color.blue(),
                    url=result["homepage"] if result.get("homepage") else None,
                )

                if result.get("poster_url"):
                    embed.set_thumbnail(url=result["poster_url"])

                embed.add_field(
                    name="Genres",
                    value=", ".join(result["genres"]) if result["genres"] else "N/A",
                    inline=True,
                )
                embed.add_field(
                    name="Release Date",
                    value=(
                        result["release_date"] if result.get("release_date") else "N/A"
                    ),
                    inline=True,
                )
                embed.add_field(
                    name="Last Aired",
                    value=(
                        result["last_air_date"]
                        if result.get("last_air_date")
                        else "N/A"
                    ),
                    inline=True,
                )
                embed.add_field(
                    name="Next Episode", value=result["next_episode_date"], inline=True
                )
                embed.add_field(name="Status", value=result["status"], inline=True)
                embed.add_field(
                    name="Networks",
                    value=(
                        ", ".join(result["networks"]) if result["networks"] else "N/A"
                    ),
                    inline=False,
                )

                seasons_info = "\n".join(
                    [
                        f"Season {s['season_number']}: {s['episode_count']} episodes"
                        for s in result["seasons"]
                    ]
                )
                embed.add_field(
                    name="Seasons",
                    value=seasons_info if seasons_info else "N/A",
                    inline=False,
                )
                embed.set_footer(
                    text="If its an anime you can use the search anime command to find it on hianime\n Data from TMBD"
                )

                await interaction.followup.send(embed=embed)
        else:
            for result in media_data.values():

                embed = discord.Embed(
                    title=result["title"],
                    description=(
                        result["overview"][:500] + "..."
                        if len(result["overview"]) > 500
                        else result["overview"]
                    ),  # Limit description size
                    color=discord.Color.blue(),
                    url=result["homepage"] if result.get("homepage") else None,
                )

                if result.get("poster_url"):
                    embed.set_thumbnail(url=result["poster_url"])

                embed.add_field(
                    name="Genres",
                    value=", ".join(result["genres"]) if result["genres"] else "N/A",
                    inline=True,
                )
                embed.add_field(
                    name="Release Date",
                    value=(
                        result["release_date"] if result.get("release_date") else "N/A"
                    ),
                    inline=True,
                )
                embed.add_field(name="Status", value=result["status"], inline=True)
                if ( "belongs_to_collection" in result and result["belongs_to_collection"]):
                    collection = result["belongs_to_collection"]
                    collection_name = collection.get("name", "Unknown Collection")
                    collection_poster = collection.get("poster_path")
                    collection_backdrop = collection.get("backdrop_path")

                    embed.add_field(name="Collection", value=collection_name, inline=False)

                    if collection_poster:
                        embed.set_image(url=f"https://image.tmdb.org/t/p/w500{collection_poster}")
                    elif collection_backdrop:
                        embed.set_image( url=f"https://image.tmdb.org/t/p/w500{collection_backdrop}")
                embed.set_footer(text="If its an anime you can use the search anime command to find it on hianime\n Data from TMBD")

                await interaction.followup.send(embed=embed)

    # ============================================================================ #
    #                                   reminder                                   #
    # ============================================================================ #
    @tasks.loop(hours=24)
    async def media_reminder_loop(self):
        try:
            upcoming = await MoviesManager.check_upcoming_dates()
            for reminder in upcoming:
                user = self.client.get_user(reminder["user_id"])
                if user:
                    try:
                        embed = discord.Embed(
                            title=f"🔔 **Media Reminder:**\n{reminder['name']} coming up on <t:{int(datetime.strptime(reminder['next_release_date'], '%Y-%m-%d').timestamp())}:D>",
                            description="**Media Details**",
                            color=discord.Color.blue(),
                        )

                        if reminder.get("status"):
                            embed.add_field(name="⚠️ Status", value=reminder["status"], inline=False)
                            embed.add_field(
                                name="Release Date",
                                value=f"<t:{int(datetime.strptime(reminder['release_date'], '%Y-%m-%d').timestamp())}:D>",
                                inline=False,
                            )
                        else:
                            season = reminder.get('season', '?')
                            episode = reminder.get('episode', '?')
                            embed.add_field(name="⚠️ Status", value="Watching", inline=False)
                            embed.add_field(
                                name="Details",
                                value=f"S{season} E{episode}",
                                inline=False,
                            )

                        await user.send(embed=embed)

                    except discord.HTTPException as dm_error:
                        errorHandler.handle_exception(dm_error)

        except Exception as e:
            errorHandler.handle_exception(e)

    # ============================================================================ #
    #                                 AUTOCOMPLETE                                 #
    # ============================================================================ #
    @delete_media.autocomplete("media_type")
    @watch_list.autocomplete("media_type")
    @add_media.autocomplete("media_type")
    @update_watchlist.autocomplete("media_type")
    @search_saved_media.autocomplete("media_type")
    @search_movie_or_series.autocomplete("media_type")
    @all_media.autocomplete("media_type")  # Correct decorator placement
    async def type_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> typing.List[app_commands.Choice[str]]:
        try:
            choices = ["series", "movie"]
            filtered_choices = [
                app_commands.Choice(name=choice, value=choice)
                for choice in choices
                if current.lower() in choice.lower()
            ]
            return filtered_choices
        except discord.errors.NotFound:
            # Ignore the "Unknown interaction" error
            return []
        except Exception as e:
            errorHandler.handle_exception(e)
            return []
        except discord.errors.HTTPException as e:
            errorHandler.handle_exception(e)
            if "Interaction has already been acknowledged" in str(e):
                pass

    @delete_media.autocomplete("title")
    @add_media.autocomplete("title")
    @update_watchlist.autocomplete("title")
    @search_saved_media.autocomplete("title")
    async def list_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> typing.List[app_commands.Choice[str]]:
        try:
            choices = []
            data_movie = await MoviesManager.view_media(interaction.user.id, "movie")
            data_series = await MoviesManager.view_media(interaction.user.id, "series")
            data_watchlis_series = await MoviesManager.view_watch_list(
                interaction.user.id, "series"
            )
            data_watchlis_movie = await MoviesManager.view_watch_list(
                interaction.user.id, "movie"
            )
            # Combine movies and series titles
            for item in (
                data_movie + data_series + data_watchlis_movie + data_watchlis_series
            ):
                choices.append(item[1])

            # Filter based on user input and limit to 25 results
            filtered_choices = [
                app_commands.Choice(name=choice, value=choice)
                for choice in choices
                if current.lower() in choice.lower()
            ][
                :25
            ]  # Limit to 25 choices

            return filtered_choices
        except discord.errors.NotFound:
            # Ignore the "Unknown interaction" error
            return []
        except Exception as e:
            errorHandler.handle_exception(e)
            return []
        except discord.errors.HTTPException as e:
            errorHandler.handle_exception(e)
            if "Interaction has already been acknowledged" in str(e):
                pass


async def setup(client):
    await client.add_cog(Movies(client))
