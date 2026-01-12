# ============================================================================ #
#                                    IMPORT                                    #
# ============================================================================ #
import random, discord
from discord import app_commands, ui
from discord.ext import commands
from settings import ErrorHandler
from views.sportyVeiw import GameSelectionView

            

# ============================================================================ #
#                           ACTIVATION SCRIPT AND COG                          #
# ============================================================================ #
class Sporty(commands.Cog):
    def __init__(self, client):
        self.client = client

    @app_commands.command(name="sporty", description="Test Your luck")
    @app_commands.guild_only()
    async def sporty(self, interaction: discord.Interaction):
        """Start the game selection menu."""
        try:
            await interaction.response.send_message(
            "Select a game to play!",
            view=GameSelectionView(interaction.user, self.client,interaction.guild_id),ephemeral=True
        )
        except Exception as e:
            errorHandler = ErrorHandler()
            embed = errorHandler.help_embed()
            errorHandler.handle(e,context=f"Error in sporty command")
            await interaction.response.send_message(embed=embed)


# ============================================================================ #
#                                     SETUP                                    #
# ============================================================================ #
async def setup(client):
    await client.add_cog(Sporty(client))
