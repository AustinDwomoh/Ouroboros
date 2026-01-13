# ============================================================================ #
#                                    IMPORT                                    #
# ============================================================================ #
import discord
from discord import app_commands
from discord.ext import commands
from views.RPSveiw import RPSview
class RPS(commands.Cog):
    """The rock paper scussor game command

    Attributes:
        client (commands.Bot): The bot client instance.
    """
    def __init__(self, client):
        self.client = client

    # ================================ ACTIVATION ================================ #
    @app_commands.command(name="rps", description="Rock Paper Game vs Ouroboros")
    #@app_commands.dm_only()
    async def rps(self, interaction: discord.Interaction):
        """Start the Rock, Paper, Scissors game against the bot."""
        # Start
        await interaction.response.send_message(
            "Game starts now! Click a button to make your choice.",
            view=RPSview(interaction.user),ephemeral=True
        )


# ============================================================================ #
#                                     SETUP                                    #
# ============================================================================ #
async def setup(client):
    await client.add_cog(RPS(client))
