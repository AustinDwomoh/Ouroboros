from operator import ne
import aiohttp
from settings import ErrorHandler,FONT_DIR  # for Dir
import discord, typing,asyncio,requests
from discord import app_commands
from discord.ext import commands, tasks
from dbmanager import MoviesManager
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from datetime import date,datetime, timezone
errorHandler = ErrorHandler()

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
                name=f"{media['title']}",
                value=f"[Watch Here]({media['link']}) || " f"[Poster]({thumbnail_url})",
                inline=False,
            )
        embed.set_footer(
            text=f"Page {self.index//5 + 1} of {((len(self.results) - 1) // 5) + 1}"
        )
        return embed

    @discord.ui.button(
        label="Previous", style=discord.ButtonStyle.secondary, disabled=True
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

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
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

class MediaListPaginationView(discord.ui.View):
    def __init__(self, data, media_type, sep=10, timeout=60, watchlist=False):
        super().__init__(timeout=timeout)
        self.data = data
        self.sep = sep
        self.media_type = media_type
        self.current_page = 1
        self.watch_list = watchlist
        self.message = None

    def wrap_text(self,text, font, max_width):
        words = text.split()
        line = ""
        lines = []
        for word in words:
            test_line = f"{line} {word}".strip()
            if font.getlength(test_line) <= max_width:
                line = test_line
            else:
                lines.append(line)
                line = word
        if line:
            lines.append(line)
        return lines[:2]  # Max 2 lines

    async def generate_media_image(self, page_data):
        row_height = 80
        image_width = 900
        margin = 10
        avatar_size = 50
        font_size = 24
        background_color = (44, 47, 51, 255)
        text_color = (255, 255, 255)
        max_title_width = image_width - (margin * 2 + avatar_size + 100)

        image_height = len(page_data) * (row_height + margin) + margin
        base_img = Image.new("RGBA", (image_width, image_height), color=background_color)
        draw = ImageDraw.Draw(base_img)
        overlay = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)

        try:
            font = ImageFont.truetype(str(FONT_DIR / "OpenSans-Bold.ttf"), font_size)
        except Exception:
            font = ImageFont.load_default()

        urls = [item.get("api_data", {}).get("poster_url") for item in page_data]
        avatars = await self.download_all_avatars(urls, avatar_size)
        for i, item in enumerate(page_data):
            y = margin + i * (row_height + margin)
            x = margin
            db_data = item.get("db_data", {})
            index = (self.current_page - 1) * self.sep + i + 1
            title = db_data.get("title", "Unknown Title")
            air_date = str(db_data.get("date") or "")
            season = db_data.get("season")
            episode = db_data.get("episode")
            avatar = avatars[i]
            # === Draw Avatar === #
            if avatar:
                avatar = self.circular_crop(avatar)
                base_img.paste(avatar, (x, y), avatar)

            # === Left: Rank + Title === #
            rank_text = f"#{index}"
            rank_x = x + avatar_size + margin
            draw.text((rank_x, y), rank_text, font=font, fill=text_color)

            rank_text_width = draw.textlength(rank_text, font=font)
            title_x = rank_x + rank_text_width + 8
            title_lines = self.wrap_text(title, font, max_title_width)
            truncated_title = " ".join(title_lines)
            draw.text((title_x, y), f"• {truncated_title}", font=font, fill=text_color)

            # === Center: Season/Episode === #
            if season  or episode:
                season_text = f"S{season} E{episode}"
                season_x = title_x + draw.textlength(f"• {truncated_title}", font=font) + 10
                draw.text((season_x, y), season_text, font=font, fill=text_color)
           

            # === Right: Air Date === #
            if air_date:
                date_width = draw.textlength(air_date, font=font)
                date_x = image_width - margin - date_width
                date_y = y + (row_height - font_size) // 2
                draw.text((date_x, date_y), air_date, font=font, fill=text_color)

            # === Separator Line === #
            line_y = y + row_height + 2
            overlay_draw.line([(margin, line_y), (image_width - margin, line_y)], fill=(255, 255, 255, 80), width=1)

        return Image.alpha_composite(base_img, overlay)

    async def download_all_avatars(self,urls, avatar_size):
        async with aiohttp.ClientSession() as session:
            tasks = [self.download_avatar(session, url, avatar_size) for url in urls]
            return await asyncio.gather(*tasks)
        
    async def download_avatar(self, session, url, avatar_size):
        if not url or not isinstance(url, str):
            return None
        try:
            async with session.get(url, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    avatar = Image.open(BytesIO(data)).convert("RGBA")
                    return avatar.resize((avatar_size, avatar_size))
        except Exception as e:
            print(f"[WARN] Avatar failed: {e}")
        return None
    
    def circular_crop(self, im):
        size = im.size
        mask = Image.new('L', size, 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0) + size, fill=255)
        output = Image.new("RGBA", size, (0, 0, 0, 0))
        output.paste(im, (0, 0), mask)
        return output

    def get_current_page_data(self):
        from_item = (self.current_page - 1) * self.sep
        until_item = from_item + self.sep
        return self.data[from_item:until_item]

    def get_total_pages(self):
        return (len(self.data) - 1) // self.sep + 1

    async def get_embed_and_file(self):
        page_data = self.get_current_page_data()
        total_pages = max(1, self.get_total_pages())

        img = await self.generate_media_image(page_data)
        from io import BytesIO
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        discord_file = discord.File(buffer, filename="medialist.png")

        embed = discord.Embed(
            title=f"{self.media_type.capitalize()} Page {self.current_page}/{total_pages}",
            color=discord.Color.blurple()
        )
        embed.set_image(url="attachment://medialist.png")
        embed.set_footer(text="Use the buttons below to navigate pages.")
        return embed, discord_file

    async def update_message(self, interaction: discord.Interaction):
        embed, discord_file = await self.get_embed_and_file()
        await interaction.response.edit_message(embed=embed, view=self, attachments=[discord_file])

    # ============================= BUTTONS ============================= #
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

class Movies(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.loop_lock = asyncio.Lock()
        self.media_reminder_loop.start()
        self.check_completion_loop.start()

    # ================================= DM CHECK ================================= #

    async def is_dm(self, interaction: discord.Interaction) -> bool:
        """Check if the interaction is happening in a DM."""
        return isinstance(interaction.channel, discord.DMChannel)

    # ============================================================================ #
    #                           DATABSE UPDATE COMMAND                             #
    # ============================================================================ #
    @app_commands.command(name="delete_media", description="Must be invoked delete a record")
    @app_commands.describe(title="If you just need to delete your record leave empty or specify title")
    @app_commands.describe(media_type="Movie or series")
    @app_commands.dm_only()
    async def delete_media(
        self,
        interaction: discord.Interaction,
        title: str = None,
        media_type: str = None,):
        """Command for movie recording state management, only usable in DMs."""
        # Check if the command is invoked in a DM
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(thinking=True, ephemeral=True)
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
        except discord.DiscordException as e:
            errorHandler.handle(e, context="Error in delete_media command")
        except Exception as e:
            errorHandler.handle(e, context="Error in delete_media command final block")
            

    # ============================================================================ #
    #                               INSERT MEDIA  CMD                              #
    # ============================================================================ #
    @app_commands.command(name="add_media",description="Add or update movies.All data entered must match the initial inputs especially titles ",)
    @app_commands.describe(title="If movie add the description if a part or a version of the movie")
    @app_commands.describe(season="If not in seasons 0")
    @app_commands.describe(episode="If not in episodes 0")
    @app_commands.dm_only()
    async def add_media(self,interaction: discord.Interaction,title: str,media_type: str,season: str,episode: str,):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(thinking=True, ephemeral=True)
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
                next_release_date = await MoviesManager.add_or_update_series(interaction.user.id,title=title,season=season,episode=episode,date=date_watched,)
                await MoviesManager.delete_from_watchlist(interaction.user.id, title=title, media_type=media_type)
                embed = discord.Embed(
                title="Series Updated",
                description=f"Your series **{title}** has been added/updated.\n Details: S{season} - E{episode}\n“… Watched on: {date_watched}",
                color=discord.Color.blue(),)
                if next_release_date:
                    embed.add_field(name="Next Expected Release",value=f"{next_release_date}",inline=False,)
                await interaction.followup.send(embed=embed)
            elif media_type.lower() == "movie":
                await MoviesManager.add_or_update_movie(interaction.user.id, title=title, date=date_watched)
                await MoviesManager.delete_from_watchlist(interaction.user.id, title=title, media_type=media_type)
                embed = discord.Embed(
                title="Movie Updated",
                description=f"Your movie **{title}** has been added/updated.\n“… Watched on: {date_watched}",
                color=discord.Color.green(),)
                await interaction.followup.send(embed=embed)
        except discord.DiscordException as e:
            errorHandler.handle(e,context="Error in add_media command")
        except Exception as e:
            errorHandler.handle(e,context="Error in add_media command final block")
    # ============================================================================ #
    #                               LOOK UP MEDIA CMD                              #
    # ============================================================================ #
    @app_commands.command(name="search_saved_media", description="Search for a movie or series by title")
    @app_commands.describe(title="Title of the movie or series to search")
    @app_commands.dm_only()
    async def search_saved_media(
        self, interaction: discord.Interaction, title: str, media_type: str):
        """Search for movies or series based on a partial title match."""
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(thinking=True, ephemeral=True)
            if not await self.is_dm(interaction):
                await interaction.followup.send(
                    "This command can only be used in DMs!", ephemeral=True
                )
                return
            
            data = await MoviesManager.search_media(interaction.user.id, title.lower(), media_type)
            result = data.get('api_data')
            db_data = data.get('db_data')
            name,last_watched, current_season, current_episode = (db_data.get('title'),db_data.get('date', "Unknown date"),db_data.get('season', 1),db_data.get('episode', 1))
            embed = discord.Embed(
                    title=name,
                    description=(
                        result.get("overview")[:500] + "..."
                        if len( result.get("overview")) > 500
                        else  result.get("overview")
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
            embed.add_field(name="Release Date",value=(result["release_date"] if result.get("release_date") else "N/A"),inline=True,)
            if media_type == "series":
                embed.add_field(name="Last Aired",value=(result["last_air_date"] if result.get("last_air_date") else "N/A"),inline=True,)
                embed.add_field(name="Current Details",value=f"S{current_season} E{current_episode} \n Last Watched {last_watched}",inline=True,)
                embed.add_field(name="Next Episode", value=result["next_episode_date"], inline=True)
                last_released = result['last_episode']
                last_season = last_released.get("season", 0)
                last_episode = last_released.get("episode", 0)
                embed.add_field(name="Last released Details",value=f"S{last_season} E{last_episode}",inline=True,)
                embed.add_field(name="Status", value=result["status"], inline=True)
                
            else:
                embed.add_field(name="Status", value=result["status"], inline=True)
                if ( "belongs_to_collection" in result and result["belongs_to_collection"]):
                    collection = result["belongs_to_collection"]
                    collection_name = collection.get("name", "Unknown Collection")
                    embed.add_field(name="Collection", value=collection_name, inline=False)
                embed.add_field(name="Watched On", value=f"{last_watched}", inline=True)
            await interaction.followup.send(embed=embed)
        except discord.DiscordException as e:
            errorHandler.handle(e, context="Error in search_saved_media command")
        except Exception as e:
            errorHandler.handle(e, context="Error in search_saved_media command final block")

    @app_commands.command(
        name="search_anime",
        description="This command only looks the anime up on hanime only",)
    @app_commands.describe(media_name="name of the anime you are looking for")
    @app_commands.dm_only()
    async def search_anime(self, interaction: discord.Interaction, media_name: str):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(thinking=True, ephemeral=True)
            if not await self.is_dm(interaction):
                await interaction.followup.send("This command can only be used in DMs!",ephemeral=True)
                return
            tv_data = await MoviesManager.search_hianime(media_name)
            if not tv_data:
                await interaction.followup.send("No anime found for that name.", ephemeral=True)
                return
            view = MediaSearchPaginator(tv_data, interaction.user)
            await interaction.followup.send(embed=view.get_embed(), view=view)
        except discord.DiscordException as e:
            errorHandler.handle(e, context="Error in search_anime command")
        except Exception as e:
            errorHandler.handle(e, context="Error in search_anime command final block")

    
        
    @app_commands.command(name="all_media", description="List Of all movies or series")
    @app_commands.describe(media_type="movie or series")
    @app_commands.dm_only()
    async def all_media(self, interaction: discord.Interaction, media_type: str):
        """All movies and series"""
        try:
            if not await self.is_dm(interaction):
                await interaction.response.send_message(
                    "This command can only be used in DMs!", ephemeral=True
                )
                return
            if not interaction.response.is_done():
                await interaction.response.defer(thinking=True, ephemeral=True)
            data = await MoviesManager.view_media(interaction.user.id, media_type)

            pagination_view = MediaListPaginationView(data, media_type=media_type)
            embed, file = await pagination_view.get_embed_and_file()
            await interaction.followup.send(embed=embed, files=[file], view=pagination_view)

            # Then fetch the sent message object if you want to store it for later editing:
            pagination_view.message = await interaction.original_response()

        except discord.DiscordException as e:
            errorHandler.handle(e, context="Error in all_media command")
        except Exception as e:
            errorHandler.handle(e,context="Error in all_media command final block")

    # ============================================================================ #
    #                                WATCH_LIST CMDS                               #
    # ============================================================================ #
    @app_commands.command(name="watch_list", description="List Of all watchlist movies or series")
    @app_commands.describe(media_type="movie or series")
    @app_commands.dm_only()
    async def watch_list(self, interaction: discord.Interaction, media_type: str):
        """This function shows the user's watchlist based on movie type"""
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(thinking=True, ephemeral=True)
            if not await self.is_dm(interaction):
                await interaction.followup.send(
                    "This command can only be used in DMs!", ephemeral=True
                )
                return
            data = await MoviesManager.view_watch_list(interaction.user.id, media_type)
    
            pagination_view = MediaListPaginationView(data, media_type=media_type)
            embed, file = await pagination_view.get_embed_and_file()
            await interaction.followup.send(embed=embed, files=[file], view=pagination_view)

            # Then fetch the sent message object if you want to store it for later editing:
            pagination_view.message = await interaction.original_response()
        except discord.DiscordException as e:
            errorHandler.handle(e,context="Error in watch_list command")
        except Exception as e:
            errorHandler.handle(e,context="Error in watch_list command final block")

    @app_commands.command(name="update_watchlist", description="Add or update the watchlist")
    @app_commands.describe(media_type="movie or series")
    @app_commands.describe(title="Media title")
    @app_commands.describe(extra="Any additional details (optional)")
    @app_commands.dm_only()
    async def update_watchlist(
        self,
        interaction: discord.Interaction,
        title: str,
        media_type: str,
        extra: str = None,):
        """Command to add or update a movie/series in the user's watchlist"""
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(thinking=True, ephemeral=True)
            if not await self.is_dm(interaction):
                await interaction.followup.send(
                    "This command can only be used in DMs!", ephemeral=True
                )
                return
            if media_type == "series":
                media_type = "tv"
            
                
            date_added = date.today()
            title = title.lower()  

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
        except discord.DiscordException as e:
            errorHandler.handle(e, context="Error in update_watchlist command")
        except Exception as e:
            errorHandler.handle(e,context="Error in update_watchlist command final block")


    @app_commands.command(name="search_movie_or_series",description="The more refined the name is the more refined the search will be",)
    @app_commands.describe(media_name="what you are looking for")
    @app_commands.dm_only()
    async def search_movie_or_series(self, interaction: discord.Interaction, media_name: str, media_type: str):
        if media_type == "series":
            media_type = "tv"
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(thinking=True, ephemeral=True)
            if not await self.is_dm(interaction):
                await interaction.followup.send(
                    "This command can only be used in DMs!", ephemeral=True
                )
                return
            result = await MoviesManager.get_media_details(media_type, media_name)
            if not result:
                await interaction.followup.send(
                    f"No data found for {media_name}.", ephemeral=True
                )
                return
           
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
            if media_type == "tv":
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

            else:
                embed.add_field(name="Status", value=result["status"], inline=True)
                if ( "belongs_to_collection" in result and result["belongs_to_collection"]):
                    collection = result["belongs_to_collection"]
                    collection_name = collection.get("name", "Unknown Collection")
                    

                    embed.add_field(name="Collection", value=collection_name, inline=False)

                embed.set_footer(text="If its an anime you can use the search anime command to find it on hianime\n Data from TMBD")

            await interaction.followup.send(embed=embed)
        except discord.DiscordException as e:
            errorHandler.handle(e, context="Error in search_movie_or_series command")
        except Exception as e:
            errorHandler.handle(e, context="Error in search_movie_or_series command final block") 

    # ============================================================================ #
    #                                   reminder                                   #
    # ============================================================================ #
    async def parse_date_to_timestamp(self,date_str: str) -> int | None:
        try:
            dt = datetime.strptime(date_str, '%Y-%m-%d')
            dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
        except (TypeError, ValueError):
            return None
    @tasks.loop(hours=48)
    async def media_reminder_loop(self):
        async with self.loop_lock:
            upcoming = await MoviesManager.check_upcoming_dates()
            id_list = set()
            for reminder in upcoming:
                user_id = reminder.get("user_id")
                if user_id is None:
                    continue
                id_list.add(user_id)

                user = await self.client.fetch_user(user_id) 
                if user:
                    try:
                        title = reminder.get("name", "Unknown Title")
                        if reminder.get('movie'):
                            date_str = reminder.get('release_date')
                            media_data = await MoviesManager.get_media_details("movie", reminder["name"])
                        else:
                            date_str = reminder.get('next_release_date')
                            media_data = await MoviesManager.get_media_details("tv", reminder["name"])
                        timestamp = await self.parse_date_to_timestamp(date_str)

                        if timestamp:
                            title_text = f"**Media Reminder:**\n{title} coming up on <t:{timestamp}:D>"
                        else:
                            title_text = f"**Media Reminder:**\n{title} coming up soon"

                        embed = discord.Embed(
                            title=title_text,
                            description="**Media Details**",
                            color=discord.Color.blue()
                        )

                        poster_url = media_data.get("poster_url")
                        if poster_url:
                            embed.set_thumbnail(url=poster_url)

                        # Current media details
                        current_season = reminder.get('season', '?')
                        current_episode = reminder.get('episode', '?')
                        current_status = media_data.get("status", "No idea")

                        embed.add_field(name="Status", value=current_status, inline=False)
                        if not reminder.get('movie'):
                            embed.add_field(
                                name="Current Details",
                                value=f"S{current_season} E{current_episode}",
                                inline=False,
                            )
                        next_episode = current_episode
                        next_season = current_season
                        if not reminder.get('movie'):
                            next_episode = media_data.get('next_episode_number', '?')
                            next_season = media_data.get('next_season_number', '?')
                            embed.add_field(
                                name="Expected Details",
                                value=f"S{next_season} E{next_episode}",
                                inline=False,
                            )

                        if reminder.get('movie'):
                            await user.send(embed=embed)
                        else:
                            try:
                                cs = int(current_season)
                                ce = int(current_episode)
                                ns = int(next_season)
                                ne = int(next_episode)
                                if cs == ns and ne != ce:
                                    await user.send(embed=embed)
                            except (TypeError, ValueError):
                                # If any value is missing or not an integer, still send the reminder
                                await user.send(embed=embed)

                        await asyncio.sleep(0.5)
                    except discord.DiscordException as e:
                        errorHandler.handle(e, context="Error in media_reminder_loop")
                    except Exception as e:
                        errorHandler.handle(e, context="Error in media_reminder_loop final block")
            for id in id_list:
                user = await self.client.fetch_user(id) 
                if user:
                    embed = discord.Embed(
                        title=f"Upcoming Updates complete",
                        description=f"New reminders received on <t:{int(datetime.now().timestamp())}:F> (<t:{int(datetime.now().timestamp())}:R>)",
                        color=discord.Color.blue()
                    
                    )

                    await user.send(embed=embed)
            await MoviesManager.refresh_tmdb_dates()

    @tasks.loop(hours=380)
    async def check_completion_loop(self):  
        async with self.loop_lock:
            uncompleted = await MoviesManager.check_completion()
            id_list = set()
            for reminder in uncompleted:
                user_id = reminder.get("user_id")
                if user_id is None:
                    continue
                id_list.add(user_id)

                user = await self.client.fetch_user(user_id)
                try:
                    if user:               
                            embed = discord.Embed(
                                title=reminder["name"],
                                description="**Media Details**",
                                color=discord.Color.blue()
                            )
                            poster_url = reminder.get("poster_url")
                            if poster_url:
                                embed.set_thumbnail(url=poster_url)

                            # Current media details
                            watched_value = reminder.get("watched")
                            if watched_value is not None:
                                current_season, current_episode = watched_value
                            else:
                                current_season, current_episode = None, None
                            unwatched_value = reminder.get("unwatched")
                            if unwatched_value is not None:
                                last_season, last_episode = unwatched_value
                            else:
                                last_season, last_episode = None, None
                            
                            if (last_episode - current_episode) < 5:
                                continue
                            embed.add_field(
                                name="Current Details",
                                value=f"S{current_season if current_season is not None else '?'} E{current_episode if current_episode is not None else '?'}",
                                inline=False,
                            )

                            embed.add_field(
                                name="Last released Details",
                                value=f"S{last_season if last_season is not None else '?'} E{last_episode if last_episode is not None else '?'}",
                                inline=False,
                            )

                            await user.send(embed=embed)
                except discord.DiscordException as e:
                    errorHandler.handle(e, context="Error in check_completion_loop")
                except Exception as e:
                    errorHandler.handle(e, context="Error in check_completion_loop final block")
            
            for id in id_list:
                user = await self.client.fetch_user(id) 
                if user:
                    embed = discord.Embed(
                        title=f"Unfinished Series and Watch list",
                        description=f"New Reminders received <t:{int(datetime.now().timestamp())}:R>",
                        color=discord.Color.green(),
                        
                    )
                    await user.send(embed=embed)
            await MoviesManager.refresh_tmdb_dates()
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
        self, interaction: discord.Interaction, current: str) -> typing.List[app_commands.Choice[str]]:
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
     
            return []
        except discord.errors.HTTPException as e:
            if "Interaction has already been acknowledged" in str(e):
                pass

    @delete_media.autocomplete("title")
    @add_media.autocomplete("title")
    @update_watchlist.autocomplete("title")
    @search_saved_media.autocomplete("title")
    @search_movie_or_series.autocomplete("media_name")
    @search_anime.autocomplete("media_name")
    async def list_autocomplete(
        self, interaction: discord.Interaction, current: str) -> typing.List[app_commands.Choice[str]]:
        try:

            title_list = await MoviesManager.fetch_titles(interaction.user.id)
            choices = []
            for item in title_list:
                
                choices.append(item)

            # Filter based on user input and limit to 25 results
            filtered_choices = [
                 app_commands.Choice(name=choice, value=choice)
                for choice in choices
                if current.lower() in choice.lower()
            ][:25]   # Limit to 25 choices

            return filtered_choices
        except discord.errors.NotFound:
            # Ignore the "Unknown interaction" error
            return []
        except Exception as e:
            return []
        except discord.errors.HTTPException as e:
            if "Interaction has already been acknowledged" in str(e):
                pass


async def setup(client):
    """Asynchronously adds the Movies cog to the Discord client."""
    await client.add_cog(Movies(client))
