import typing

import discord
from discord import app_commands
from discord.ext import commands

from handle import handler
from dbmanager.MovieManager import MovieManager
from dbmanager.SharedCollectionManager import sharedCollectionManager
from constants import MediaType
from views.movieView import SharedMediaSelectionView, create_selection_embed

movieManager = MovieManager()


def _media_type_label(media_type: str | None) -> str:
    if not media_type:
        return "N/A"
    try:
        media_type_obj = MediaType.find_media_type(media_type)
    except ValueError:
        return media_type
    return media_type_obj.table_name.title() if media_type_obj else media_type


class InviteView(discord.ui.View):
    def __init__(self, invite_id: int):
        super().__init__(timeout=7 * 24 * 60 * 60)
        self.invite_id = invite_id

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.respond(interaction, True)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.respond(interaction, False)

    async def respond(self, interaction: discord.Interaction, accept: bool):
        try:
            await sharedCollectionManager.respond_to_invite(
                self.invite_id,
                interaction.user.id,
                accept,
            )

            await interaction.response.edit_message(
                content="Invitation accepted." if accept else "Invitation declined.",
                view=self,
            )
        except (PermissionError, ValueError) as error:
            await interaction.response.send_message(str(error), ephemeral=True)
        except Exception as error:
            handler.error_handle(error, context=f"InviteView.respond({self.invite_id})")
            await interaction.response.send_message(
                "Error: Failed to respond to the invitation.", ephemeral=True
            )


class SharedCollections(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client
        self.media_title_cache: dict[str, dict[str, int]] = {}  # {title: {"id": media_id, "tmdb_id": tmdb_id}}

    @app_commands.command(name="shared_create", description="Create a shared watchlist or playlist")
    @app_commands.describe(name="Collection name", collection_type="Watchlist or playlist")
    @app_commands.choices(collection_type=[
        app_commands.Choice(name="Watchlist", value="watchlist"),
        app_commands.Choice(name="Playlist", value="playlist"),
    ])
    async def shared_create(
        self,
        interaction: discord.Interaction,
        name: str,
        collection_type: app_commands.Choice[str],
    ):
        await interaction.response.defer()
        try:
            collection = await sharedCollectionManager.create_collection(
                interaction.user.id,
                name,
                collection_type.value,
            )
            await interaction.followup.send(
                f"Created **{collection['name']}** with ID `{collection['id']}`."
            )
        except (PermissionError, ValueError) as error:
            await interaction.followup.send(str(error), ephemeral=True)
        except Exception as error:
            handler.error_handle(error, context=f"shared_create({name})")
            await interaction.followup.send("Error: Could not create collection.", ephemeral=True)

    @app_commands.command(name="shared_invite", description="Invite a user to a shared collection")
    @app_commands.describe(collection_name="The shared collection to invite the user to", user="The user to invite")
    async def shared_invite(
        self,
        interaction: discord.Interaction,
        collection_name: str,
        user: discord.User,
    ):
        await interaction.response.defer()
        try:
            collection_id = await sharedCollectionManager.get_collection_id(
                interaction.user.id,
                collection_name,
            )
            if collection_id is None:
                raise ValueError("Collection not found")
            invite = await sharedCollectionManager.invite(
                collection_id,
                interaction.user.id,
                user.id,
            )
            await interaction.followup.send(f"Invitation sent to {user.mention}.")
            try:
                await user.send(
                    f"{interaction.user.mention} invited you to shared collection `{collection_name}`.",
                    view=InviteView(invite["id"]),
                )
            except discord.Forbidden:
                pass
        except (PermissionError, ValueError) as error:
            await interaction.followup.send(str(error), ephemeral=True)
        except Exception as error:
            handler.error_handle(error, context=f"shared_invite({collection_name})")
            await interaction.followup.send("Error: Could not send invitation.", ephemeral=True)

    @app_commands.command(name="shared_add", description="Add media to a shared collection")
    @app_commands.describe(
        collection_name="The shared collection to add media to",
        media_title="The title of the media to add",
        media_type="Movie or series (only needed if the title isn't already known)",
    )
    @app_commands.choices(media_type=[
        app_commands.Choice(name="Movie", value="movie"),
        app_commands.Choice(name="Series", value="tv"),
    ])
    async def shared_add(
        self,
        interaction: discord.Interaction,
        collection_name: str,
        media_title: str,
        media_type: app_commands.Choice[str] | None = None,
    ):
        await interaction.response.defer()
        try:
            collection_id = await sharedCollectionManager.get_collection_id(
                interaction.user.id,
                collection_name,
            )
            if collection_id is None:
                raise ValueError("Collection not found")

            media_info = self.media_title_cache.get(media_title)
            if media_info:
                result = await sharedCollectionManager.add_item(collection_id, interaction.user.id, media_info["id"])

                embed = discord.Embed(
                    title="Added to Shared Collection",
                    description=f"**{result['title']}** ({_media_type_label(result['media_type'])}) added to **{result['collection_name']}**",
                    color=discord.Color.green(),
                )
                await interaction.followup.send(embed=embed)

                await self.notify_new_item(interaction.user, result)
                return

            # Not cached locally - search TMDB and let the user pick, same as Movies' add flow
            if media_type is None:
                raise ValueError(
                    f"`{media_title}` isn't in the database yet. "
                    "Pick a `media_type` (movie/series) so it can be searched for."
                )

            media_options = await movieManager.search_media_multiple(media_type.value, media_title)
            if not media_options:
                kind = "movies" if media_type.value == "movie" else "series"
                raise ValueError(f"No {kind} found for: `{media_title}`")

            if len(media_options) > 1:
                embed = create_selection_embed(
                    media_options,
                    "movie" if media_type.value == "movie" else "series",
                    media_title,
                )
                view = SharedMediaSelectionView(
                    media_options,
                    media_type.value,
                    collection_id,
                    collection_name,
                    interaction.user.id,
                )
                await interaction.followup.send(embed=embed, view=view)
                return

            media = media_options[0]
            tmdb_id = media.get("tmdb_id", media["id"])
            media_data = await movieManager.cache_media(media_type.value, tmdb_id)
            if not media_data:
                raise ValueError(f"Failed to fetch details for `{media_title}`")

            result = await sharedCollectionManager.add_item(collection_id, interaction.user.id, media_data.id)  # type: ignore

            embed = discord.Embed(
                title="Added to Shared Collection",
                description=f"**{result['title']}** ({_media_type_label(result['media_type'])}) added to **{result['collection_name']}**",
                color=discord.Color.green(),
            )
            await interaction.followup.send(embed=embed)

            await self.notify_new_item(interaction.user, result)
        except (PermissionError, ValueError) as error:
            await interaction.followup.send(str(error), ephemeral=True)
        except Exception as error:
            handler.error_handle(error, context=f"shared_add({collection_name}, {media_title})")
            await interaction.followup.send("Error: Could not add media to the collection.", ephemeral=True)

    @app_commands.command(name="shared_list", description="Show a shared collection")
    @app_commands.describe(collection_name="The shared collection to view")
    async def shared_list(self, interaction: discord.Interaction, collection_name: str):
        await interaction.response.defer(thinking=True)
        try:
            collection_id = await sharedCollectionManager.get_collection_id(
                interaction.user.id,
                collection_name,
            )
            if collection_id is None:
                await interaction.followup.send("Collection not found.", ephemeral=True)
                return
            collection = await sharedCollectionManager.get_collection(
                collection_id,
                interaction.user.id,
            )
            if not collection:
                await interaction.followup.send(
                    "You are not a member of that collection.",
                    ephemeral=True,
                )
                return

            embed = discord.Embed(
                title=f"{collection['name']} ({collection['collection_type']})",
                description=(
                    f"{len(collection['items'])} item(s) remaining"
                    if collection["items"]
                    else "This collection is empty."
                ),
                color=discord.Color.blue(),
            )
            for idx, item in enumerate(collection["items"][:20], start=1):
                embed.add_field(
                    name=f"{idx}. {item['title']}",
                    value=_media_type_label(item.get("media_type")),
                    inline=False,
                )
            if len(collection["items"]) > 20:
                embed.set_footer(text=f"+ {len(collection['items']) - 20} more items")

            await interaction.followup.send(embed=embed)
        except Exception as error:
            handler.error_handle(error, context=f"shared_list({collection_name})")
            await interaction.followup.send("Error: Could not fetch the collection.", ephemeral=True)

    @app_commands.command(name="shared_watched", description="Mark an item in a shared collection as watched")
    @app_commands.describe(
        collection_name="The shared collection the media is in",
        media_title="The title of the media to mark watched",
        everyone="Mark watched for every member (collection owner only)",
    )
    async def shared_watched(
        self,
        interaction: discord.Interaction,
        collection_name: str,
        media_title: str,
        everyone: bool = False,
    ):
        """Mark a shared collection item watched, modeled after Movies' add/update flow."""
        await interaction.response.defer()
        try:
            collection_id = await sharedCollectionManager.get_collection_id(
                interaction.user.id,
                collection_name,
            )
            if collection_id is None:
                raise ValueError("Collection not found")

            collection = await sharedCollectionManager.get_collection(collection_id, interaction.user.id)
            if not collection:
                raise ValueError("You are not a member of that collection")

            media_item = next(
                (item for item in collection["items"] if item["title"] == media_title),
                None,
            )
            if not media_item:
                raise ValueError(f"`{media_title}` is not in that collection")

            progress = await sharedCollectionManager.mark_watched(
                collection_id,
                media_item["media_id"],
                interaction.user.id,
                everyone,
            )

            status_text = "removed from the collection" if progress["completed"] else "progress updated"
            embed = discord.Embed(
                title=f"Watched {status_text.title()}",
                description=f"**{progress['title']}** in **{progress['collection_name']}**",
                color=discord.Color.green() if progress["completed"] else discord.Color.blue(),
            )
            embed.add_field(
                name="Progress",
                value=f"{progress['watched_count']}/{progress['total_count']} member(s) watched",
                inline=True,
            )
            await interaction.followup.send(embed=embed)

            await self.notify_members(interaction.user, progress)
        except (PermissionError, ValueError) as error:
            await interaction.followup.send(str(error), ephemeral=True)
        except Exception as error:
            handler.error_handle(error, context=f"shared_watched({collection_name}, {media_title})")
            await interaction.followup.send("Error: Could not update watch status.", ephemeral=True)

    async def notify_new_item(self, actor: discord.abc.User, result: dict):
        """DM the other members as soon as new media is added, so they see it instantly."""
        others = [member_id for member_id in result["member_ids"] if member_id != actor.id]
        if not others:
            return
        message = (
            f"{actor.mention} added **{result['title']}** ({_media_type_label(result['media_type'])}) "
            f"to **{result['collection_name']}**!"
        )
        await self._dm_members(others, message)

    async def notify_members(self, actor: discord.abc.User, progress: dict):
        """DM the other members when everyone has watched, or when only one person has watched so far."""
        others = [member_id for member_id in progress["member_ids"] if member_id != actor.id]
        if not others:
            return

        if progress["completed"]:
            message = (
                f"Everyone has now watched **{progress['title']}** in "
                f"**{progress['collection_name']}** — it's been removed from the shared collection!"
            )
        elif progress["watched_count"] == 1:
            message = (
                f"{actor.mention} just watched **{progress['title']}** in "
                f"**{progress['collection_name']}**. You're still catching up!"
            )
        else:
            return

        await self._dm_members(others, message)

    async def _dm_members(self, member_ids: list[int], message: str):
        for member_id in member_ids:
            try:
                user = await self.client.fetch_user(member_id)
                await user.send(message)
            except discord.HTTPException:
                pass

    # ============================================================================ #
    #                                AUTOCOMPLETE                                  #
    # ============================================================================ #

    @shared_invite.autocomplete("collection_name")
    @shared_add.autocomplete("collection_name")
    @shared_list.autocomplete("collection_name")
    @shared_watched.autocomplete("collection_name")
    async def collection_name_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> typing.List[app_commands.Choice[str]]:
        """Return collections the current user belongs to."""
        try:
            collections = await sharedCollectionManager.get_user_collections(
                interaction.user.id,
            )
            search = current.casefold()
            return [
                app_commands.Choice(
                    name=f"{collection['name']} ({collection['collection_type']})",
                    value=collection["name"],
                )
                for collection in collections
                if search in collection["name"].casefold()
            ][:25]
        except Exception as error:
            handler.error_handle(error, context="collection_name_autocomplete")
            return []

    @shared_add.autocomplete("media_title")
    async def media_title_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> typing.List[app_commands.Choice[str]]:
        """Autocomplete for media titles."""
        try:
            self.media_title_cache = await movieManager.fetch_media_names()

            filtered = [
                app_commands.Choice(name=title, value=title)
                for title in self.media_title_cache.keys()
                if current.lower() in title.lower()
            ][:25]  # Discord limit
            return filtered
        except Exception as error:
            handler.error_handle(error, context="media_title_autocomplete")
            return []

    @shared_watched.autocomplete("media_title")
    async def shared_watched_media_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> typing.List[app_commands.Choice[str]]:
        """Autocomplete media titles that are actually in the chosen collection."""
        try:
            collection_name = interaction.namespace.collection_name
            if not collection_name:
                return []
            collection_id = await sharedCollectionManager.get_collection_id(
                interaction.user.id, collection_name
            )
            if collection_id is None:
                return []
            collection = await sharedCollectionManager.get_collection(collection_id, interaction.user.id)
            if not collection:
                return []

            search = current.lower()
            return [
                app_commands.Choice(name=item["title"], value=item["title"])
                for item in collection["items"]
                if search in item["title"].lower()
            ][:25]
        except Exception as error:
            handler.error_handle(error, context="shared_watched_media_autocomplete")
            return []


async def setup(client: commands.Bot):
    await client.add_cog(SharedCollections(client))
