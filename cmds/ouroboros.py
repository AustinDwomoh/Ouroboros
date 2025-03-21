# ============================================================================ #
#                                    IMPORTS                                   #
# ============================================================================ #

import random, discord
from discord import app_commands
from discord.ext import commands

# ============================================================================ #
#                                   OUROBOROS                                  #
# ============================================================================ #
class Ouroboros(commands.Cog):
    """
    A Discord bot cog that provides users with random quotes when invoked.

    Attributes:
        client (commands.Bot): The bot client instance.
    """

    def __init__(self, client):
        self.client = client

    # ============================================================================ #
    #                               ACTIVATION SCRIPT                              #
    # ============================================================================ #
    @app_commands.command(name="ouroboros", description="Infinite Quotes")
    async def ouroboros(self, interaction: discord.Interaction):
        """
        Sends a random quote from a predefined list of quotes.

        Args:
            interaction (discord.Interaction): The interaction context from the Discord app.

        Raises:
            Exception: Captures and logs any unexpected errors that occur during command execution.
        """
        
        quotes = [
                "To see a world in a grain of sand and heaven in a wild flower Hold infinity in the palm of your hand and eternity in an hour.",
                "The greatest wealth is not in having more possessions, but in having more choices.",
                "The greatest obstacle in life is not the one that prevents us from doing what we love, but the one that prevents us from doing it with love.",
                "The only way to do great work is to love what you do.",
                "The only way to find true love is to find a person who understands your pain and can share it with you.",
                "Never mess with the internet, you can never win.",
                "What's achievable depends on the risk.",
                "Two things are infinite: the universe and human stupidity; and I'm not sure about the universe.",
                "The greatest secret of success is that people never really know what you are capable of.",
                "Ought implies can.",
                "My life of evil is nothing more than a clown show, thus I have no intention of making way for your pretense of justice.",
                "The greatest thing in life is to find that something you're willing to do, even when you don't know how to do it.",
                "The greatest thing in life is to stop questioning and start doing.",
                "<@!755872891601551511> gave me life.",
                "I am Ouroboros, the snake that eats its own tail.",
                "It is better to be a human being dissatisfied than a pig satisfied; better to be Socrates dissatisfied than a fool satisfied. And if the fool or the pig think otherwise, that is because they know only their own side of the question.",
                "Destruction is a form of creation.",
            ]
        embed = discord.Embed(
                title="OUROBOROS",
                description=random.choice(quotes),
                color=discord.Color.red(),
            )
        await interaction.response.send_message(embed=embed)


# The required setup function for loading this command
async def setup(client):
    await client.add_cog(Ouroboros(client))
