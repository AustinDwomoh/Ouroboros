# ============================================================================ #
#                                    IMPORT                                    #
# ============================================================================ #
import random, discord
from discord import app_commands, ui
from discord.ext import commands
from settings import ErrorHandler
from dbmanager import Games


# ============================================================================ #
#                        UI ELEMENTS FOR GAME SELECTION                        #
# ============================================================================ #
# View for selecting the game
class GameSelectionView(ui.View):
    def __init__(self, player, bot):
        super().__init__(timeout=30)
        self.player = player
        self.bot = bot
    
    async def on_timeout(self):
        await self.player.send("You took too long to select a game!")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.player

    @ui.button(label="Even or Odd", style=discord.ButtonStyle.success)
    async def even_odd_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.edit_message(
            content="Starting Even or Odd game...", view=None
        )
        await interaction.channel.send(
            "Game starts now! Click a button to make your choice.",
            view=EvenOddView(self.player, self.bot),
        )
        self.stop()

    @ui.button(label="Red or Black", style=discord.ButtonStyle.red)
    async def red_black_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.edit_message(
            content="Starting Red or Black game...", view=None
        )
        await interaction.channel.send(
            "Game starts now! Click a button to make your choice.",
            view=RedBlackView(self.player, self.bot),
        )
        self.stop()


# ============================================================================ #
#                         UI ELEMENT FOR EVEN ODD GAME                         #
# ============================================================================ #
class EvenOddView(ui.View):
    def __init__(self, player, bot):
        super().__init__(timeout=30)
        self.player = player
        self.bot = bot
        self.total_rounds = 5  # Fixed number of rounds
        self.current_round = 1
        self.player_score = 0

    async def on_timeout(self):
        await self.player.send("Don't bother me if you ain't ready!")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.player

    async def handle_round(self, interaction: discord.Interaction, player_choice):
        await interaction.response.defer()
        number = random.randint(1, 10)
        result = "even" if number % 2 == 0 else "odd"

        if player_choice == result:
            self.player_score += 1
            response = f"Round {self.current_round}: You chose {player_choice} and the number was {number}. You win!"
        else:
            response = f"Round {self.current_round}: You chose {player_choice} and the number was {number}. You lose!"

        self.current_round += 1

        # Update the message with scores
        if self.current_round <= self.total_rounds:
            await interaction.edit_original_response(
                content=f"{response}\n\nCurrent Score: {self.player_score}\nRound {self.current_round}/{self.total_rounds}: Click a button to make your choice.",
                view=self,
            )
        else:
            await interaction.edit_original_response(
                content=f"{response}\n\nGame over! Your final score: {self.player_score}.",
                view=None,
            )
            # Save results
            self.stop()
            self.player_score = self.player_score * 2
            if not isinstance(interaction.channel, discord.DMChannel):
                await Games.save_game_result(
                    interaction.guild.id,
                    interaction.user.id,
                    self.player_score,
                    "sporty",
                )

    @ui.button(label="Even", style=discord.ButtonStyle.success)
    async def even_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.handle_round(interaction, "even")

    @ui.button(label="Odd", style=discord.ButtonStyle.danger)
    async def odd_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.handle_round(interaction, "odd")


# ============================================================================ #
#                         UI ELEMENT FOR RED BLACK GAME                        #
# ============================================================================ #
class RedBlackView(ui.View):
    def __init__(self, player, bot):
        super().__init__(timeout=30)
        self.player = player
        self.bot = bot
        self.total_rounds = 5
        self.current_round = 1
        self.player_score = 0

    async def on_timeout(self):
        await self.player.send("Don't bother me if you ain't ready!")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.player

    async def handle_round(self, interaction: discord.Interaction, player_choice):
        await interaction.response.defer()
        result = random.choice(["red", "black"])

        if player_choice == result:
            self.player_score += 1
            response = f"Round {self.current_round}: You chose {player_choice} and the result was {result}. You win!"
        else:
            response = f"Round {self.current_round}: You chose {player_choice} and the result was {result}. You lose!"

        self.current_round += 1

        # Update the message with scores
        if self.current_round <= self.total_rounds:
            await interaction.edit_original_response(
                content=f"{response}\n\nCurrent Score: {self.player_score}\nRound {self.current_round}/{self.total_rounds}: Click a button to make your choice.",
                view=self,
            )
        else:
            await interaction.edit_original_response(
                content=f"{response}\n\nGame over! Your final score: {self.player_score}.",
                view=None,
            )
            # Save results
            self.stop()
            self.player_score = self.player_score * 2
            if not isinstance(interaction.channel, discord.DMChannel):
                await Games.save_game_result(
                    interaction.guild.id,
                    interaction.user.id,
                    self.player_score,
                    "sporty",
                )

    @ui.button(label="Red", style=discord.ButtonStyle.red)
    async def red_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.handle_round(interaction, "red")

    @ui.button(label="Black", style=discord.ButtonStyle.secondary)
    async def black_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.handle_round(interaction, "black")


# ============================================================================ #
#                           ACTIVATION SCRIPT AND COG                          #
# ============================================================================ #
class Sporty(commands.Cog):
    def __init__(self, client):
        self.client = client

    @app_commands.command(name="sporty", description="Test Your luck")
    async def sporty(self, interaction: discord.Interaction):
        """Start the game selection menu."""
        try:
            await interaction.response.send_message(
            "Select a game to play!",
            view=GameSelectionView(interaction.user, self.client),
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
