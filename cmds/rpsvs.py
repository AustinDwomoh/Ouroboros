# ============================================================================ #
#                                    IMPORT                                    #
# ============================================================================ #
import re, discord
from discord import app_commands
from discord.ext import commands
from settings import ErrorHandler
from views.RPSveiw import RPSview, OpponentAcceptView


# ============================================================================ #
#                                  RPS VS COG                                  #
# ============================================================================ #
class Rpvp(commands.Cog):
    def __init__(self, client):
        self.client = client

    # ================================ ACTIVATION ================================ #
    @app_commands.command(name="rpvp", description="tag your opponent")
    @app_commands.guild_only()
    async def rpvp(self, interaction: discord.Interaction):
        """Start the Rock, Paper, Scissors PvP game with a fixed 5 rounds."""
        await interaction.response.send_message(
            "Please tag the player who will compete against you.",ephemeral=True
        )

        def check(m):
            return m.author == interaction.user and m.channel == interaction.channel

        try:
            msg = await self.client.wait_for("message", check=check, timeout=30)
            opponent_tag = msg.content.strip()
            match = re.search(r"<@!?(\d+)>", opponent_tag)

            if match:
                opponent_id = int(
                    match.group(1)
                )  # Extract the user ID from the mention
                opponent = interaction.guild.get_member(opponent_id)
                if opponent and opponent.id != interaction.user.id:
                    # Prepare the game view and opponent accept view
                    game_view = RPSview(interaction.user, opponent)
                    accept_view = OpponentAcceptView(interaction, opponent, game_view)
                    await interaction.followup.send(
                        f"{opponent.mention}, do you accept the challenge?",
                        view=accept_view
                    )
                else:
                    await interaction.followup.send(
                        "You need to tag a valid opponent who is not yourself.",ephemeral=True
                    )
            else:
                await interaction.followup.send(
                    "Please tag a valid player using the correct mention format.",ephemeral=True
                )
        except Exception as e:
            errorHandler = ErrorHandler()
            embed = errorHandler.help_embed()
            errorHandler.handle(e, context="rpvp command")
            await interaction.response.send_message(embed=embed)


# ============================================================================ #
#                                     SETUP                                    #
# ============================================================================ #
async def setup(client):
    await client.add_cog(Rpvp(client))
