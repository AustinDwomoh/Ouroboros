# ============================================================================ #
#                                    IMPORT                                    #
# ============================================================================ #
import re, discord
from discord import app_commands, ui
from discord.ext import commands
from settings import ErrorHandler
from dbmanager import Games 
from constants import gameType


# ============================================================================ #
#                             UI BUTTONS FOR START                             #
# ============================================================================ #
class OpponentAcceptView(ui.View):
    """Creates a veiw for the opponent to accept the invite
    """
    def __init__(self, ctx, opponent, game_view):
        super().__init__(timeout=30)
        self.ctx = ctx
        self.opponent = opponent
        self.game_view = game_view

    @ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept_button(
        self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user == self.opponent:
            await interaction.response.send_message(
                f"{self.opponent.mention} has accepted the challenge!", ephemeral=False
            )
            round_start_message = await interaction.channel.send(
                f"5 rounds between {interaction.user.mention} and {self.opponent.mention}."
            )

            # Sends the first round message
            first_round_message = await interaction.channel.send(
                f"Round 1: {interaction.user.mention}, click a button to make your choice.",
                view=self.game_view,
            )

            self.stop()  # Stop this view after acceptance
        else:
            await interaction.response.send_message(
                f"You are not the opponent!", ephemeral=True
            )

    @ui.button(label="Decline", style=discord.ButtonStyle.danger)
    async def decline_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user == self.opponent:
            await interaction.response.send_message(
                f"{self.opponent.mention} declined the challenge.", ephemeral=False
            )
            self.stop()  # Stop this view after decline
        else:
            await interaction.response.send_message(
                f"You are not the opponent!", ephemeral=True
            )


# ============================================================================ #
#                           UI ELEMENT FOR GAME VIEW                           #
# ============================================================================ #
# Custom button view for selecting Rock, Paper, or Scissors
class RPSView(ui.View):
    def __init__(
        self,
        player1,
        player2,
        
    ):
        """The Game veiw

        Params:
            player1 (interaction object(user)): the user object for player one
            player2 (interaction object(user)): the user object for player one
        """
        super().__init__(timeout=30)
        self.player1 = player1
        self.player2 = player2
        self.total_rounds = 5
        self.current_round = 1
        self.player1_score = 0
        self.player2_score = 0
        self.player_choices = {
            player1.id: None,
            player2.id: None,
        }  # To store choices of both players

    async def on_timeout(self):
        """Time out check for all players, think it needs revision but has been working as needed so far
        """
        await self.player1.send(
            f"Time's up! You didn't make your choice, {self.player1.mention}."
        )
        await self.player2.send(
            f"Time's up! You didn't make your choice, {self.player2.mention}."
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.player1 or interaction.user == self.player2

    async def determine_winner(self, player1_choice, player2_choice):
        """This comapares and detemine the user choices

        Args:
            player1_choice (str): player choice
            player2_choice (str): player choice

        Returns:
            str: the winner or tie
        """
        if player1_choice == player2_choice:
            return "tie"
        elif (
            (player1_choice == "rock" and player2_choice == "scissors")
            or (player1_choice == "scissors" and player2_choice == "paper")
            or (player1_choice == "paper" and player2_choice == "rock")
        ):
            return "player1"
        else:
            return "player2"

    async def handle_round(self, interaction: discord.Interaction, player_choice):
        """This runs the rounds alternating and switching till the end it only allows the players who were assigned in the beggining to participate

        Args:
            interaction (discord.Interaction): discord object representing the intraction with the user
            player_choice (str): The choice that a player makes on h is turn
        """
        self.player_choices[interaction.user.id] = player_choice

        if all(choice is not None for choice in self.player_choices.values()):
            player1_choice = self.player_choices[self.player1.id]
            player2_choice = self.player_choices[self.player2.id]
            result = await self.determine_winner(player1_choice, player2_choice)

            if result == "player1":
                self.player1_score += 1
                await interaction.response.send_message(
                    f"Round {self.current_round}: {self.player1.mention} wins! They chose {player1_choice}, and {self.player2.mention} chose {player2_choice}."
                )
            elif result == "player2":
                self.player2_score += 1
                await interaction.response.send_message(
                    f"Round {self.current_round}: {self.player2.mention} wins! They chose {player2_choice}, and {self.player1.mention} chose {player1_choice}."
                )
            else:
                await interaction.response.send_message(
                    f"Round {self.current_round}: It's a tie! Both chose {player1_choice}."
                )

            self.current_round += 1

            if self.current_round <= self.total_rounds:
                self.player_choices = {
                    self.player1.id: None,
                    self.player2.id: None,
                }  # Reset choices for next round
                await interaction.followup.send(
                    f"Round {self.current_round}: {self.player1.mention} and {self.player2.mention}, click a button to make your choice.",
                    view=self,
                )
            else:
                # Game over - determine the winner
                if self.player1_score > self.player2_score:
                    await interaction.followup.send(
                        f"Game over! {self.player1.mention} won the game! Final score: {self.player1_score} - {self.player2_score}."
                    )
                elif self.player2_score > self.player1_score:
                    await interaction.followup.send(
                        f"Game over! {self.player2.mention} won the game! Final score: {self.player1_score} - {self.player2_score}."
                    )
                else:
                    await interaction.followup.send(
                        f"Game over! It's a tie! Final score: {self.player1_score} - {self.player2_score}."
                    )

                self.player1_score = self.player1_score * 2
                self.player2_score = self.player2_score * 2
                await Games.save_game_result(interaction.guild.id, self.player1.id, self.player1_score, gameType.PVP)
                await Games.save_game_result(interaction.guild.id, self.player2.id, self.player2_score, gameType.PVP)
                self.stop()

    # ================================ GAME BUTTON =============================== #
    @ui.button(label="Rock", style=discord.ButtonStyle.primary)
    async def rock_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.handle_round(interaction, "rock")

    @ui.button(label="Paper", style=discord.ButtonStyle.primary)
    async def paper_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.handle_round(interaction, "paper")

    @ui.button(label="Scissors", style=discord.ButtonStyle.primary)
    async def scissors_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.handle_round(interaction, "scissors")


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
                    game_view = RPSView(interaction.user, opponent)
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
