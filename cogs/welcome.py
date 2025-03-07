from PIL import Image, ImageDraw, ImageFont
from settings import *  # for Dir
import discord,requests,os,random
from discord import app_commands
from discord.ext import commands
from dbmanager import ServerStatManager

ServerStatManager = ServerStatManager.ServerStatManager()  # it works leave it alone

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
        channels = ServerStatManager.get_greetings_channel_ids(member.guild.id)
        channel_id = channels.get("welcome")

        if channel_id:
            channel = member.guild.get_channel(channel_id)
            if channel:
                await self.send_welcome_banner(channel, member)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        channels = ServerStatManager.get_greetings_channel_ids(member.guild.id)
        channel_id = channels.get("goodbye")

        if channel_id:
            channel = member.guild.get_channel(channel_id)
            if channel:
                await self.send_goodbye_banner(channel, member)

    async def send_welcome_banner(self, channel, member):
        if not channel:
            return

        welcome_file_path = None
        try:
            # Fetch and prepare the avatar image
            avatar_bytes = requests.get(str(member.display_avatar.url), stream=True).raw
            try:
                avatar = Image.open(avatar_bytes).convert("RGB").resize((167, 167))
            except Exception as e:
                ErrorHandler.handle_exception(e)
                return

            # Apply circular mask to avatar
            alpha = Image.new("L", avatar.size, 0)
            draw = ImageDraw.Draw(alpha)
            draw.ellipse([(0, 0), avatar.size], fill=255)
            avatar.putalpha(alpha)

            # Load and overlay avatar on the banner
            try:
                banner = Image.open(img_dir / "default.png").convert("RGBA")
            except Exception as e:
                ErrorHandler.handle_exception(e)
                return

            overlay = Image.new("RGBA", banner.size, (0, 0, 0, 0))
            x_position = (banner.width - avatar.width) // 2
            y_position = (banner.height - avatar.height) // 2
            overlay.paste(avatar, (x_position, y_position), avatar)
            banner = Image.alpha_composite(banner, overlay)

            # Add welcome text
            draw = ImageDraw.Draw(banner)
            try:
                font = ImageFont.truetype("arial.ttf", 60)
            except IOError as e:
                ErrorHandler.handle_exception(e)
                font = ImageFont.load_default()

            main_color = "white"  # Primary text color
            shadow_color = "gray"  # Shadow color
            text = f"Welcome, {member.name}!"
            text_x = (banner.width - draw.textbbox((0, 0), text, font=font)[2]) // 2
            text_y = banner.height - 60
            draw.text((text_x + 2, text_y + 2), text, font=font, fill=shadow_color)
            draw.text((text_x, text_y), text, font=font, fill=main_color)
            # Save banner image
            welcome_file_path = img_dir / f"welcome_{member.name}.jpg"
            banner.convert("RGB").save(welcome_file_path)

            # Send message and banner in Discord channel
            welcome_message = random.choice(self.welcome_messages).format(
                server_name=member.guild.name, member=member
            )
            await channel.send(welcome_message)
            await channel.send(file=discord.File(welcome_file_path))

        except Exception as e:
            ErrorHandler.handle_exception(e)

        finally:
            # Ensure cleanup of the banner file
            if welcome_file_path and os.path.exists(welcome_file_path):
                os.remove(welcome_file_path)

    async def send_goodbye_banner(self, channel, member):
        if not channel:
            return

        goodbye_file_path = None
        try:
            # Fetch and prepare the avatar image
            avatar_bytes = requests.get(str(member.display_avatar.url), stream=True).raw
            try:
                avatar = Image.open(avatar_bytes).convert("RGB").resize((167, 167))
            except Exception as e:
                ErrorHandler.handle_exception(e)
                return

            # Apply circular mask to avatar
            alpha = Image.new("L", avatar.size, 0)
            draw = ImageDraw.Draw(alpha)
            draw.ellipse([(0, 0), avatar.size], fill=255)
            avatar.putalpha(alpha)

            # Load and overlay avatar on the banner
            try:
                banner = Image.open(img_dir / "default.png").convert("RGBA")
            except Exception as e:
                ErrorHandler.handle_exception(e)
                return

            overlay = Image.new("RGBA", banner.size, (0, 0, 0, 0))
            x_position = (banner.width - avatar.width) // 2
            y_position = (banner.height - avatar.height) // 2
            overlay.paste(avatar, (x_position, y_position), avatar)
            banner = Image.alpha_composite(banner, overlay)

            # Add goodbye text
            draw = ImageDraw.Draw(banner)
            try:
                font = font = ImageFont.truetype("arial.ttf", 60)
            except IOError as e:
                ErrorHandler.handle_exception(e)
                font = ImageFont.load_default()
            # Define text and shadow colors
            main_color = "white"  # Primary text color
            shadow_color = "gray"  # Shadow color
            text = f"Goodbye, {member.name}!"
            text_x = (banner.width - draw.textbbox((0, 0), text, font=font)[2]) // 2
            text_y = banner.height - 60
            draw.text((text_x + 2, text_y + 2), text, font=font, fill=shadow_color)
            draw.text((text_x, text_y), text, font=font, fill=main_color)

            # Save banner image
            goodbye_file_path = img_dir / f"goodbye_{member.name}.jpg"
            banner.convert("RGB").save(goodbye_file_path)

            # Send message and banner in Discord channel
            goodbye_message = random.choice(self.goodbye_messages).format(
                server_name=member.guild.name, member=member
            )
            await channel.send(goodbye_message)
            await channel.send(file=discord.File(goodbye_file_path))

        except Exception as e:
           ErrorHandler.handle_exception(e)

        finally:
            # Ensure cleanup of the banner file
            if goodbye_file_path and os.path.exists(goodbye_file_path):
                os.remove(goodbye_file_path)

    @app_commands.command(
        name="set_welcome_channel",
        description="call this in the channel to serve as your welcome",
    )
    @app_commands.guild_only()
    async def set_welcome_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ):
        """Set the welcome channel for the guild."""
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
        ServerStatManager.set_channel_id(interaction.guild.id, "welcome", channel.id)
        await interaction.response.send_message(
            f"Welcome channel set to {channel.mention}", ephemeral=True
        )

    @app_commands.command(
        name="set_goodbye_channel",
        description="call this in the channel to serve as your goodbye",
    )
    @app_commands.guild_only()
    async def set_goodbye_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ):
        """Set the goodbye channel for the guild."""
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
        ServerStatManager.set_channel_id(interaction.guild.id, "goodbye", channel.id)
        await interaction.response.send_message(
            f"Goodbye channel set to {channel.mention}", ephemeral=True
        )


async def setup(client):
    await client.add_cog(WelcomeGoodbyeCog(client))
