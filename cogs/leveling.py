import discord, requests
from discord import app_commands
from discord.ext import commands
#from dbmanager import LevelinManager
from settings import ErrorHandler
from views.LeaderboardPage import LeaderboardPaginationView
from io import BytesIO



class Levelling(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_message(self, message):
        try:
            if message.author.bot:
                return  # Ignore bot messages
            guild_id = message.guild.id
            user_id = message.author.id
            # Fetch the user's XP and level, or initialize them
            user_data = LevelinManager.get_user_level(guild_id, user_id)
            if user_data:
                xp, level = user_data
            else:
                xp, level = 0, 1
                LevelinManager.insert_or_update_user(guild_id, user_id, xp, level)
            # Add XP and check for level up
            xp += 5  # Customize the XP per message

            def level_up_xp(level, base_xp=100, growth_factor=1.15):
                """
                Calculate the XP needed to level up, with a progressive increase.
                """
                return int(base_xp * (growth_factor ** (level - 1)))

            while xp >= level_up_xp(level):
                xp -= level_up_xp(level)  # Deduct XP required for current level
                level += 1
                embed = discord.Embed(
                title="🎉 Level Up!",
                description=(
                    f"Congratulations **{message.author.mention}**!\n You reached **Level {level}**.\n\n "
                ),
                color=discord.Color.purple()  # pick your color
                )
                embed.set_thumbnail(url=str(message.author.display_avatar.url))
                
                await message.channel.send(embed=embed)
            LevelinManager.insert_or_update_user(guild_id, user_id, xp, level)
        except Exception as e:
            await ErrorHandler().handle(e, context="Levelling Cog on_message")

    @app_commands.command(name="level_self", description="Check your level")
    @app_commands.guild_only()
    async def level_self(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
            user_data = LevelinManager.get_user_level(
                interaction.guild.id, interaction.user.id
            )
            if not user_data:
                await interaction.followup.send(
                    f"{interaction.user.mention}, you have no recorded level data yet."
                )
                return
            xp, level = user_data
            rank = LevelinManager.get_rank(interaction.guild.id, interaction.user.id)  # Get the user's rank
            
            embed = discord.Embed(
                title="🎉 Current Lvl!",
                description=(
                    f"Congratulations **{interaction.user.name}**!\n You are **Rank #{rank} | Level {level}**.\n\n continue chatting to level up more! "
                ),
                color=discord.Color.purple()  # pick your color
            )
            embed.set_thumbnail(url=str(interaction.user.display_avatar.url))
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await ErrorHandler().handle(e, context="Levelling Cog level_self command")
        

    @app_commands.command(name="level_server", description="Check the server leaderboard.")
    @app_commands.guild_only()
    async def level_server(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()

            # Fetch leaderboard data
            top_users = LevelinManager.fetch_top_users(interaction.guild.id)

            table_data = []
            for idx, (user_id, level, xp) in enumerate(top_users,start=1):
                member = interaction.guild.get_member(user_id)
                if member:
                    avatar_url = member.display_avatar.url
                    table_data.append(
                        (idx,member.display_name, level, xp, avatar_url)
                    )

            # Create pagination view
            pagination_view = LeaderboardPaginationView(
                data=table_data,
                sep=5,
                timeout=None
            )

            # Generate the first page's image
            page_data = pagination_view.get_current_page_data()
            img = pagination_view.generate_leaderboard_image(page_data)
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            buffer.seek(0)

            # Prepare discord file
            discord_file = discord.File(buffer, filename="leaderboard.png")

            # Create embed
            embed = discord.Embed(
                title=f"🏆 Leaderboard Page {pagination_view.current_page}/{pagination_view.get_total_pages()}",
                color=discord.Color.gold()
            )
            embed.set_image(url="attachment://leaderboard.png")
            embed.set_footer(text="Use the buttons below to navigate pages.")

            # Send initial message and store it
            pagination_view.message = await interaction.followup.send(
                embed=embed,
                file=discord_file,
                view=pagination_view
            )
        except Exception as e:
            await ErrorHandler().handle(e, context="Levelling Cog level_server command")


async def setup(client):
    await client.add_cog(Levelling(client))
