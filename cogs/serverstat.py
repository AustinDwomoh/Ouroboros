from settings import *  # for Dir
import discord
from discord import app_commands
from discord.ext import commands, tasks
from dbmanager import ServerStatManager

ServerStatManager = ServerStatManager.ServerStatManager()  # it works leave it alone 
#i get it now it hasnt been initialized yet is why
# ============================================================================ #
#                                     fixes                                    #
# ============================================================================ #
#the import is like that since unlik the order db classes this one  has an actual class and its causing the issues
errorHandler = ErrorHandler()
class ServerStat(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.update_stats.start()  # Start the periodic task

    @tasks.loop(minutes=20)
    async def update_stats(self):
        for guild in self.client.guilds:
            state = ServerStatManager.get_server_state(guild.id)

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
                        errorHandler.handle_exception(e)
                        continue  # Skip if category creation fails
                else:
                    category = existing_category

                # Clear all channels in the category
                for channel in category.channels:
                    try:
                        await channel.delete()
                    except Exception as e:
                        errorHandler.handle_exception(e)

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
                        errorHandler.handle_exception(e)

    @update_stats.before_loop
    async def before_update_stats(self):
        await self.client.wait_until_ready()

    @commands.Cog.listener()
    async def on_ready(self):
        # Check the state of each guild when bot is ready
        for guild in self.client.guilds:
            state = ServerStatManager.get_server_state(guild.id)
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
        if interaction.user.id not in ALLOWED_ID and not any(
            role.permissions.administrator
            or role.permissions.manage_roles
            or role.permissions.ban_members
            or role.permissions.kick_members
            or role.name == "Tour manager"
            or interaction.user.id == interaction.user.guild.owner_id
            for role in interaction.user.roles
        ):
            embed = discord.Embed(
                title="Permission Denied",
                description="You are not allowed to invoke this command.",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.defer()
        guild_id = interaction.guild.id
        state = "on" if state == "on" else "off"  # Ensures only "on" or "off" is stored
        ServerStatManager.set_server_state(
            guild_id, state
        )  # Use DatabaseManager to set server state

        await interaction.followup.send(
            f"Server_stat set to '{state}' for {interaction.guild.name}"
        )

        await self.update_stats()

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
        inphinithy = await self.client.fetch_user(755872891601551511)
        await inphinithy.send(f"Joined new guild: {guild.name} ({guild.id})")

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        """
        Triggered when the bot is removed from a guild.
        """
        inphinithy = await self.client.fetch_user(755872891601551511)
        await inphinithy.send(f"Left guild: {guild.name} ({guild.id})")
        ServerStatManager.set_server_state(guild.id, "off")


async def setup(client):
    await client.add_cog(ServerStat(client))
