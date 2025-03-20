# ============================================================================ #
#                                    IMPORTS                                   #
# ============================================================================ #
import discord,requests,googleapiclient,feedparser
from settings import *  # for Dir
from discord import app_commands
from discord.ext import commands, tasks
from dbmanager import notifmanager

errorHandler = ErrorHandler()

# ============================================================================ #
#                             YOUTUBE NOTIFICATION                             #
# ============================================================================ #
class YoutubeNotif(commands.Cog):  # WORKS ALLRIGHT NEED TO STRESS TEST
    def __init__(self, client):
        self.client = client
        self.check_new_videos.start()  # starts the loop for checking notifications

    def get_channel_id_from_handle(self, interaction: discord.Interaction, handle_url):
        """
        This function takes a handle url and returns the channel id of the channel
        """
        # Extract handle name from the URL (e.g., "@richardschwabe")
        handle = handle_url.split("@")[1]

        url = f"https://www.googleapis.com/youtube/v3/channels"
        params = {"part": "id", "forUsername": handle, "key": YOUTUBE_API_KEY}

        response = requests.get(url, params=params)
        data = response.json()

        if "items" in data and len(data["items"]) > 0:
            return data["items"][0]["id"]  # Channel ID
        else:

            url = f"https://www.googleapis.com/youtube/v3/search"
            params = {
                "part": "snippet",
                "q": f"@{handle}",  # Query the handle
                "type": "channel",
                "key": YOUTUBE_API_KEY,
            }
            response = requests.get(url, params=params)
            data = response.json()

            if "items" in data and len(data["items"]) > 0:
                return data["items"][0]["snippet"]["channelId"]
        return None  # if the channel doesnt exists

    def fetch_rss_feed(self, feed_url):
        """Function for rss feed check for youtube"""
        feed = feedparser.parse(feed_url)
        if "entries" in feed:
            return feed.entries
        else:
            return []

    @app_commands.command(
        name="setup_youtube_notification",
        description="Activate for a youtube channel and the channel to receive the notification",
    )
    @app_commands.guild_only()
    @app_commands.describe(channel="The channel to recevie the notifications")
    @app_commands.describe(youtube_handle="eg. only youtube.com/@username")
    async def setup_youtube_notification(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        youtube_handle: str,
    ):
        """
        Sets up a YouTube notification for the given guild and channel.
        Adds the guild, channel, and notification type to the database.
        """
        try:
            await interaction.response.defer()
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

            guild_id = interaction.guild.id
            channel_id = channel.id
            channel_name = channel.name
            if not youtube_handle or "@" not in youtube_handle.strip():
                await interaction.followup.send(
                    "The YouTube handle is invalid. Please provide a valid handle (e.g., @channel_name) without spaces or extra characters.",
                    ephemeral=True,
                )
                return None

            notif_type_id = self.get_channel_id_from_handle(interaction, youtube_handle)

            notifmanager.add_or_update_channel(
                channel_id,
                guild_id,
                channel_name,
                platform_name="YouTube",
                platform_id=notif_type_id,
            )
            # Send confirmation message
            embed = discord.Embed(
                title="YouTube Notification Setup",
                description=(
                    f"YouTube notifications for `{youtube_handle.split('@')[1]}`'s channel "
                    f"have been set up for {channel.mention} in this server!"
                ),
                color=discord.Color.green(),
            )
            embed.set_footer(text="YouTube Notifications")
            await interaction.followup.send(embed=embed)
        except Exception as e:
            errorHandler.handle_exception(e)

    @tasks.loop(minutes=10)
    async def check_new_videos(self):
        """
        Periodically checks for new videos from YouTube channels and notifies Discord channels.
        """
        try:
            for guild in self.client.guilds:
                discord_channels_to_notify = notifmanager.get_channel_for_notification(
                    guild.id, "YouTube"
                )
                if not discord_channels_to_notify:
                    continue
                for channel_id in discord_channels_to_notify:
                    youtube_channel_id = notifmanager.get_platform_ids_for_channel(
                        channel_id, "YouTube"
                    )

                    if not youtube_channel_id:
                        continue
                    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={youtube_channel_id}"
                    entries = self.fetch_rss_feed(feed_url)

                    if not entries:
                        continue

                    latest_video = entries[0]
                    video_id = latest_video.link.split("v=")[-1]
                    video_title = latest_video.title

                    # Check if the video is new
                    latest_video_id = notifmanager.get_last_updated_content(
                        channel_id, platform_name="YouTube"
                    )

                    if video_id == latest_video_id:
                        continue

                    # Update last notified video ID
                    notifmanager.update_last_updated_content(
                        channel_id, platform_name="YouTube", content_id=video_id
                    )

                    # Notify all channels for this guild
                    for discord_channel_id in discord_channels_to_notify:
                        discord_channel = self.client.get_channel(discord_channel_id)
                        # Sends message with embed and @everyone mention
                        if discord_channel:
                            await discord_channel.send(
                                f"@everyone \n**{video_title}**\n{latest_video.link}"
                            )
        except (discord.HTTPException, googleapiclient.errors.HttpError, KeyError, Exception) as e:
            errorHandler.handle_exception(e)
        


async def setup(client):
    await client.add_cog(YoutubeNotif(client))
    # await client.add_cog(Xnotif(client))
