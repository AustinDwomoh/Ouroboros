import discord
import random
from settings import ErrorHandler,ALLOWED_ID
from discord import app_commands
from discord.ext import commands


class EmbedCog(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client

    @app_commands.command(
        name="create_embed", description="Create an embed of your choice"
    )
    @app_commands.guild_only()
    async def create_embed(
        self, interaction: discord.Interaction, title: str, description: str, tag: str = None
    ):
        await interaction.response.defer()
        embed_color = discord.Color.from_rgb(
            random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)
        )
        embed = discord.Embed(title=title, description=description, color=embed_color)
        embed.set_footer(text=f"Embed by {interaction.user.display_name}")

        content = tag if tag else ""
        await interaction.followup.send(content=content, embed=embed)
    
    @app_commands.command(
        name="trigger", description="Trigger an error to test ErrorHandler"
    )
    @app_commands.dm_only()
    async def trigger(self, interaction: discord.Interaction):
        if interaction.user.id not in ALLOWED_ID:
            await interaction.response.send_message("Not for you!", ephemeral=True)
            return
        try:
            1 / 0
        except Exception as e:
            ErrorHandler().handle(e, context="Embed Trigger Error")
            await interaction.response.send_message("Triggered error for testing.", ephemeral=True)


async def setup(client):
    
    await client.add_cog(EmbedCog(client))
