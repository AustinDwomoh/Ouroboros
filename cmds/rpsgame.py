# ============================================================================ #
#                                    IMPORT                                    #
# ============================================================================ #
import random,discord
from discord import app_commands, ui
from discord.ext import commands
from settings import ErrorHandler
from dbmanager import Games  # for database connection
from constants import gameType

# ============================================================================ #
#                                  UI ELEMENT & GAME LOGIC                     #
# ============================================================================ #
# Custom button view for Rock-Paper-Scissors
class RPSView(ui.View):
    """The game view for the Rock Paper Scissor games with another user

    Args:
        ui (_type_): Discord veiws
    """
    def __init__(self, player, bot):
        """_summary_

        Args:
            player (interaction user object): The player that initailizes the game
            bot (_type_): the bot it self
        """
        super().__init__(timeout=30)
        self.player = player
        self.bot = bot
        self.total_rounds = 5  # Fixed number of rounds
        self.current_round = 1
        self.player_score = 0
        self.bot_score = 0

    async def on_timeout(self):
        # Notify the user that the game was canceled due to timeout
        """Keeps track of the game and make sure it properly timesout
        """
        response = [
            f"Don't bother me if you ain't ready, {self.player.mention}.",
            f"Small lashings for you {self.player.mention} if you don't hurry up!",
        ]
        await self.player.send(random.choice(response))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.player

    # ================================ GAME LOGIC ================================ #
    @staticmethod
    def rps_game(player_choice):
        """Uses the player choice as the starting line for thegame and the bot runs a random choice selection

        Args:
            player_choice (str): The choice used to initilize the game

        Returns:
            _type_: Returns the winner and their choice
        """
        bot_choice = random.choice(["rock", "paper", "scissors"])
        if player_choice == bot_choice:
            return "tie", bot_choice
        elif (
            (player_choice == "rock" and bot_choice == "scissors")
            or (player_choice == "scissors" and bot_choice == "paper")
            or (player_choice == "paper" and bot_choice == "rock")
        ):
            return "player", bot_choice
        else:
            return "bot", bot_choice

    # =============================== ROUND RESPONSE ============================== #
    async def handle_round(self, interaction: discord.Interaction, player_choice):
        """This manges the round for the games

        Args:
            interaction (discord.Interaction): _description_
            player_choice (str): Players choice
        """
        try:
            await interaction.response.defer()
            result, bot_choice = self.rps_game(player_choice)

            if result == "player":
                self.player_score += 1
                response = f"Round {self.current_round}: You win! You chose {player_choice}, I chose {bot_choice}. Nice one!"
            elif result == "bot":
                self.bot_score += 1
                response = f"Round {self.current_round}: I win! You chose {player_choice}, I chose {bot_choice}. Better luck next time, loser!"
            else:
                response = f"Round {self.current_round}: It's a tie! We both chose {bot_choice}. But I let you win!"
            self.current_round += 1

            # Update the message with scores
            if self.current_round <= self.total_rounds:
                await interaction.edit_original_response(
                    content=f"{response}\n\nCurrent Score: You {self.player_score} - {self.bot_score} Me.\nRound {self.current_round}/5: Click a button to make your choice.",
                    view=self,
                )
            else:
                # Game over - determine the winner
                if self.player_score > self.bot_score:
                    final_message = f"{response}\n\nGame over! You won the game! Final score: You {self.player_score} - {self.bot_score} Me. 🎉😎 You’re the champion, but I'm still the best! 😂"
                elif self.bot_score > self.player_score:
                    final_message = f"{response}\n\nGame over! I won the game! Final score: You {self.player_score} - {self.bot_score} Me. 🤖💥 Ha! I knew you were no match for me!"
                else:
                    final_message = f"{response}\n\nGame over! It's a tie! Final score: You {self.player_score} - {self.bot_score} Me. 🤷‍♂️ Not bad, but you can't beat a bot like me!"
                await interaction.edit_original_response(content=final_message)
                self.stop()
                if not isinstance(interaction.channel, discord.DMChannel):
                    #if it is a dm we dont store it
                    await Games.save_game_result(
                        interaction.guild.id, interaction.user.id, self.player_score, gameType.pvb
                    )
        except Exception as e:
            errorHandler = ErrorHandler()
            embed = errorHandler.help_embed()
            errorHandler.handle(e,context='RPS game round interaction')
            await interaction.response.send_message(embed=embed)

    # ================================ UI BUTTONS ================================ #
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
            view=RPSView(interaction.user, self.client),
        )


# ============================================================================ #
#                                     SETUP                                    #
# ============================================================================ #
async def setup(client):
    await client.add_cog(RPS(client))
