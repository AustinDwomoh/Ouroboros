import random, discord
from discord import app_commands
from discord.ext import commands
from settings import ErrorHandler


error_handler = ErrorHandler()

# ============================================================================ #
#                                 BREAK COG                                   #     
# ============================================================================ #
class Break(commands.Cog):
    """
    A Discord bot cog that allows users to take a break from interactions.
    Users can invoke the /break command to receive a random motivational quote
    and a reminder to relax.

    Attributes:
        client (commands.Bot): The bot client instance.
    """

    def __init__(self, client):
        self.client = client

    # ============================================================================ #
    #                               ACTIVATION SCRIPT                              #
    # ============================================================================ #
    @app_commands.command(name="break", description="Take a break and get a motivational quote!")
    @app_commands.guild_only()
    async def break_command(self, interaction: discord.Interaction):
        """
        Sends a random motivational quote to the user to encourage them to take a break.

        Args:
            interaction (discord.Interaction): The interaction context from the Discord app.

        Raises:
            Exception: Captures and logs any unexpected errors that occur during command execution.
        """
        try:
           1/0  # Intentional error for testing
        except Exception as e:
            error_handler.handle(e, context="break_command")


async def setup(client):
    await client.add_cog(Break(client))