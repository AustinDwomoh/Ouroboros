# ============================================================================
#                            DISCORD IMPORTS                       =
# ============================================================================
import discord, asyncio
from discord import app_commands
from discord.ext import commands
from settings import ALLOWED_ID, DISCORD_HANDLER_WEBHOOK_URL, DISCORD_INTERACTION_WEBHOOK_URL,COMMANDS
from constants import Roles
from handle import handler
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
    #@app_commands.command(name="delete_channels", description="Delete specified channels.")
   #@app_commands.guild_only()
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

       
        if not Roles.check_role_permission(interaction.user, " "):
            embed = discord.Embed(
            title="Permission Denied",
            description="You don't have permission to use this command.",
            color=discord.Color.red(),
            )
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
        except discord.HTTPException as e:
            await interaction.followup.send(
                f"An error occurred while trying to delete the channel {channels.name}.",
                ephemeral=True,
            )
            handler.error_handle(e, context="ChannelManagement.delete_channels")
        except Exception as e:
            handler.error_handle(e, context="ChannelManagement.delete_channels final except")
            await interaction.response.send_message("An error occurred while processing your request.", ephemeral=True)


    # ============================================================================
    #                             DELETE CATEGORIES COMMAND                      =
    # ============================================================================
    #@app_commands.command( name="delete_categories", description="Delete specified categories." )
   # @app_commands.guild_only()
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
        if not Roles.check_role_permission(interaction.user, " "):
            embed = discord.Embed(
            title="Permission Denied",
            description="You don't have permission to use this command.",
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
        except discord.HTTPException as e:
            await interaction.followup.send(
                f"An error occurred while trying to delete the category {category.name}.",
                ephemeral=True,
            )
            handler.error_handle(e, context="ChannelManagement.delete_categories")
        except Exception as e:
            await interaction.followup.send(
                "An error occurred while processing your request.",
                ephemeral=True,
            )
            handler.error_handle(e, context="ChannelManagement.delete_categories")
    # ============================================================================
    #                             CLEAR MESSAGES COMMAND                         =
    # ============================================================================
    #@app_commands.command(name="clear_messages", description="Clear messages from a channel.")
    #@app_commands.guild_only()
    async def clear_messages( self, interaction: discord.Interaction, channel: discord.TextChannel, limit: int ):
        """
        Clears a specified number of messages from a given text channel or DMs.

        Parameters:
        interaction (discord.Interaction): The interaction object that contains information about the command invocation.
        channel (Optional[discord.TextChannel]): The channel from which messages will be cleared. Defaults to the current channel if None.
        limit (int): The number of messages to delete.
        """
        if not Roles.check_role_permission(interaction.user, " "):
            embed = discord.Embed(
            title="Permission Denied",
            description="You don't have permission to use this command.",
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
                await interaction.followup.send(
                    f"I do not have permission to clear messages in {channel.mention}.",
                    ephemeral=True,
                )
            except Exception as e:
                handler.error_handle(e, context="ChannelManagement.clear_messages")
                await interaction.response.send_message("An error occurred while processing your request.")

    @app_commands.command(name="hi", description="To esatblish a dm connection, and get a list of commands")
    async def hi(self, interaction: discord.Interaction):
        """Establish a DM connection and send the full command list."""
        try:
            categories = {}
            for name, data in COMMANDS.items():
                cat = data["category"]
                categories.setdefault(cat, []).append((name, data))


            dm_embed = discord.Embed(
                title="Hello from Ouroboros!",
                description=(
                    "I am **Ouroboros**, your versatile bot designed to assist you "
                    "with a variety of tasks. Here's everything you can do:"
                ),
                color=discord.Color.teal(),
                timestamp=discord.utils.utcnow()
            )

            for cat in ["Universal", "DM", "Server", "Admin"]:
                cmds = categories.get(cat, [])
                if not cmds:
                    continue
                value = "\n".join(
                    f"`/{name}` — {data['description']}" + (" *(admin)*" if data.get("admin") else "")
                    for name, data in cmds
                )
                dm_embed.add_field(name=f" {cat}", value=value, inline=False)

            dm_embed.set_footer(text="Need help? Contact Inphinithy · discord.com/users/755872891601551511")

            await interaction.user.send(embed=dm_embed)
            await interaction.response.send_message(
                "I've sent you a DM with the full command list!", ephemeral=True
            )

        except discord.Forbidden as e:
            error_embed = discord.Embed(
                title="Unable to Send DM",
                description="I couldn't send you a direct message. Please make sure your DM settings allow messages from server members.",
                color=discord.Color.red(),
            )
            error_embed.add_field(
                name="How to fix it:",
                value=(
                    "1. Go to **User Settings** > **Privacy & Safety**.\n"
                    "2. Enable 'Allow direct messages from server members.'"
                ),
                inline=False,
            )
            error_embed.set_footer(text="Once updated, try using /hi again!")
            handler.error_handle(e, context="hi — could not send DM")
            await interaction.response.send_message(embed=error_embed, ephemeral=True)

        except Exception as e:
            handler.error_handle(e, context="hi — final except")
            await interaction.response.send_message(
                embed=handler.get_error_embed(), ephemeral=True
            )
   
    @app_commands.command(name="cleandms", description="Clean the bot dms")
    async def cleandms(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if isinstance(interaction.channel, discord.DMChannel):
            async for msg in interaction.channel.history():
                if msg.author.id == self.client.user.id:
                    try:
                        await msg.delete()
                    except discord.NotFound:
                        pass
                    await asyncio.sleep(2)
                    

# ============================================================================
#                                   SETUP FUNCTION                           =
# ============================================================================
async def setup(client):
    """Sets up the ChannelManagement cog."""
    await client.add_cog(ChannelManagement(client))

