import discord
import random
from settings import *  # for Dir
from discord import app_commands
from discord.ext import commands


class Embed(commands.Cog):
    @app_commands.command(
        name="create_embed", description="Create an embed of your choice"
    )
    @app_commands.guild_only()
    async def create_embed( self, interaction: discord.Interaction, title: str, description: str, tag: str = None,
    ):
        await interaction.response.defer()
        embed_color = discord.Color.from_rgb(
            random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)
        )
        embed = discord.Embed(title=title, description=description, color=embed_color)
        embed.set_footer(text=f"Embed by {interaction.user.display_name}")
        await interaction.followup.send(tag, embed=embed)


async def setup(client):
    await client.add_cog(Embed(client))
