# ============================================================================ #
#                                    IMPORT                                    #
# ============================================================================ #
import random, discord
from discord import app_commands, ui
from discord.ext import commands
from settings import ErrorHandler
from dbmanager import Games
from constants import gameType

GAME_RULES = {
    "even_odd": {
        "choices": ["even", "odd"],
        "resolver": lambda: "even" if random.randint(1, 10) % 2 == 0 else "odd",
    },
    "red_black": {
        "choices": ["red", "black"],
        "resolver": lambda: random.choice(["red", "black"]),
    }
}

# ============================================================================ #
#                        UI ELEMENTS FOR GAME SELECTION                        #
# ============================================================================ #
# View for selecting the game
class GameButton(ui.Button):
    def __init__(self, choice, view_reference):
        label = choice.capitalize()
        style = discord.ButtonStyle.green if choice in ["even", "red"] else discord.ButtonStyle.red

        super().__init__(label=label, style=style)
        self.choice = choice
        self.view_reference = view_reference

    async def callback(self, interaction: discord.Interaction):
        await self.view_reference.play_round(interaction, self.choice)

class GameSelectionView(ui.View):
    def __init__(self, player, bot, guild_id):
        super().__init__(timeout=30)
        self.player = player
        self.bot = bot
        self.guild_id = guild_id

    async def interaction_check(self, interaction):
        return interaction.user == self.player

    @ui.button(label="Even or Odd", style=discord.ButtonStyle.success)
    async def even_odd(self, interaction, button):
        await interaction.response.edit_message(
            content="Starting Even/Odd...check your DMs!",
            view=None
        )
        await self.player.send(
            "Lets Begin!",
            view=GameView(self.player, self.bot, "even_odd", self.guild_id)
        )

    @ui.button(label="Red or Black", style=discord.ButtonStyle.danger)
    async def red_black(self, interaction, button):
        await interaction.response.edit_message(
            content="Starting Red/Black...check your DMs!",
            view=None
        )
        await self.player.send(
            "Lets Begin!",
            view=GameView(self.player, self.bot, "red_black", self.guild_id)
        )


class GameView(ui.View):
    def __init__(self, player, bot, game_key, guild_id):
        super().__init__(timeout=30)
        self.player = player
        self.bot = bot
        self.guild_id = guild_id
        self.total_rounds = 5
        self.current_round = 1
        self.player_score = 0

        self.game_key = game_key
        self.game_config = GAME_RULES[game_key]

        # Dynamically create buttons for the game
        for choice in self.game_config["choices"]:
            self.add_item(GameButton(choice, self))

    async def on_timeout(self):
        await self.player.send("You took too long. Game cancelled.")

    async def interaction_check(self, interaction: discord.Interaction):
        return interaction.user == self.player

    async def play_round(self, interaction, player_choice):
        await interaction.response.defer()

        resolver = self.game_config["resolver"]
        result = resolver()

        if player_choice == result:
            self.player_score += 1
            msg = f"Round {self.current_round}: You chose {player_choice}, result was **{result}**. You win!"
        else:
            msg = f"Round {self.current_round}: You chose {player_choice}, result was **{result}**. You lose!"

        self.current_round += 1

        if self.current_round <= self.total_rounds:
            await interaction.edit_original_response(
                content=f"{msg}\n\nCurrent Score: **{self.player_score}**\nRound {self.current_round}/{self.total_rounds}",
                view=self
            )
        else:
            await interaction.edit_original_response(
                content=f"{msg}\n\nGame Over! Final Score: **{self.player_score}**",
                view=None
            )
            self.stop()

            final_score = self.player_score * 2

            #since the games will be initated via DM we need to save the game result here
            await Games.save_game_result(
                    self.guild_id,
                    interaction.user.id,
                    final_score,
                    gameType.sporty
                )
            

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
