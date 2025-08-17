# ============================================================================ #
#                                    IMPORTS                                   #
# ============================================================================ #
import discord,requests,googleapiclient,feedparser
from settings import *  # for Dir
from discord import app_commands
from discord.ext import commands, tasks
from dbmanager import notifmanager



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
            ErrorHandler().handle(e, context="Error in setup_youtube_notification command")

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
                    youtube_channel_id = notifmanager.get_platform_ids_for_channel(channel_id, "YouTube")
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
            ErrorHandler().handle(e,context="Error in check_new_videos task")
        

class Xnotif(commands.Cog):
    def __init__(self, client):
        self.bearer_token = os.environ.get("BEARER_TOKEN")
        self.client = client
        self.check_x_notification.start()  # Start the periodic check

    def get_user_id(self, username):
        """Fetch the user ID for a given X username."""
        username = username.split('@')[1]
        url = f"https://api.twitter.com/2/users/by/username/{username}"
        headers = {"Authorization": f"Bearer {self.bearer_token}"}
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            raise Exception(f"Failed to fetch user ID: {response.status_code} {response.text}")
        return response.json()["data"]["id"]

    def bearer_oauth(self, r):
        """Bearer token authentication method."""
        r.headers["Authorization"] = f"Bearer {self.bearer_token}"
        r.headers["User-Agent"] = "v2UserTweetsPython"
        return r

    async def connect_to_endpoint(self, channel_id):
        """Connect to the X API and fetch tweets."""
        url = f"https://api.twitter.com/2/users/{channel_id}/tweets"
        params = {"tweet.fields": "created_at,attachments"}
        response = requests.get(url, auth=self.bearer_oauth, params=params)
        if response.status_code != 200:
            raise Exception(
                "Request returned an error: {} {}".format(response.status_code, response.text)
            )
        return response.json()

    def get_media_url_from_key(self, media_key):
        """Fetch media URL from media key."""
        url = f"https://api.twitter.com/2/media/{media_key}"
        response = requests.get(url, auth=self.bearer_oauth)
        if response.status_code == 200:
            return response.json().get('data', {}).get('url')
        return None
    
    @tasks.loop(minutes=10)
    async def check_x_notification(self):
        """Periodically check for new updates and notify subscribed Discord channels."""
        try:
            print("Checking for X updates...")
            for guild in self.client.guilds:
                discord_channels_to_notify = notifmanager.get_channel_for_notification(guild.id, 'X')
                if not discord_channels_to_notify:
                    continue

                for channel_id in discord_channels_to_notify:
                    x_channel_id = notifmanager.get_platform_ids_for_channel(channel_id, 'X')

                    if not x_channel_id:
                        continue

                    response = await self.connect_to_endpoint(x_channel_id)

                    # Assuming response has tweets data
                    tweets = response.get("data", [])
                    if not tweets:
                        continue

                    latest_tweet = tweets[0]
                    tweet_id = latest_tweet["id"]
                    tweet_text = latest_tweet["text"]
                    tweet_url = f"https://twitter.com/{x_channel_id}/status/{tweet_id}"

                    # Check if the tweet is new
                    latest_notified_id = notifmanager.get_last_updated_content(channel_id, platform_name="X")
                    if tweet_id == latest_notified_id:
                        continue

                    # Update last notified tweet ID
                    notifmanager.update_last_updated_content(channel_id, platform_name="X", content_id=tweet_id)

                    # Prepare media (images) if any
                    media_urls = []
                    if "attachments" in latest_tweet:
                        media_keys = latest_tweet["attachments"].get("media_keys", [])
                        for media_key in media_keys:
                            media_url = self.get_media_url_from_key(media_key)
                            if media_url:
                                media_urls.append(media_url)

                    # Create the embed
                    embed = discord.Embed(
                        title="New Tweet",
                        description=tweet_text,
                        url=tweet_url,
                        color=discord.Color.blue()
                    )

                    # Add images to embed if they exist
                    if media_urls:
                        for media_url in media_urls:
                            embed.set_image(url=media_url)  # Add each image to the embed

                    # Notify all channels for this guild
                    for discord_channel_id in discord_channels_to_notify:
                        discord_channel = self.client.get_channel(discord_channel_id)
                        if discord_channel:
                            try:
                                await discord_channel.send(embed=embed)
                            except Exception as e:
                                pass
                        

        except Exception as e:
            ErrorHandler().handle(e, context="Error in check_x_notification task")

    @check_x_notification.before_loop
    async def before_check_x_notification(self):
        """Ensure the loop starts after bot is ready."""
        await self.client.wait_until_ready()

    @app_commands.command(name="setup_x_notification", description="Activate notifications for an X channel and Discord channel.")
    @app_commands.guild_only()
    @app_commands.describe(channel="The channel to receive notifications.")
    @app_commands.describe(x_handle="e.g., username")
    async def setup_x_notification(self, interaction: discord.Interaction, channel: discord.TextChannel, x_handle: str):
        """Set up X notifications for a specified Discord channel."""
        try:
            guild_id = interaction.guild.id
            channel_id = channel.id
            channel_name = channel.name

            if not x_handle:
                await interaction.response.send_message(
                    "The X handle is invalid. Please provide a valid handle (e.g., @username).",
                    ephemeral=True
                )
                return None

            notif_type_id = self.get_user_id(x_handle)

            # Link the guild, channel, and notification type
            notifmanager.add_or_update_channel(
                channel_id, guild_id, channel_name, platform_name="X", platform_id=notif_type_id
            )

            # Send confirmation message
            await interaction.response.send_message(
                f"X notifications have been set up for channel {channel.mention}."
            )
        except Exception as e:
            # Handle errors and send an error message
            ErrorHandler().handle(e, context="Error in setup_x_notification command")
 

            """ embed = discord.Embed(title="Error Occurred",description="An error occurred while trying delete your movie records",
                    color=discord.Color.red())
                    embed.add_field(name="Contact for Help", value="Please reach out to me:\n**inphinithy**\n[Send a DM](https://discord.com/users/755872891601551511)", inline=False)
                    await interaction.followup.send(embed=embed) """
            
async def setup(client):
    pass
    #await client.add_cog(YoutubeNotif(client))
    # await client.add_cog(Xnotif(client))
