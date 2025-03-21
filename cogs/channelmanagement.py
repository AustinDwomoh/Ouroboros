# ============================================================================
#                            DISCORD IMPORTS                       =
# ============================================================================
import discord, asyncio
from discord import app_commands
from discord.ext import commands
from settings import ErrorHandler,ALLOWED_ID

errorHandler = ErrorHandler()
# ============================================================================
#                              CHANNEL MANAGEMENT COG                        =
# ============================================================================
class ChannelManagement(commands.Cog):
    """
    ChannelManagement class is a Discord cog that provides commands for managing channels and categories.

    This class includes commands to:
    - Delete specified text channels
    - Delete specified categories along with their channels
    - Clear messages from a channel

    Each command checks for user permissions and handles errors gracefully, providing feedback to the user.
    """

    def __init__(self, client):
        """
        Initializes the ChannelManagement cog with the given Discord client.

        Parameters:
        client (discord.Client): The Discord client instance that this cog will operate with.
        """
        self.client = client

    # ============================================================================
    #                               DELETE CHANNEL COMMAND                       =
    # ============================================================================
    @app_commands.command(name="delete_channels", description="Delete specified channels.")
    @app_commands.guild_only()
    async def delete_channels(self, interaction: discord.Interaction, channels: discord.TextChannel):
        """
        Deletes the specified text channels provided by the user.

        This command checks if the user has permission to delete channels. If the user is not authorized,
        it sends a permission denied message. It then attempts to delete the specified channel and handles
        possible errors such as lack of permissions or HTTP exceptions.

        Parameters:
        interaction (discord.Interaction): The interaction object that contains information about the command invocation.
        channels (discord.TextChannel): The channel to be deleted.
        """

        # Check if the user has permission to delete channels
        if ( interaction.user.id not in ALLOWED_ID and not any( role.permissions.administrator for role in interaction.user.roles)
            and not any( role.permissions.manage_roles or role.permissions.ban_members or role.permissions.kick_members for role in interaction.user.roles)):
            embed = discord.Embed( title="Permission Denied", description="You are not allowed to invoke this command.", color=discord.Color.red(),)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        try:
            await interaction.response.defer()
            # Ensure at least one channel is provided
            if not channels:
                await interaction.followup.send( "Please provide at least one channel to delete.", ephemeral=True)
                return

            # Send a processing embed while deleting the channel
            thinking_embed = discord.Embed(
                title="Processing...",
                description="Please wait while I delete the channel.",
                color=discord.Color.yellow(),
            )
            await interaction.followup.send(embed=thinking_embed, ephemeral=True)

            # Attempt to delete the specified channel
            await channels.delete()
            await interaction.followup.send(
                f"Channel {channels.name} has been deleted."
            )
        except discord.Forbidden as e:
            await interaction.followup.send(
                f"I do not have permission to delete the channel {channels.name}.",
                ephemeral=True,
            )
            errorHandler.handle_exception(e)
        except discord.HTTPException as e:
            await interaction.followup.send(
                f"An error occurred while trying to delete the channel {channels.name}.",
                ephemeral=True,
            )
            errorHandler.handle_exception(e)
        except Exception as e:
            embed = errorHandler.help_embed()
            errorHandler.handle_exception(e)
            await interaction.response.send_message(embed=embed)


    # ============================================================================
    #                             DELETE CATEGORIES COMMAND                      =
    # ============================================================================
    @app_commands.command( name="delete_categories", description="Delete specified categories." )
    @app_commands.guild_only()
    async def delete_categories( self, interaction: discord.Interaction, category: discord.CategoryChannel):
        """
        Deletes the specified categories and all channels under them.

        This command checks if the user has permission to delete categories. If the user is not authorized,
        it sends a permission denied message. It then attempts to delete all channels under the specified
        category, followed by the category itself, handling any errors that may arise.

        Parameters:
        interaction (discord.Interaction): The interaction object that contains information about the command invocation.
        category (discord.CategoryChannel): The category to be deleted along with its channels.
        """

        # Check if the user has permission to delete categories
        if ( interaction.user.id not in ALLOWED_ID and not any(role.permissions.administrator for role in interaction.user.roles)
            and not any( role.permissions.manage_roles or role.permissions.ban_members or role.permissions.kick_members for role in interaction.user.roles )):
            embed = discord.Embed(
                title="Permission Denied",
                description="You are not allowed to invoke this command.",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        try:
            await interaction.response.defer()
            # Send a processing embed while deleting the category
            thinking_embed = discord.Embed(
                title="Processing...",
                description="Please wait while I delete the category and its channels.",
                color=discord.Color.yellow(),
            )
            await interaction.followup.send(embed=thinking_embed, ephemeral=True)

            if not category.channels:
                await interaction.followup.send(
                    f"No channels found under the category {category.name}.",
                    ephemeral=True,
                )
                return
            for channel in category.channels:
                await channel.delete()
            await category.delete()
            await interaction.followup.send(
                f"Category {category.name} and its channels have been deleted."
            )
        except discord.Forbidden as e:
            await interaction.followup.send(
                f"I do not have permission to delete the category {category.name}.",
                ephemeral=True,
            )
            errorHandler.handle_exception(e)
        except discord.HTTPException as e:
            await interaction.followup.send(
                f"An error occurred while trying to delete the category {category.name}.",
                ephemeral=True,
            )
            errorHandler.handle_exception(e)
        except Exception as e:
            embed = errorHandler.help_embed()
            errorHandler.handle_exception(e)
            await interaction.response.send_message(embed=embed)
    # ============================================================================
    #                             CLEAR MESSAGES COMMAND                         =
    # ============================================================================
    @app_commands.command(name="clear_messages", description="Clear messages from a channel.")
    @app_commands.guild_only()
    async def clear_messages( self, interaction: discord.Interaction, channel: discord.TextChannel, limit: int ):
        """
        Clears a specified number of messages from a given text channel or DMs.

        Parameters:
        interaction (discord.Interaction): The interaction object that contains information about the command invocation.
        channel (Optional[discord.TextChannel]): The channel from which messages will be cleared. Defaults to the current channel if None.
        limit (int): The number of messages to delete.
        """
        if ( interaction.user.id not in ALLOWED_ID and not any( role.permissions.administrator for role in interaction.user.roles) and not any(
                role.permissions.manage_roles
                or role.permissions.ban_members
                or role.permissions.kick_members
                for role in interaction.user.roles
            )
        ):
            embed = discord.Embed(
                title="Permission Denied",
                description="You are not allowed to invoke this command.",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.defer()

        if isinstance(channel, discord.TextChannel):
            thinking_embed = discord.Embed(
                title="Processing...",
                description=f"Clearing {limit} messages from {channel.mention}.",
                color=discord.Color.yellow(),
            )
            await interaction.followup.send(embed=thinking_embed, ephemeral=True)

            try:
                deleted_count = 0
                while deleted_count < limit:
                    to_delete = min(10, limit - deleted_count)  # Delete in chunks of 10
                    deleted = await channel.purge(limit=to_delete)
                    deleted_count += len(deleted)
                    await asyncio.sleep(2)  # Add delay to prevent rate limits

                await interaction.followup.send(
                    f"Deleted {deleted_count} messages from {channel.mention}."
                )
            except discord.Forbidden as e:
                errorHandler.handle_exception(e)
                await interaction.followup.send(
                    f"I do not have permission to clear messages in {channel.mention}.",
                    ephemeral=True,
                )
            except Exception as e:
                embed = errorHandler.help_embed()
                errorHandler.handle_exception(e)
                await interaction.response.send_message(embed=embed)

    @app_commands.command(name="hi", description="To esatblish a dm connection")
    @app_commands.guild_only()
    async def hi(self, interaction: discord.Interaction):
        """This command is used to establish a DM connection with the bot."""
        try:
            # Create an embed for the DM message
            dm_embed = discord.Embed(
                title="Hello from Ouroboros!",
                description=(
                    "I am **Ouroboros**, your versatile bot, currently in development. "
                    "Here's how you can get started using my commands:"
                ),
                color=discord.Color.green(),
            )
            dm_embed.add_field(
                name="Commands Available:",
                value=(
                    "1. **/help** - Displays all commands and what they do.\n"
                    "2. **/hi** - Establish a DM connection with me."
                ),
                inline=False,
            )
            await interaction.user.send(embed=dm_embed)
            await interaction.response.send_message(
                "I've sent you a DM with more information about me!", ephemeral=True
            )
        except discord.Forbidden as e:
            error_embed = discord.Embed(
                title="Unable to Send DM",
                description=(
                    "I couldn't send you a direct message. Please make sure your DM settings allow messages from server members."
                ),
                color=discord.Color.red(),
            )
            error_embed.add_field(
                name="How to Fix It:",
                value=(
                    "1. Go to **User Settings** > **Privacy & Safety**.\n"
                    "2. Enable 'Allow direct messages from server members.'"
                ),
                inline=False,
            )
            error_embed.set_footer(text="Once updated, try using /hi again!")
            errorHandler.handle_exception(e)
            await interaction.response.send_message(embed=error_embed, ephemeral=True)
        except Exception as e:
            embed = errorHandler.help_embed()
            errorHandler.handle_exception(e)
            await interaction.response.send_message(embed=embed)
   
    @app_commands.command( name="help", description="Displays a list of commands and their descriptions")
    async def help(self, interaction: discord.Interaction):
        """Displays a list of commands categorized by DM and Server usage."""
        # Create the embed
        embed = discord.Embed(
            title="Ouroboros Command List",
            description=(
                "Here are all the commands you can use with Ouroboros, "
                "categorized by where they are available (DMs or Server):"
            ),
            color=discord.Color.blue(),
        )
        # DM-Only Commands
        embed.add_field(
            name="📩 DM-Only Commands:",
            value=(
                "- **/add-media** - Insert or update a movie in your records.\n"
                "- **/all_media** - Show all stored media (series or movies).\n"
                "- **/delete_movies** - Delete your record completely (irreversible).\n"
                "- **/search_anime** - Looks up an anime and provides links to wacth. Refine the search key to avoid unneccesarry results\n"
                "- **/search_movie_or_series** - Looks up details for a movie or series in depth\n"
                "- **/search_saved_media** - Search for a media you stored.\n"
                "- **/update_watchlist** - Store movies to watch later, automatic reminders, gets cleared when added to your media records\n"
                "- **/watch_list** - Your watchlist\n"
            ),
            inline=False,)
        # Server-Only Commands
        embed.add_field(
            name="🏠 Server-Only Commands:",
            value=(
                "- **/activate_tournament** - Initiates the daily quick tour program (Admin-only).\n"
                "- **/clear_message** - Delete a specified number of messages in a channel (Admin-only).\n"
                "- **/coinflip** - A flip game between two users; reacts to the first two clicks.\n"
                "- **/delete_categories** - Delete all categories (Admin-only).\n"
                "- **/delete_channels** - Delete all channels (Admin-only).\n"
                "- **/leaderboard** - View the games ranking (global or specific game).\n"
                "- **/level_self** - View your level in the ranking.\n"
                "- **/level_server** - View the leaderboard of actives in the ranking.\n"
                "- **/rank** - View your ranking in games.\n"
                "- **/rpvp** - Play Rock-Paper-Scissors against another player.\n"
                "- **/setup_youtube_notifications**- It automatically send video updates for added youtube channels\n"
                "- **/server_stats** - Admin command to track server data.\n"
                "- **/create_embed** - Create an embed with a specified title and description.Can also tag members\n"
                "- **/set_goodbye_channel** - Set the goodbye channel (Admin-only).\n"
                "- **/set_welcome_channel** - Set the welcome channel (Admin-only).\n\n\n"
            ),
            inline=False,
        )
        # Universal Commands
        embed.add_field(
            name="\n\n\n🌟 Universal Commands:",
            value=(
                "- **/ouroboros** - Get quotes.\n"
                "- **/rps** - Play Rock-Paper-Scissors (scores aren’t stored in DM's).\n"
                "- **/sporty** - Play a Red or Black and Even/Odd game (scores aren’t stored in DM's).\n"
                "- **/help** - Displays all commands and what they do.\n"
                "- **/hi** - Establish a DM connection with me."
            ),
            inline=False,
        )
        embed.add_field(
            name="Contact for Help If an admin cant use a command",
            value="Please reach out to me:\n**Inphinithy**\n[Send a DM](https://discord.com/users/755872891601551511)",
            inline=False,
        )
        # Footer
        embed.set_footer(
            text="Use commands in the appropriate location (DMs or Server). Admin-only commands require permissions."
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ============================================================================
#                                   SETUP FUNCTION                           =
# ============================================================================
async def setup(client):
    """Sets up the ChannelManagement cog."""
    await client.add_cog(ChannelManagement(client))

