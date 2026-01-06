# ---------------------------------------------------------------------------- #
#                                    IMPORTS                                   #
# ---------------------------------------------------------------------------- #

from typing import Optional, Dict
import discord,asyncio
from discord import  app_commands
from discord.ext import commands, tasks
from discord import ui
from settings import ErrorHandler,BOT_MODE
from datetime import datetime, timedelta
from dbmanager import Games, ServerStatManager
from constants import gameType, channelType, Roles, Status
from models import Round, Match
errorHandler = ErrorHandler()





# ============================================================================ #
#                                  UI ELEMENTS                                 #
# ============================================================================ #
class SignupButton(ui.Button):
    def __init__(self, on_signup_callback):
        super().__init__(label="Sign Up", style=discord.ButtonStyle.primary)
        self.on_signup_callback = on_signup_callback

    async def callback(self, interaction: discord.Interaction):
        await self.on_signup_callback(interaction)


# ============================================================================ #
#                               MATCH MANAGEMENT                               #
# ============================================================================ #
class MatchView(ui.View):
    """View responsible for ready status, lasts 2 mins before timing out"""

    def __init__(self, current_round: Round, fixtures_channel):
        super().__init__(timeout=120 if BOT_MODE == "production" else 60)  # 2 mins to get ready
        self.current_round = current_round
        self.fixtures_channel = fixtures_channel
        self.message = None
        
        self.ready_button = ui.Button(label="Ready", style=discord.ButtonStyle.primary)
        self.ready_button.callback = self.record_ready
        self.add_item(self.ready_button)

    async def on_timeout(self):
        """Disable the ready button to prevent further inputs"""
        for child in self.children:
            child.disabled = True
        if self.message:
            await self.message.edit(view=self)

    async def record_ready(self, interaction: discord.Interaction):
        """Handle player readiness"""
        if self.ready_button.disabled:
            await interaction.response.send_message("Ready period has ended", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # Find the match the player is in
        match = self.current_round.get_match_for_player(interaction.user.id)
        
        if not match:
            await interaction.followup.send(
                "You're not registered in this tournament.", ephemeral=True
            )
            return

        # Mark player as ready
        if not match.mark_ready(interaction.user.id):
            await interaction.followup.send(
                "You are already marked as ready for this match.", ephemeral=True
            )
            return

        # Update the embed
        await self.update_embed(interaction)

        # Notify the opponent
        opponent_id = match.get_opponent(interaction.user.id)
        if opponent_id:
            opponent = await interaction.guild.fetch_member(opponent_id)
            if opponent:
                try:
                    message = await opponent.send(
                        f"Your opponent <@{interaction.user.id}> is now ready! Head to the tournament channel to chat."
                    )
                    # Delete notification after 5 minutes
                    await asyncio.sleep(300)
                    if message:
                        await message.delete()
                except discord.errors.Forbidden:
                    await self.fixtures_channel.send(
                        f"Unable to send a DM to <@{opponent_id}>. Please ensure their DMs are open.",
                        delete_after=300,
                    )
                except Exception as e:
                    errorHandler.handle(e, context="DM Error in Tournament Ready")

    async def update_embed(self, interaction: discord.Interaction = None):
        """Update the embed to display all matches and their readiness statuses"""
        current_time = datetime.now()
        future_time = current_time + timedelta(seconds=self.timeout)
        unix_timestamp = int(future_time.timestamp())
        
        embed = discord.Embed(
            title="Tournament Matches",
            description=f"Time out <t:{unix_timestamp}:R>",
            color=discord.Color.blue(),
        )

        # Display all matches
        for match in self.current_round.matches:
            player1, player2 = match.players
            player1_status = "✅" if player1 in match.ready_players else "❌"
            player2_status = "✅" if player2 in match.ready_players else "❌"

            embed.add_field(
                name=f"Match {match.match_id}",
                value=f"{player1_status} <@{player1}> vs <@{player2}> {player2_status}",
                inline=False,
            )

        # Update the message
        if interaction and interaction.message:
            await interaction.message.edit(embed=embed)
        elif self.message:
            await self.message.edit(embed=embed)


class WinLossButton(ui.Button):
    """Button to record win/loss for a match"""

    def __init__(self, label, players, on_win_callback):
        super().__init__(
            label=label,
            style=(
                discord.ButtonStyle.green
                if label == "Win"
                else discord.ButtonStyle.danger
            ),
        )
        self.players = players
        self.on_win_callback = on_win_callback

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id not in self.players:
            await interaction.response.send_message(
                "You're not part of this match!", ephemeral=True
            )
            return
        await self.on_win_callback(interaction, interaction.user.id, self.label)


class ResultsView(discord.ui.View):
    """View to record match results"""

    def __init__(self, match: Match, result_callback, fixtures_channel):
        super().__init__(timeout=180 if BOT_MODE == "production" else 60)  # 3 mins to submit results
        self.match = match
        self.result_callback = result_callback
        self.choices = {}  # {player_id: "Win" or "Lose"}
        self.conflict_counter = 0
        self.message = None
        self.fixtures_channel = fixtures_channel

        # Add Win/Loss buttons
        self.add_item(WinLossButton("Win", match.players, self.record_result))
        self.add_item(WinLossButton("Lose", match.players, self.record_result))

    async def on_timeout(self):
        """Handle timeout"""
        # Disable buttons
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass

        # Evaluate results based on current state
        if len(self.choices) == 1:
            # Only one player responded
            player_id = list(self.choices.keys())[0]
            opponent_id = self.match.get_opponent(player_id)
            choice = self.choices[player_id]
            
            await self.message.channel.send(
                f"<@{player_id}> chose {choice}, but <@{opponent_id}> did not respond. "
                f"<@{player_id}> wins by default for being active."
            )
            await self.result_callback(player_id, opponent_id)
            
        elif len(self.choices) == 0:
            # No player responded
            await self.message.channel.send(
                "Neither player responded. Match requires admin intervention."
            )
            await self.result_callback(None, None)
            
        elif len(self.choices) == 2:
            # Both players responded
            await self.resolve_choices()

        # Clean up
        try:
            await self.message.delete()
        except discord.NotFound:
            pass

    async def record_result(self, interaction: discord.Interaction, player_id: int, choice: str):
        """Record a player's choice"""
        await interaction.response.defer(ephemeral=True)
        self.choices[player_id] = choice

        opponent_id = self.match.get_opponent(player_id)
        choices_made = len(self.choices)
        total_choices = len(self.match.players)
        
        embed = discord.Embed(
            title=f"**Choice:** {choice}",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Match Update",
            value=f"<@{player_id}> has made their choice!\nChoices made: {choices_made}/{total_choices}",
            inline=False,
        )
        
        await interaction.channel.send(
            content=f"<@{opponent_id}>",
            embed=embed,
            delete_after=60
        )

        # If both players have made choices, resolve
        if len(self.choices) == 2:
            await self.resolve_choices()

    async def resolve_choices(self):
        """Resolve the match based on player choices"""
        player1, player2 = self.match.players
        choice1 = self.choices.get(player1)
        choice2 = self.choices.get(player2)

        if choice1 == choice2:
            # Conflict: both chose the same outcome
            self.conflict_counter += 1
            await self.message.channel.send(
                f"Conflict detected: both <@{player1}> and <@{player2}> chose {choice1}. "
                "Please re-confirm your choices."
            )
            self.choices.clear()
            
            if self.conflict_counter >= 3:
                await self.message.channel.send(
                    "Too many conflicts! Match cancelled. Admin intervention required."
                )
                await self.result_callback(None, None)
        else:
            # Determine winner and loser
            if choice1 == "Win" and choice2 == "Lose":
                winner, loser = player1, player2
            elif choice1 == "Lose" and choice2 == "Win":
                winner, loser = player2, player1
            else:
                # Shouldn't happen, but handle it
                return
            
            await self.result_callback(winner, loser)

    async def send_results_embed(self):
        """Send final results for the round"""
        if not self.match.results_submitted:
            return

        winner_str = f"<@{self.match.winner}> wins against <@{self.match.loser}>"
        
        embed = discord.Embed(
            title="Match Result",
            description=winner_str,
            color=discord.Color.green(),
        )
        await self.fixtures_channel.send(embed=embed)


# ============================================================================ #
#                              TOURNAMENT MANAGER                              #
# ============================================================================ #
class DailyTournament(commands.Cog):
    """Manages tournaments in guilds"""

    def __init__(self, client):
        self.client = client
        self.registration_timer = 5 * 60  if BOT_MODE == "production" else 60  # 5 minutes or 10 seconds for testing
        
        # Guild-specific tournament data
        self.tournaments: Dict[int, Round] = {}  # {guild_id: current_round}
        
        # Roles and channels per guild
        self.player_roles: Dict[int, discord.Role] = {}
        self.manager_roles: Dict[int, discord.Role] = {}
        self.winner_roles: Dict[int, discord.Role] = {}
        self.channels: Dict[int, Dict[str, discord.TextChannel]] = {}  # {guild_id: {channel_type: channel}}
        
        self.daily_tournament_loop.start()

    def get_tournament(self, guild_id: int) -> Optional[Round]:
        """Get the current tournament round for a guild"""
        return self.tournaments.get(guild_id)

    def start_tournament(self, guild_id: int) -> Round:
        """Start a new tournament for a guild"""
        tournament = Round(round_number=1)
        self.tournaments[guild_id] = tournament
        return tournament

    def get_next_round(self, guild_id: int) -> Optional[Round]:
        """Create the next round from the current round's winners"""
        current = self.tournaments.get(guild_id)
        if not current:
            return None
        
        # Get winners and players with byes
        next_players = current.get_winners() + current.next_round_players
        
        if len(next_players) <= 1:
            return None  # Tournament is over
        
        # Create next round
        next_round = Round(round_number=current.round_number + 1, players=next_players)
        self.tournaments[guild_id] = next_round
        return next_round

    def end_tournament(self, guild_id: int):
        """End the tournament for a guild"""
        if guild_id in self.tournaments:
            del self.tournaments[guild_id]

    async def setup_guild_channel(self, guild: discord.Guild):
        """Create tournament channels for a guild"""
        try:
            # Create category
            category = await guild.create_category("🏆 Quick-Tournament")

            # Create channels
            signup_channel = await category.create_text_channel("sign_up")
            fixtures_channel = await category.create_text_channel("fixtures")
            chat_channel = await category.create_text_channel("chat_channel")

            # Store channels
            self.channels[guild.id] = {
                channelType.SIGNUP: signup_channel,
                channelType.FIXTURES: fixtures_channel,
                channelType.CHAT: chat_channel,
            }

            # Save to database
            await ServerStatManager.set_channel_id(guild.id, channelType.SIGNUP, signup_channel.id)
            await ServerStatManager.set_channel_id(guild.id, channelType.FIXTURES, fixtures_channel.id)
            await ServerStatManager.set_channel_id(guild.id, channelType.CHAT, chat_channel.id)

            # Setup roles
            await self.setup_roles(guild)

            # Set permissions
            await signup_channel.set_permissions(guild.default_role, read_messages=True, send_messages=False)
            await fixtures_channel.set_permissions(guild.default_role, read_messages=True, send_messages=False)
            await chat_channel.set_permissions(guild.default_role, read_messages=True, send_messages=True)

            await chat_channel.send(
                f"Welcome to the chat channel! Check out <#{fixtures_channel.id}> for tournament updates."
            )

            await self.send_guidelines(guild.id)
            await self.prepare_registration(guild.id)

        except (discord.Forbidden, discord.HTTPException) as e:
            errorHandler.handle(e, context="Setup Guild Channel Error")

    async def setup_roles(self, guild: discord.Guild):
        """Setup tournament roles for a guild"""
        # Player role
        stored_player_role = await ServerStatManager.get_role(guild.id, Roles.PLAYER)
        player_role = discord.utils.get(guild.roles, name=stored_player_role) if stored_player_role != Roles.NONE.value else None
        
        if not player_role:
            player_role = await guild.create_role(name=Roles.PLAYER.value)
        
        self.player_roles[guild.id] = player_role

        # Manager role
        stored_manager_role = await ServerStatManager.get_role(guild.id, Roles.TOUR_MANAGER)
        manager_role = discord.utils.get(guild.roles, name=stored_manager_role) if stored_manager_role != Roles.NONE.value else None
        
        if not manager_role:
            manager_role = await guild.create_role(name=Roles.TOUR_MANAGER.value)
        
        self.manager_roles[guild.id] = manager_role

    async def send_guidelines(self, guild_id: int):
        """Send tournament guidelines"""
        channels = self.channels.get(guild_id, {})
        chat_channel = channels.get(channelType.CHAT)
        player_role = self.player_roles.get(guild_id)
        
        if not chat_channel or not player_role:
            return

        embed = discord.Embed(
            title="Tournament Guidelines",
            description=(
                "Welcome to the Tournament!\n\n"
                "**Rules:**\n"
                "1. Sign up using the button in the signup channel\n"
                "2. Confirm match results after each game\n"
                "3. Be respectful to all players\n"
                "4. All rounds last 20 minutes\n"
                "5. Match settings: Time - 8 minutes; Condition - Excellent; No extras; PKs on\n"
                "6. New tournament every 4 hours\n"
                f"7. Chat only in <#{chat_channel.id}>\n"
                "8. Match starts once both players are ready\n"
                "9. If ready times out, that's a loss\n\n"
                "**Disconnection Rules:**\n"
                "10. First half disconnects: Match restarts at 6 minutes\n"
                "11. 70+ mins, 1 goal difference, leading team disconnects: Coin flip (best of 3 = 2 goals)\n"
                "12. 70+ mins, 1 goal difference, losing team disconnects: Leading team wins\n"
                "13. Goal difference > 1: Leading team wins\n"
            ),
            color=discord.Color.blue(),
        )

        await chat_channel.send(content=f"<@&{player_role.id}>", embed=embed)

    async def prepare_registration(self, guild_id: int):
        """Start registration countdown"""
        channels = self.channels.get(guild_id, {})
        signup_channel = channels.get(channelType.SIGNUP)
        player_role = self.player_roles.get(guild_id)
        
        if not signup_channel or not player_role:
            return

        countdown_duration = self.registration_timer // 60  # in minutes
        current_time = datetime.now()
        future_time = current_time + timedelta(minutes=countdown_duration)
        unix_timestamp = int(future_time.timestamp())

        embed = discord.Embed(
            title="Tournament Registration",
            description=f"Tournament registration opens <t:{unix_timestamp}:R>!",
            color=discord.Color.blue(),
        )

        await signup_channel.send(
            content=f"<@&{player_role.id}>",
            embed=embed,
            delete_after=countdown_duration * 60
        )

        await asyncio.sleep(countdown_duration * 60)
        await self.start_registration(guild_id)

    async def start_registration(self, guild_id: int):
        """Open registration for players"""
        channels = self.channels.get(guild_id, {})
        signup_channel = channels.get(channelType.SIGNUP)
        player_role = self.player_roles.get(guild_id)
        
        if not signup_channel or not player_role:
            return

        # Start new tournament
        tournament = self.start_tournament(guild_id)

        view = ui.View()
        signup_button = SignupButton(on_signup_callback=lambda i: self.register_player(i, guild_id))
        view.add_item(signup_button)

        current_time = datetime.now()
        future_time = current_time + timedelta(seconds=self.registration_timer)
        unix_timestamp = int(future_time.timestamp())

        embed = discord.Embed(
            title="Tournament Registration",
            description=f"Registration is open! Click to sign up.\nCloses <t:{unix_timestamp}:R>",
            color=discord.Color.green(),
        )

        msg = await signup_channel.send(
            content=f"<@&{player_role.id}>",
            embed=embed,
            view=view
        )

        await asyncio.sleep(self.registration_timer)
        await msg.delete()

        registered_count = len(tournament.players)
        await signup_channel.send(
            f"Registration ended! {registered_count} players registered.",
            delete_after=60
        )

        await self.end_registration(guild_id)

    async def register_player(self, interaction: discord.Interaction, guild_id: int):
        """Register a player for the tournament"""
        tournament = self.get_tournament(guild_id)
        print(tournament)
        player_role = self.player_roles.get(guild_id)
        channels = self.channels.get(guild_id, {})
        chat_channel = channels.get(channelType.CHAT)
        
        if not tournament or not player_role:
            await interaction.response.send_message(
                "Tournament is not active!", ephemeral=True
            )
            return

        if interaction.user.id in tournament.players:
            await interaction.response.send_message(
                "You're already registered!", ephemeral=True
            )
            return

        # Register player
        tournament.players.append(interaction.user.id)
        print(tournament)
        await interaction.user.add_roles(player_role)
        
        if chat_channel:
            await chat_channel.set_permissions(player_role, send_messages=True)

        await interaction.response.send_message(
            f"You've successfully registered and received the {player_role.name} role!",
            ephemeral=True
        )

    async def end_registration(self, guild_id: int):
        """End registration and start tournament or schedule next one"""
        tournament = self.get_tournament(guild_id)
        channels = self.channels.get(guild_id, {})
        signup_channel = channels.get(channelType.SIGNUP)
        player_role = self.player_roles.get(guild_id)
        
        if not tournament or not signup_channel:
            return

        if len(tournament.players) < 2:
            # Not enough players
            current_time = datetime.now()
            future_time = current_time + timedelta(hours=4)
            unix_timestamp = int(future_time.timestamp())

            embed = discord.Embed(
                title="Tournament Cancelled",
                description=f"Not enough players. Next tournament <t:{unix_timestamp}:R>",
                color=discord.Color.red(),
            )
            await signup_channel.send(embed=embed)

            # Remove roles from registered players
            if player_role:
                for player_id in tournament.players:
                    member = signup_channel.guild.get_member(player_id)
                    if member and player_role in member.roles:
                        await member.remove_roles(player_role)

            self.end_tournament(guild_id)
        else:
            # Start tournament
            chat_channel = channels.get(channelType.CHAT)
            if chat_channel:
                embed = discord.Embed(
                    title="Match Conditions",
                    description="Conditions: Excellent\nTime: 8 mins\nPenalty: On\nExtras: Off",
                    color=discord.Color.blue(),
                )
                await chat_channel.send(embed=embed)

            await self.run_round(guild_id)

    async def run_round(self, guild_id: int):
        """Run a tournament round"""
        try:
            tournament = self.get_tournament(guild_id)
            channels = self.channels.get(guild_id, {})
            fixtures_channel = channels.get(channelType.FIXTURES)
            player_role = self.player_roles.get(guild_id)
            
            if not tournament or not fixtures_channel:
                return

            await fixtures_channel.send(f"🏆 **Round {tournament.round_number} Starting!**")

            # Create matches
            bye_players = tournament.create_matches(guild_id)
            print(tournament)
            # Announce byes
            for player_id in bye_players:
                await fixtures_channel.send(
                    f"<@{player_id}> has received a bye to the next round!"
                )

            # Display matches with ready view
            if tournament.matches:
                match_view = MatchView(tournament, fixtures_channel)
                await match_view.update_embed()
                
                message = await fixtures_channel.send(
                    content=f"<@&{player_role.id}>",
                    view=match_view
                )
                match_view.message = message

                # Wait for ready timeout
                await asyncio.sleep(match_view.timeout)

            # Process ready statuses
            await self.process_ready_statuses(guild_id)

        except Exception as e:
            errorHandler.handle(e, context="Run Round Error")

    async def process_ready_statuses(self, guild_id: int):
        """Process which matches are ready and handle timeouts"""
        tournament = self.get_tournament(guild_id)
        channels = self.channels.get(guild_id, {})
        fixtures_channel = channels.get(channelType.FIXTURES)
        
        if not tournament or not fixtures_channel:
            return

        for match in tournament.matches:
            if len(match.ready_players) == 0:
                # No players ready - cancel match
                match.status = Status.CANCELLED
                match.results_submitted = True
                await fixtures_channel.send(
                    f"⚠️ Match {match.match_id} cancelled - timeout: "
                    f"<@{match.players[0]}> vs <@{match.players[1]}>",
                    delete_after=30
                )
                
            elif len(match.ready_players) == 1:
                # One player ready - they win
                winner_id = match.ready_players[0]
                loser_id = match.get_opponent(winner_id)
                match.record_result(winner_id, loser_id)
                
                await fixtures_channel.send(
                    f"⏰ Match {match.match_id} timed out: "
                    f"<@{winner_id}> wins by default over <@{loser_id}>",
                    delete_after=60
                )
                
                # Save to database
                await Games.save_game_result(guild_id, winner_id, 3, gameType.EFOOTBALL)
                await Games.save_game_result(guild_id, loser_id, 0, gameType.EFOOTBALL)
                
            elif match.is_ready():
                # Both players ready - match proceeds
                match.status = Status.READY

        # Start results collection for ready matches
        await self.start_results_collection(guild_id)

    async def start_results_collection(self, guild_id: int):
        """Collect results from all ready matches"""
        tournament = self.get_tournament(guild_id)
        channels = self.channels.get(guild_id, {})
        fixtures_channel = channels.get(channelType.FIXTURES)
        
        if not tournament or not fixtures_channel:
            return

        # Get all ready matches
        ready_matches = [m for m in tournament.matches if m.status == Status.READY]
        
        if not ready_matches:
            # No matches to collect results for
            await self.prepare_next_round(guild_id)
            return

        # Announce results collection period
        countdown_duration = 20 if BOT_MODE == "production" else 1 # minutes
        current_time = datetime.now()
        future_time = current_time + timedelta(minutes=countdown_duration)
        unix_timestamp = int(future_time.timestamp())

        embed = discord.Embed(
            title="Match Results",
            description=f"Submit your results! Deadline <t:{unix_timestamp}:R>",
            color=discord.Color.blue(),
        )
        await fixtures_channel.send(embed=embed)

        # Create result views for each ready match
        result_views = []
        for match in ready_matches:
            results_view = ResultsView(
                match,
                lambda w, l, m=match: self.record_match_result(guild_id, m, w, l),
                fixtures_channel
            )
            
            timeout_timestamp = int((datetime.now() + timedelta(seconds=results_view.timeout)).timestamp())
            embed = discord.Embed(
                title=f"Match {match.match_id} Results",
                description=f"Confirm your result! Timeout <t:{timeout_timestamp}:R>",
                color=discord.Color.blue(),
            )
            
            message = await fixtures_channel.send(
                f"<@{match.players[0]}> vs <@{match.players[1]}>",
                embed=embed,
                view=results_view
            )
            results_view.message = message
            result_views.append(results_view)

        # Wait for all results views to timeout
        await asyncio.sleep(countdown_duration * 60)

        # Prepare next round
        await self.prepare_next_round(guild_id)

    async def record_match_result(self, guild_id: int, match: Match, winner_id: Optional[int], loser_id: Optional[int]):
        """Record a match result"""
        if winner_id and loser_id:
            match.record_result(winner_id, loser_id)
            
            # Save to database
            await Games.save_game_result(guild_id, winner_id, 3, gameType.EFOOTBALL)
            await Games.save_game_result(guild_id, loser_id, 0, gameType.EFOOTBALL)
        else:
            # No winner determined - mark as cancelled
            match.status = Status.CANCELLED
            match.results_submitted = True

    async def prepare_next_round(self, guild_id: int):
        """Prepare for the next round or declare winner"""
        try:
            tournament = self.get_tournament(guild_id)
            channels = self.channels.get(guild_id, {})
            fixtures_channel = channels.get(channelType.FIXTURES)
            
            if not tournament or not fixtures_channel:
                return

            # Get winners from this round
            winners = tournament.get_winners()
            next_players = winners + tournament.next_round_players

            if len(next_players) > 1:
                # More rounds needed
                await asyncio.sleep(60)
                next_round = self.get_next_round(guild_id)
                if next_round:
                    await self.run_round(guild_id)
            elif len(next_players) == 1:
                # We have a winner!
                await self.declare_winner(guild_id, next_players[0])
            else:
                # No winner (all matches cancelled/unresolved)
                await fixtures_channel.send("Tournament ended without a winner. Admin intervention required.")
                await self.cleanup_tournament(guild_id)

        except Exception as e:
            errorHandler.handle(e, context="Prepare Next Round Error")

    async def declare_winner(self, guild_id: int, winner_id: int):
        """Declare the tournament winner"""
        channels = self.channels.get(guild_id, {})
        signup_channel = channels.get(channelType.SIGNUP)
        player_role = self.player_roles.get(guild_id)
        guild = self.client.get_guild(guild_id)
        
        if not guild or not signup_channel:
            return

        final_winner = guild.get_member(winner_id)
        if not final_winner:
            return

        # Get or create winner role
        winner_role_name = await ServerStatManager.get_role(guild_id, Roles.WINNER)
        winner_role = discord.utils.get(guild.roles, name=winner_role_name)
        
        if not winner_role:
            winner_role = await guild.create_role(name=Roles.WINNER.value)

        # Save winner points
        await Games.save_game_result(guild_id, winner_id, 10, gameType.EFOOTBALL)

        # Remove champion role from previous champion
        for member in guild.members:
            if winner_role in member.roles and member.id != winner_id:
                await member.remove_roles(winner_role)

        # Add champion role to winner
        await final_winner.add_roles(winner_role)

        # Remove player role from all participants
        if player_role:
            for member in guild.members:
                if player_role in member.roles:
                    await member.remove_roles(player_role)

        # Announce winner
        current_time = datetime.now()
        future_time = current_time + timedelta(hours=4)
        unix_timestamp = int(future_time.timestamp())

        embed = discord.Embed(
            title="🏆 **Tournament Complete!**",
            description=(
                f"Congratulations to our new champion <@{winner_id}>!\n"
                f"They have been awarded the **{winner_role.mention}** role! 👑 and 10 bonus points\n\n"
                f"Next Tournament: <t:{unix_timestamp}:f>"
            ),
            color=discord.Color.gold(),
        )

        await signup_channel.send(
            content=f"<@&{player_role.id}>" if player_role else "",
            embed=embed
        )

        # Cleanup tournament
        await self.cleanup_tournament(guild_id)

    async def cleanup_tournament(self, guild_id: int):
        """Clean up tournament data"""
        self.end_tournament(guild_id)

    # ============================================================================ #
    #                             TOURNAMENT COMMANDS                              #
    # ============================================================================ #
    @app_commands.command(
        name="activate_tournament",
        description="Activate or deactivate the tournament system"
    )
    @app_commands.describe(state='Turn tournament "on" or "off"')
    @app_commands.guild_only()
    async def activate_tournament(self, interaction: discord.Interaction, state: str):
        """Activate or deactivate tournament system"""
        req_role = await ServerStatManager.get_role(interaction.guild.id, Roles.TOUR_MANAGER)
        
        if not Roles.check_role_permission(interaction.user, req_role):
            embed = discord.Embed(
                title="Permission Denied",
                description="You don't have permission to use this command.",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        state = "on" if state.lower() == "on" else "off"

        if state == "on":
            await ServerStatManager.set_server_tourstate(interaction.guild.id, state)
            category = discord.utils.get(interaction.guild.categories, name="🏆 Quick-Tournament")

            if category is None:
                await interaction.response.send_message("Activating tournament...", ephemeral=True)
                await self.setup_guild_channel(interaction.guild)
            else:
                await interaction.response.send_message(
                    "Tournament channels already exist.", ephemeral=True
                )
        else:
            await interaction.response.send_message(
                "Deactivating tournament and cleaning up...", ephemeral=True
            )
            await ServerStatManager.set_server_tourstate(interaction.guild.id, state)
            await ServerStatManager.set_channel_id(interaction.guild.id, channelType.SIGNUP, None)
            await ServerStatManager.set_channel_id(interaction.guild.id, channelType.FIXTURES, None)
            await ServerStatManager.set_channel_id(interaction.guild.id, channelType.CHAT, None)

            # Remove tournament data
            self.end_tournament(interaction.guild.id)
            if interaction.guild.id in self.channels:
                del self.channels[interaction.guild.id]

            # Delete channels
            category = discord.utils.get(interaction.guild.categories, name="🏆 Quick-Tournament")
            if category:
                for channel in category.channels:
                    await channel.delete()
                await category.delete()
                await interaction.followup.send("Tournament channels removed.", ephemeral=True)
            else:
                await interaction.followup.send("No tournament channels found.", ephemeral=True)

    @app_commands.command(
        name="set_tour_role",
        description="Change the role for tournaments"
    )
    @app_commands.guild_only()
    async def set_tour_role(
        self,
        interaction: discord.Interaction,
        new_role: str,
        role_type: str
    ):
        """Change tournament role"""
        req_role = await ServerStatManager.get_role(interaction.guild.id, Roles.TOUR_MANAGER)

        if not Roles.check_role_permission(interaction.user, req_role):
            embed = discord.Embed(
                title="Permission Denied",
                description="You don't have permission to use this command.",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        role_type = role_type.lower()
        role_enum = Roles.find_role(role_type)
        
        if role_enum is None:
            embed = discord.Embed(
                title="Invalid Role Type",
                description="Please specify: player, tour_manager, or winner.",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await ServerStatManager.set_role(interaction.guild.id, role_enum, new_role)

        embed = discord.Embed(
            title="Role Updated",
            description=f"Role {role_type} has been changed to @{new_role}",
            color=discord.Color.blue(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @activate_tournament.autocomplete("state")
    async def state_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str = ""
    ):
        """Autocomplete for state parameter"""
        choices = ["on", "off"]
        return [
            app_commands.Choice(name=choice, value=choice)
            for choice in choices
            if current.lower() in choice.lower()
        ]

    @set_tour_role.autocomplete("role_type")
    async def role_type_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str = ""
    ):
        """Autocomplete for role_type parameter"""
        choices = Roles.get_roles()
        return [
            app_commands.Choice(name=choice.value, value=choice.value)
            for choice in choices
            if current.lower() in choice.value.lower()
        ]

    @tasks.loop(hours=12 if BOT_MODE == "production" else 0.1) 
    async def daily_tournament_loop(self):
        """Run tournaments automatically every 12 hours"""
        try:
            tournament_servers = await ServerStatManager.get_tournament_servers()
            for guild_id,channels in tournament_servers.items():
                guild = self.client.get_guild(guild_id)
                if not guild:
                    continue

                # Load channels for this guild if not loaded
                if guild_id not in self.channels:
                    self.channels[guild_id] = {
                        channelType.SIGNUP: guild.get_channel(channels[channelType.SIGNUP]),
                        channelType.FIXTURES: guild.get_channel(channels[channelType.FIXTURES]),
                        channelType.CHAT: guild.get_channel(channels[channelType.CHAT]),
                        
                    }

                await self.prepare_registration(guild_id)

        except Exception as e:
            errorHandler.handle(e, context="Daily Tournament Loop Error")

    @daily_tournament_loop.before_loop
    async def before_daily_tournament_loop(self):
        """Wait for bot to be ready before starting loop"""
        await self.client.wait_until_ready()


# ============================================================================ #
#                                SETUP FUNCTION                                #
# ============================================================================ #
async def setup(client):
    await client.add_cog(DailyTournament(client))