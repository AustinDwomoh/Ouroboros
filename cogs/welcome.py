from settings import *  # for Dir
import discord,random
from discord import app_commands
from discord.ext import commands
from dbmanager import ServerStatManager
from constants import Roles, channelType
from handle import handler
img_dir = IMGS_DIR


class WelcomeGoodbyeCog(commands.Cog):
    
    def __init__(self, client):
        self.client = client
        self.welcome_messages = [
            "🎉 Welcome to **{server_name}**, {member.mention}! We're thrilled to have you join our community!",
            "👋 Hello, {member.mention}! Welcome to **{server_name}**! Please take a moment to read our rules in the #rules channel.",
            "🌟 Welcome aboard, {member.mention}! We'd love to get to know you better. What's something interesting about yourself?",
            "Welcome, {member.mention}! 🎈 Be sure to check out our #events channel for updates on regular events!",
            "Hey there, {member.mention}! 🎊 If you have any questions or need help, don't hesitate to reach out to any of our staff members!",
        ]
        self.goodbye_messages = [
            "😢 We're sad to see you go, {member.mention}. Thank you for being part of **{server_name}**!",
            "Goodbye, {member.mention}! 🌈 We hope you had a great time with us!",
            "Farewell, {member.mention}! 💔 Remember, our doors are always open if you decide to return!",
            "👋 Bye, {member.mention}! If you ever want to hang out again, you're always welcome back!",
            "Take care, {member.mention}! 🌟 We hope to see you again someday!",
        ]

    @commands.Cog.listener()
    async def on_member_join(self, member):
        try:
            channels = await ServerStatManager.get_greetings_channel_ids(member.guild.id)
            channel_id = channels.get(channelType.WELCOME.value)

            if channel_id:
                channel = member.guild.get_channel(channel_id)
                if channel:
                    await self.send_welcome_banner(channel, member)
        except Exception as e:
            handler.error_handle(e, context="Error in on_member_join listener")

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        try:
            channels = await ServerStatManager.get_greetings_channel_ids(member.guild.id)
            channel_id = channels.get(channelType.GOODBYE.value)

            if channel_id:
                channel = member.guild.get_channel(channel_id)
                if channel:
                    await self.send_goodbye_banner(channel, member)
        except Exception as e:
            handler.error_handle(e, context="Error in on_member_remove listener")

    async def send_welcome_banner(self, channel, member):
        if not channel:
            return
        try:
            # Fetch and prepare the avatar image
            embed = discord.Embed(
                title=f"Welcome To {member.guild.name}",
                description=(f"{random.choice(self.welcome_messages).format(
                server_name=member.guild.name, member=member
            )}"),color=discord.Color.purple()
            )
            embed.set_thumbnail(url=member.display_avatar.url)

            await channel.send(embed=embed)

        except Exception as e:
            handler.error_handle(e, context="Error in send_welcome_banner method")

    async def send_goodbye_banner(self, channel, member):
        if not channel:
            return
        try:
            # Fetch and prepare the avatar image
            embed = discord.Embed(
                title=f"Goodbye {member.guild.name}",
                description=(f"{random.choice(self.goodbye_messages).format(
                server_name=member.guild.name, member=member
            )}"),color=discord.Color.purple()
            )
            embed.set_thumbnail(url=member.display_avatar.url)

            await channel.send(embed=embed)

        except Exception as e:
           handler.error_handle(e, context="Error in send_goodbye_banner method")


    @app_commands.command(
        name="set_welcome_channel",
        description="call this in the channel to serve as your welcome",
    )
    @app_commands.guild_only()
    async def set_welcome_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ):
        """Set the welcome channel for the guild."""
        try:
            if not Roles.check_role_permission(interaction.user, " "):
                embed = discord.Embed(
                title="Permission Denied",
                description="You don't have permission to use this command.",
                color=discord.Color.red(),
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            await ServerStatManager.set_channel_id(interaction.guild.id, channelType.WELCOME, channel.id) #type: ignore
            await interaction.response.send_message(
                f"Welcome channel set to {channel.mention}", ephemeral=True
            )
        except Exception as e:
            handler.error_handle(e, context="Error in set_welcome_channel command")

    @app_commands.command(
        name="set_goodbye_channel",
        description="call this in the channel to serve as your goodbye",
    )
    @app_commands.guild_only()
    async def set_goodbye_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ):
        """Set the goodbye channel for the guild."""
        try:
            if not Roles.check_role_permission(interaction.user, ""):
                embed = discord.Embed(
                    title="Permission Denied",
                    description="You are not allowed to invoke this command.",
                    color=discord.Color.red(),
                )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
            await ServerStatManager.set_channel_id(interaction.guild.id, channelType.GOODBYE, channel.id) #type: ignore
            await interaction.response.send_message(
                f"Goodbye channel set to {channel.mention}", ephemeral=True
            )
        except Exception as e:
            handler.error_handle(e, context="Error in set_goodbye_channel command")


async def setup(client):
    await client.add_cog(WelcomeGoodbyeCog(client))
