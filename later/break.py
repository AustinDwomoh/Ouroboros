import random, discord
from discord import app_commands
from discord.ext import commands
from settings import ErrorHandler


error_handler = ErrorHandler()

# ============================================================================ #
#                                 BREAK COG                                   #     
# ============================================================================ #
class Break(commands.Cog):
    def __init__(self, client):
        self.client = client

    # ============================================================================ #
    #                               ACTIVATION SCRIPT                              #
    # ============================================================================ #
    #@app_commands.command(name="break", description="Take a break and get a motivational quote!")
    #@app_commands.guild_only()
    async def break_command(self, interaction: discord.Interaction):
        """
        
        """
        try:
           1/0  # Intentional error for testing
        except Exception as e:
            error_handler.handle(e, context="break_command")


async def setup(client):
    await client.add_cog(Break(client))