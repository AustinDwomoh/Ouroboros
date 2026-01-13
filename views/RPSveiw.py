from discord import ui
import random
import discord
from constants import gameType
from dbmanager import Games


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



import discord
from discord import ui
import random

class RPSview(ui.View):
    PLAYER1 = "player1"
    PLAYER2 = "player2"
    TIE = "tie"
    ROCK = "rock"
    PAPER = "paper"
    SCISSORS = "scissors"
    

    def __init__(self, player1, player2=None, timeout=180):
        super().__init__(timeout=timeout)
        self.player1 = player1
        self.player2 = player2  # Keep as None for bot games
        self.is_bot_game = player2 is None
        self.total_rounds = 5
        self.current_round = 1
        self.player1_score = 0
        self.player2_score = 0
        self.choices = {
            player1.id: None,
            "bot" if self.is_bot_game else player2.id: None
        }
        self.message = None  # Store the original message to edit

    async def on_timeout(self):
        """Handle view timeout - only send messages to human players."""
        response = [
            f"Don't bother me if you ain't ready, {self.player1.mention}.",
            f"Time's up! Come back when you're ready to play.",
        ]
        
        # Send to player1
        try:
            await self.player1.send(random.choice(response))
        except:
            pass  # Handle case where user has DMs disabled
        
        # Only send to player2 if it's not a bot game
        if not self.is_bot_game and self.player2:
            try:
                await self.player2.send(random.choice(response))
            except:
                pass

    def rps_game(self, player1_choice, player2_choice):
        """Determines the winner of a round based on player choices.

        Args:
            player1_choice (str): Choice of player 1.
            player2_choice (str): Choice of player 2 or bot.

        Returns:
            str: 'player1', 'player2', or 'tie' based on the outcome.
        """
        if player1_choice == player2_choice:
            return self.TIE
        elif (
            (player1_choice == self.ROCK and player2_choice == self.SCISSORS)
            or (player1_choice == self.SCISSORS and player2_choice == self.PAPER)
            or (player1_choice == self.PAPER and player2_choice == self.ROCK)
        ):
            return self.PLAYER1
        else:
            return self.PLAYER2
        
    async def handle_round(self, interaction: discord.Interaction, player_choice):
        """Manages a round of the game based on player choices.

        Args:
            interaction (discord.Interaction): The interaction object.
            player_choice (str): The choice made by the player.
        """
        # Validate that the correct player is clicking
        if self.is_bot_game:
            # In bot game, only player1 can click
            if interaction.user.id != self.player1.id:
                await interaction.response.send_message(
                    "This isn't your game!", ephemeral=True
                )
                return
        else:
            # In PvP game, only the two players can click
            if interaction.user.id not in [self.player1.id, self.player2.id]:
                await interaction.response.send_message(
                    "This isn't your game!", ephemeral=True
                )
                return
        
        # Store the player's choice
        self.choices[interaction.user.id] = player_choice
        
        # For bot games, generate bot choice immediately
        if self.is_bot_game:
            bot_choice = random.choice([self.ROCK, self.PAPER, self.SCISSORS])
            self.choices["bot"] = bot_choice
        
        # Get both choices
        player1_choice = self.choices[self.player1.id]
        player2_key = "bot" if self.is_bot_game else self.player2.id
        player2_choice = self.choices[player2_key]
        
        # In PvP mode, wait for both players to choose
        if not self.is_bot_game and (player1_choice is None or player2_choice is None):
            # Edit the message to show someone has chosen
            await interaction.response.edit_message(
                content=f"Round {self.current_round} of {self.total_rounds}\n"
                        f"Score: {self.player1.mention} {self.player1_score} - {self.player2_score} {self.player2.mention}\n"
                        f"{interaction.user.mention} has made their choice! Waiting for the other player...",
                view=self
            )
            return
        
        # Both choices are in, determine winner
        winner = self.rps_game(player1_choice, player2_choice)
        
        # Update scores and create result message
        player2_name = "Ouroboros" if self.is_bot_game else self.player2.mention
        
        if winner == self.PLAYER1:
            self.player1_score += 1
            result_message = f"{self.player1.mention} wins this round! {player1_choice} beats {player2_choice}."
        elif winner == self.PLAYER2:
            self.player2_score += 1
            result_message = f"{player2_name} wins this round! {player2_choice} beats {player1_choice}."
        else:
            result_message = f"This round is a tie! Both chose {player1_choice}."
        
        # Reset choices for next round
        self.choices[self.player1.id] = None
        self.choices[player2_key] = None
        
        # Increment round counter
        self.current_round += 1
        
        # Check if game is over
        if self.current_round > self.total_rounds:
            if self.player1_score > self.player2_score:
                final_message = f"Game over! {self.player1.mention} wins the game with a score of {self.player1_score} to {self.player2_score}!"
            elif self.player2_score > self.player1_score:
                final_message = f"Game over! {player2_name} wins the game with a score of {self.player2_score} to {self.player1_score}!"
            else:
                final_message = f"Game over! It's a tie with both players scoring {self.player1_score}!"
            
            # Edit message with final results and remove buttons
            await interaction.response.edit_message(
                content=f"{result_message}\n{final_message}",
                view=None
            )
            if self.is_bot_game:
                # Save game result for player vs bot
                await Games.save_game_result(interaction.guild.id, self.player1.id, self.player1_score, gameType.PVB)
            else:
                # Save game result for player vs player
                await Games.save_game_result(interaction.guild.id, self.player1.id, self.player1_score, gameType.PVP)
                await Games.save_game_result(interaction.guild.id, self.player2.id, self.player2_score, gameType.PVP)
        
            
            self.stop()
        else:
            # Edit message with round results and keep buttons active
            await interaction.response.edit_message(
                content=f"{result_message}\n"
                        f"Round {self.current_round} of {self.total_rounds}\n"
                        f"Score: {self.player1.mention} {self.player1_score} - {self.player2_score} {player2_name}\n"
                        f"Make your choice!",
                view=self
            )

    @ui.button(label="Rock", style=discord.ButtonStyle.primary, emoji="🪨")
    async def rock_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_round(interaction, self.ROCK)

    @ui.button(label="Paper", style=discord.ButtonStyle.primary, emoji="📄")
    async def paper_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_round(interaction, self.PAPER)
    
    @ui.button(label="Scissors", style=discord.ButtonStyle.primary, emoji="✂️")
    async def scissors_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_round(interaction, self.SCISSORS)