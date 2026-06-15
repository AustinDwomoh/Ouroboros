from settings import *  # for Dir
import discord
from discord import app_commands
from discord.ext import commands, tasks
from dbmanager import ServerStatManager
from constants import Roles
from handle import handler
# ============================================================================ #
#                                     fixes                                    #
# ============================================================================ #

class ServerStat(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.update_stats.start()  # Start the periodic task

    @tasks.loop(minutes=20)
    async def update_stats(self):
        for guild in self.client.guilds:
            state = await ServerStatManager.get_server_state(guild.id)

            if state == "on":
                member_count = guild.member_count
                role_count = len(guild.roles)
                channel_count = len(guild.channels) - 3

                category_name = "🔒Server Stats🔒"
                existing_category = discord.utils.get(
                    guild.categories, name=category_name
                )

                # Create the category if it doesn’t exist
                if not existing_category:
                    try:
                        category = await guild.create_category(category_name)
                    except Exception as e:
                        handler.error_handle(e, context="Error creating category for server stats")
                        continue
                else:
                    category = existing_category

                # Clear all channels in the category
                for channel in category.channels:
                    try:
                        await channel.delete()
                    except Exception as e:
                        handler.error_handle(e, context="Error deleting existing channels in server stats category")

                # Define permission overwrites
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(connect=False),
                    guild.me: discord.PermissionOverwrite(connect=True),
                }

                # Define names for the stat channels
                stats_channel_names = [
                    f"Members: {member_count}",
                    f"Roles: {role_count}",
                    f"Channels: {channel_count}",
                ]

                # Create new channels with updated stats
                for name in stats_channel_names:
                    try:
                        await guild.create_voice_channel(
                            name, category=category, overwrites=overwrites
                        )
                    except Exception as e:
                        handler.error_handle(e, context="Error creating voice channel for server stats")

    @update_stats.before_loop
    async def before_update_stats(self):
        await self.client.wait_until_ready()

    @commands.Cog.listener()
    async def on_ready(self):
        # Check the state of each guild when bot is ready
        for guild in self.client.guilds:
            state = await ServerStatManager.get_server_state(guild.id)
            if state:
                print(f"Data found for guild {guild.name}: State = {state}")
            else:
                print(f"No data found for guild {guild.name}. Defaulting to 'off'.")

    @app_commands.command(
        name="server_stats", description="Toggle the state of a server for stats"
    )
    @app_commands.guild_only()
    @app_commands.describe(state="The state to set (on or off)")
    async def server_stats(self, interaction: discord.Interaction, state: str):
        if not Roles.check_role_permission(interaction.user, "Tour manager"):
            embed = discord.Embed(
            title="Permission Denied",
            description="You don't have permission to use this command.",
            color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        try:
            await interaction.response.defer()
            guild_id = interaction.guild.id #type: ignore
            state = "on" if state == "on" else "off"  # Ensures only "on" or "off" is stored
            await ServerStatManager.set_server_state(guild_id, state)  # Use DatabaseManager to set server state

            await interaction.followup.send(f"Server_stat set to '{state}' for {interaction.guild.name}") #type: ignore
            await self.update_stats()
        except Exception as e:
            handler.error_handle(e, context="Error in server_stats command")

    @server_stats.autocomplete("state")
    async def state_autocomplete(self, interaction: discord.Interaction, current: str):
        # Provide autocomplete options for the "state" argument
        choices = ["on", "off"]
        return [
            app_commands.Choice(name=choice, value=choice)
            for choice in choices
            if current.lower() in choice.lower()
        ]

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        """
        Triggered when the bot is added to a guild.
        """
       
        await ServerStatManager.set_server_state(guild.id, "off")  # Initialize server state to "off" when joining a new guild
        owner = await guild.fetch_member(guild.owner_id) #type: ignore
        embed = discord.Embed(title="Welcome to Ouroboros!", description=
                              f"Thank you for adding me to {guild.name}!, If you have any questions, feel free to ask!, This is the link to our support server: https://discord.gg/yZaUzRBEbF", color=discord.Color.gold(),
                    timestamp=discord.utils.utcnow())
        embed.set_footer(text="Ouroboros Bot")
        await owner.send(embed=embed)
        handler.log_task(message=f"Joined new guild: {guild.name} ({guild.id})", level="info", context="Guild Join")
        

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        """
        Triggered when the bot is removed from a guild.
        """
        handler.log_task(message=f"Left guild: {guild.name} ({guild.id})", level="info", context="Guild Leave")
        await ServerStatManager.set_server_state(guild.id, "off")
        await ServerStatManager.delete_server(guild.id)
        


async def setup(client):
    await client.add_cog(ServerStat(client))
