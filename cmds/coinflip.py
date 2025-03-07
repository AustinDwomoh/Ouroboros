# ============================================================================ #
#                                    IMPORT                                    #
# ============================================================================ #
import random, discord, asyncio
from discord import app_commands, ButtonStyle
from discord.ext import commands
from settings import *
from discord.ui import Button, View

# ============================================================================ #
#                                LOGGING_CONFIG                                #
# ============================================================================ #



# ============================================================================ #
#                                 cOINFLIP COG                                 #
# ============================================================================ #
class Coinflip(commands.Cog):
    """
    A Discord bot cog that allows users to participate in a coin flip game.
    Users can choose either "Head" or "Tails," and the bot will simulate three coin flips.
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
            class CoinFlipView(View):
                def __init__(self):
                    super().__init__(timeout=30)
                    self.user_choices = {}

                @discord.ui.button(
                    label="Head", style=ButtonStyle.blurple, custom_id="head"
                )
                async def head_button(
                    self, interaction: discord.Interaction, button: Button
                ):
                    await self.handle_choice(interaction, "Head")

                @discord.ui.button(
                    label="Tails", style=ButtonStyle.green, custom_id="tails"
                )
                async def tails_button(
                    self, interaction: discord.Interaction, button: Button
                ):
                    await self.handle_choice(interaction, "Tails")

                async def handle_choice(
                    self, interaction: discord.Interaction, user_choice
                ):
                    # Track user choices
                    if interaction.user not in self.user_choices:
                        self.user_choices[interaction.user] = user_choice
                        await interaction.response.send_message(
                            f"{interaction.user.display_name} chose **{user_choice}**.",
                            delete_after=30,
                        )

                        # Check if we have two participants
                        if len(self.user_choices) == 2:
                            await self.start_coinflip(interaction)
                    else:
                        await interaction.response.send_message(
                            "You have already made your choice.", delete_after=30
                        )

                async def start_coinflip(self, interaction: discord.Interaction):
                    try:
                        results = []
                        for i in range(3):
                            await asyncio.sleep(1)  # Simulate loading
                            result = random.choice(["Head", "Tails"])
                            results.append(result)
                            await interaction.followup.edit_message(
                                interaction.message.id,
                                content=f"Throw {i + 1}: Coin landed on **{result}**.",
                            )

                        # Count results
                        head_count = results.count("Head")
                        tails_count = results.count("Tails")

                        # Prepare result message with participant tags
                        result_message = (
                            f"**Final Result:**\n"
                            f"**Heads: {head_count}**\n"
                            f"**Tails: {tails_count}**\n"
                        )

                        # Tag the first two participants who made the choices
                        tagged_users = ", ".join(
                            [user.mention for user in self.user_choices.keys()]
                        )
                        result_message += f"Participants: {tagged_users}"
                        await interaction.followup.send(
                            embed=discord.Embed(
                                title="Coin Flip Results",
                                description=result_message,
                                color=discord.Color.blue(),
                            )
                        )
                    except Exception as e:
                        ErrorHandler.handle_exception(e)
            embed = discord.Embed(
                title="Coin Flip",
                description="Please choose Heads or Tails:",
                color=discord.Color.green(),
            )
            await interaction.response.send_message(embed=embed, view=CoinFlipView())
        except Exception as e:
            ErrorHandler.handle_exception(e)

# ============================================================================ #
#                                     SETUP                                    #
# ============================================================================ #
# The required setup function for loading this command
async def setup(client):
    await client.add_cog(Coinflip(client))
