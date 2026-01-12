# ============================================================================ #
#                                    IMPORT                                    #
# ============================================================================ #
import discord
from discord import app_commands
from discord.ext import commands
from settings import ErrorHandler
from views.CoinView import CoinFlipView


errorHandler =ErrorHandler()



# ============================================================================ #
#                                 cOINFLIP COG                                 #
# ============================================================================ #
class Coinflip(commands.Cog):
    """
    A Discord bot cog that allows users to participate in a coin flip game.
    Users can choose either "Heads" or "Tails," and the bot will simulate three coin flips.
    After the flips, it will display the outcome to determine the winner based on the majority result.

    Attributes:
        client (commands.Bot): The bot client instance.
    """
    

    def __init__(self, client):
        self.client = client

    # ============================================================================ #
    #                               ACTIVATION SCRIPT                              #
    # ============================================================================ #
    @app_commands.command(name="coinflip", description="Flip a coin!")
    @app_commands.guild_only()
    async def coinflip(self, interaction: discord.Interaction):
        """
        Flip a coin and allow users to choose heads or tails. The game allows two participants, and after three flips,
        the result will display which side won based on the majority outcome.
        Invoked only by ALLOWED_ID

        Args:
            interaction (discord.Interaction): The interaction context from the Discord app.

        Raises:
            Exception: Captures and logs any unexpected errors that occur during command execution.
        """
        try:
        
            embed = discord.Embed(
                title="Coin Flip",
                description=f"Please choose {CoinFlipView.CHOICE_1} or {CoinFlipView.CHOICE_2}:",
                color=discord.Color.green(),
            )
            await interaction.response.send_message(embed=embed, view=CoinFlipView())
        except Exception as e:
            embed = errorHandler.help_embed()
            errorHandler.handle(e, context='Coinflip command interaction')
            await interaction.response.send_message(embed=embed)

# ============================================================================ #
#                                     SETUP                                    #
# ============================================================================ #
# The required setup function for loading this command
async def setup(client):
    await client.add_cog(Coinflip(client))
