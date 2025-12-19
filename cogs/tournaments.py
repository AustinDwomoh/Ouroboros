# ---------------------------------------------------------------------------- #
#                                    IMPORTS                                   #
# ---------------------------------------------------------------------------- #
import discord,json,random,os,asyncio
from discord import app_commands
from discord.ext import commands, tasks
from discord import ui
from settings import ErrorHandler,ALLOWED_ID
from datetime import datetime, timedelta
from dbmanager import Games, ServerStatManager
from constants import gameType
errorHandler = ErrorHandler()

# ============================================================================ #
#                                    ISSUES                                    #
# ============================================================================ #
# multiplayer check

# ---------------------------------------------------------------------------- #
#                              JsonDATA MANAGEMENT                             #
# ---------------------------------------------------------------------------- #
DATA_DIR = "data"

os.makedirs(DATA_DIR, exist_ok=True)


def get_tournament_filename(guild_id):
    """Generate tournament data filename for specific guild."""
    return f"tournament_data_{guild_id}.json"

def load_tournament_data(guild_id):
    """Loads tournament data from a JSON file in the data directory."""
    file_path = os.path.join(DATA_DIR, get_tournament_filename(guild_id))
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            return json.load(f)
    return {"registered_players": [], "next_round_players": [], "matches": []}

def save_tournament_data(guild_id, data):
    """Saves tournament data to a JSON file in the data directory."""
    file_path = os.path.join(DATA_DIR, get_tournament_filename(guild_id))
    with open(file_path, "w") as f:
        json.dump(data, f, indent=4)


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
    """
    This veiw is responsible for ready veiw and lasts 2 mins before timing out
    """

    def __init__(self, tournament_data, fixtures_channel):
        super().__init__(timeout=120)  # 2mins to get ready
        self.tournament_data = tournament_data
        self.fixtures_channel = fixtures_channel
        self.ready_status = {}
        self.message = None
        # Initialize readiness status for all matches
        for match in self.tournament_data["matches"]:
            match_id = match["match_id"]
            self.ready_status[match_id] = {player: False for player in match["players"]}
        self.ready_button = ui.Button(label="Ready", style=discord.ButtonStyle.primary)
        self.ready_button.callback = self.record_ready
        self.add_item(self.ready_button)

    async def on_timeout(self):
        """It dissables the ready button to prevent further inputs"""
        for child in self.children:
            child.disabled = True
        await self.message.edit(view=self)

    async def record_ready(self, interaction: discord.Interaction):
        """Handles the readiness state of a player across all matches."""
        if self.ready_button.disabled:  # Buttons are disabled
            await interaction.followup.send(
                "Ready Timed Out", ephemeral=True
            )  # probably never gonna get sent
            return
        await interaction.response.defer(ephemeral=True)
        user_in_match = None

        # Find the match the player is part of
        for match in self.tournament_data["matches"]:
            if interaction.user.id in match["players"]:
                user_in_match = match
                break

        if user_in_match:
            match_id = user_in_match["match_id"]

            self.ready_status.setdefault(match_id, {})
            self.ready_status[match_id].setdefault(interaction.user.id, False)

            # Check if the player is already marked as ready
            if self.ready_status[match_id][interaction.user.id]:
                await interaction.followup.send(
                    "You are already marked as ready for this match.", ephemeral=True
                )
                return

            # Update readiness status
            self.ready_status[match_id][interaction.user.id] = True
            if "ready_players" not in user_in_match:
                user_in_match["ready_players"] = []
            if interaction.user.id not in user_in_match["ready_players"]:
                user_in_match["ready_players"].append(interaction.user.id)
            save_tournament_data(interaction.guild.id, self.tournament_data)

            await self.update_embed(interaction)
            # Notify the opponent
            opponent_id = next(
                player_id
                for player_id in user_in_match["players"]
                if player_id != interaction.user.id
            )
            opponent = await interaction.guild.fetch_member(opponent_id)
            if opponent:
                try:
                    message = await opponent.send(
                        f"Your opponent <@{interaction.user.id}> is now ready! Head to the tournament channel to chat."
                    )
                    # Wait for 300 seconds (5 minutes) and then delete the message
                    await asyncio.sleep(300)
                    if message:
                        await message.delete()
                except discord.errors.Forbidden as e:
                    await self.fixtures_channel.send(
                        f"Unable to send a DM to <@{opponent_id}>. Please ensure their DMs are open.",
                        delete_after=300,
                    )
                    errorHandler.handle(e, context="DM Error in Tournament Ready")

            await interaction.message.edit(view=self)
        else:
            await interaction.followup.send(
                "You're not part of any active match in this round.", ephemeral=True
            )

    async def update_embed(self, interaction: discord.Interaction):
        """Updates the embed to display all matches and their readiness statuses."""
        current_time = datetime.now()
        future_time = current_time + timedelta(seconds=self.timeout)
        unix_timestamp = int(future_time.timestamp())
        embed = discord.Embed(
            title="Tournament Matches",
            description=f"Time out  <t:{unix_timestamp}:R>",
            color=discord.Color.blue(),
        )
        # Iterate through all matches and build their readiness statuses
        for match in self.tournament_data["matches"]:
            match_id = match["match_id"]
            player1, player2 = match["players"]

            player1_name = f"<@{player1}>"
            player2_name = f"<@{player2}>"
            player1_status = "✅" if self.ready_status[match_id][player1] else "❌"
            player2_status = "✅" if self.ready_status[match_id][player2] else "❌"

            # Add a field for the current match
            embed.add_field(
                name=f"Match {match_id}",
                value=f"{player1_status} {player1_name} vs {player2_name} {player2_status}",
                inline=False,
            )

        # Update the message with the new embed
        if interaction:
            await interaction.message.edit(embed=embed)
        else:
            await self.fixtures_channel.send(embed=embed)


class WinLossButton(ui.Button):
    """A button to display a  win/loss and calls the record results function of results veiw."""

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
        self.on_win_callback = on_win_callback  # Pass the callback function

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id not in self.players:
            await interaction.response.send_message(
                "You're not part of this match!", ephemeral=True
            )
            return
        await self.on_win_callback(interaction, interaction.user.id, self.label)


class ResultsView(discord.ui.View):
    """A view to display the results of a match and record the results."""

    def __init__(self, players, tournament_data, result_callback, fixtures_channel):
        super().__init__(timeout=180)
        self.players = players
        self.tournament_data = tournament_data
        self.result_callback = result_callback
        self.choices = {}
        self.conflict_counter = 0  # Track conflicts
        self.message = None  # The message this view is attached to
        self.fixtures_channel = fixtures_channel
        # Add Win/Loss buttons
        self.add_item(WinLossButton("Win", players, self.record_result))
        self.add_item(WinLossButton("Lose", players, self.record_result))

    async def on_timeout(self):
        """Handle what happens when the view times out."""
        # Disable buttons
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass  # If the message is already deleted, ignore

        # Evaluate results based on current state
        if len(self.choices) == 1:
            # Only one player responded
            for player, choice in self.choices.items():
                opponent = self.get_opponent(player)
                await self.message.channel.send(
                    f"<@{player}> made a choice ({choice}), but <@{opponent}> did not respond in time. "
                    f"<@{player}> is declared the winner for being active."
                )
                await self.result_callback(self.fixtures_channel, player, opponent)
        elif len(self.choices) == 0:
            # No player responded
            await self.message.channel.send(
                "Neither player responded in time. The match is unresolved, and admin intervention may be required."
            )
            await self.result_callback(self.fixtures_channel, None, None)
        elif len(self.choices) == 2:
            # Both players responded, check for conflicts or resolve the match
            await self.resolve_choices()

        # Clean up the message
        try:
            await self.message.delete()
            await self.send_embed()

        except discord.NotFound:
            print("Message already deleted.")

    def get_opponent(self, player):
        """Get the opponent of a given player."""
        return [p for p in self.players if p != player][0]

    async def record_result(self, interaction: discord.Interaction, player_id, choice):
        """Record a player's result and check if both players have responded.Sends an embed to show choice"""
        await interaction.response.defer(ephemeral=True)
        self.choices[player_id] = choice

        # Notify the other player
        opponent = self.get_opponent(player_id)
        choices_made = len(self.choices)
        total_choices = len(self.players)
        embed = discord.Embed(title=f"**Choice:** {choice}", color=discord.Color.blue())
        embed.add_field(
            name=f"Match",
            value=f"Player <@{player_id}> has made their choice!\nChoices made: {choices_made}/{total_choices} ",
            inline=False,
        )
        if player_id == self.players[0]:
            await interaction.channel.send(
                content=f"<@{opponent}> ", embed=embed, delete_after=60
            )
        else:
            await interaction.channel.send(
                content=f"<@{opponent}> ", embed=embed, delete_after=60
            )

        # If both players have made choices, resolve the match
        if len(self.choices) == 2:
            await self.resolve_choices()

    async def resolve_choices(self):
        """Resolve the match based on player choices."""
        player1, player2 = self.players
        choice1 = self.choices.get(player1)
        choice2 = self.choices.get(player2)

        if choice1 == choice2:
            # Conflict: both players chose the same outcome
            self.conflict_counter += 1
            await self.message.channel.send(
                f"Conflict detected: both <@{player1}> and <@{player2}> chose {choice1}. "
                "Please re-confirm your choices."
            )
            self.choices.clear()  # Clear choices for re-confirmation
            if self.conflict_counter >= 3:
                # Too many conflicts, escalate to admin
                await self.message.channel.send(
                    "Too many conflicts! Match skipped. Both players Banned"
                )
                await self.result_callback(self.fixtures_channel, None, None)
        else:
            # Resolve the match based on the choices
            if choice1 == "Win" and choice2 == "Lose":
                winner, loser = player1, player2
            elif choice1 == "Lose" and choice2 == "Win":
                winner, loser = player2, player1
            await self.result_callback(self.fixtures_channel, winner, loser)

    async def send_embed(self):
        """Sends the final match results for all players at the end of the round."""
        tournament_data = load_tournament_data(self.fixtures_channel.guild.id)
        winner_str = ""
        for match in tournament_data["matches"]:
            if match["status"] == "completed" and match["results_submitted"]:
                winner = match["winner"]
                loser = match["loser"]
                winner_str += f"<@{winner}> wins against <@{loser}>\n"

        if winner_str:
            embed = discord.Embed(
                title="Tournament Results",
                description=winner_str,
                color=discord.Color.green(),
            )
            await self.fixtures_channel.send(embed=embed)


class DailyTournament(commands.Cog):
    """
    Responsible for running tournamnets in guilds
    """

    def __init__(self, client):
        self.client = client
        self.registration_timer = 5 * 60  # 1 minute for testing
        self.registered_players = []
        self.daily_tournament_loop.start()

    async def setup_guild_channel(self, guild, interaction=discord.Interaction):
        """
        Creates channels neccesary for running tournamnets, It does that only once when the command is initially invoked and
        Uses the same channels to run contnious tours

        Params:
        guild (discord.Guild): The guild to set up channels for
        """
        try:
            # Create the category
            category = await guild.create_category("🏆 Quick-Tournament")

            # Create channels within the category
            signup_channel = await category.create_text_channel("sign_up")
            fixtures_channel = await category.create_text_channel("fixtures")
            chat_channel = await category.create_text_channel("chat_channel")

            # Retrieve channel IDs
            signup_channel_id = signup_channel.id
            fixtures_channel_id = fixtures_channel.id
            chat_channel_id = chat_channel.id
            # Store the guild's channel IDs in ServerStatManager. it is stored in the serverstat.db
            ServerStatManager.set_channel_id(guild.id, "signup", signup_channel_id)
            ServerStatManager.set_channel_id(guild.id, "fixtures", fixtures_channel_id)
            ServerStatManager.set_channel_id(guild.id, "chat", chat_channel_id)
            tour_player_role = discord.utils.get(
                guild.roles, name=ServerStatManager.get_role(guild.id, "player_role")
            )
            if not tour_player_role:
                tour_player_role = await guild.create_role(
                    name=ServerStatManager.get_role(guild.id, "player_role")
                )

            tour_manager_role = discord.utils.get(
                guild.roles,
                name=ServerStatManager.get_role(guild.id, "tour_manager_role"),
            )
            if not tour_manager_role:
                tour_manager_role = await guild.create_role(
                    ServerStatManager.get_role(guild.id, "tour_manager_role")
                )
            # Set permissions for the channels
            await signup_channel.set_permissions(
                guild.default_role, read_messages=True, send_messages=False
            )
            await fixtures_channel.set_permissions(
                guild.default_role, read_messages=True, send_messages=False
            )

            await chat_channel.send(
                f"Welcome to the chat channel! You can discuss tournament matters here. Please check out <#{fixtures_channel.id}>."
            )
            await self.send_guidelines(chat_channel, interaction)
            await self.prepare_registration(signup_channel)

        except (discord.Forbidden,discord.HTTPException) as e:
            errorHandler.handle(e, context="Setup Guild Channel Error")


    async def send_guidelines(self, chat_channel, interaction):
        """
        This is the Guidelines for the tournaments, Sent at the start of each tournament

        Params:
        guielines_channel(discord.channel): A channel labelled #guidelines in the Guild tour is running
        chat_channel(discord.channel): A channel labelled #chat in the Guild tour is running
        """
        embed = discord.Embed(
            title="Tournament Guidelines",
            description=(
                "Welcome to the Tournament!\n\n"
                "Please follow these guidelines:\n"
                "1. **Sign Up**: Use the 'Sign Up' button to register for the tournament.\n"
                "2. **Match Results**: After your match, confirm your results using the buttons provided.\n"
                "3. **Conduct**: Be respectful to all players. Any misconduct may result in disqualification.\n"
                "4. **Have Fun!**: Enjoy the tournament and good luck!\n"
                "5. **Timing**: All rounds last 20 minutes.\n"
                "6. **Connectivity Issues**: Should your matches fail to connect, use the coin flip command to determine the winner for a smooth tournament.\n"
                "7. **Match Settings**: Time - 8 minutes; Condition - Excellent; No extra; straight to PKs.\n"
                "8.New quick tour every 4 hours.\n"
                f"9. Chat only in <#{chat_channel.id}> so admins can resolve any issues that arise\n"
                "10. Match starts once players are ready. If ready times out for you, thats a loss\n"
                " **Disconnection**: Goal stand in each case check the specifics below\n"
                "11. Incase of match disconnects, first half and below matcth restarts and time is set to 6 mins irrespective of the time, players may chose its upto them if an agreemnet can be made\n"
                "12. 70+ mins, If the goal differnce is just one and the leading team disconnects a coin flip will be used to determine and the best out of three gets two goals. If its the losing team the win is giving to the lead\n"
                "13. If GD is more than one the game ends with the lead winning\n"
            ),
            color=discord.Color.blue(),
        )

        role_name = ServerStatManager.get_role(chat_channel.guild.id, "player_role")
        tour_role = discord.utils.get(chat_channel.guild.roles, name=role_name)

        # Send the embed message with the buttons
        await chat_channel.send(content=f"<@&{tour_role.id}>", embed=embed)

    async def prepare_registration(self, signup_channel):
        """
        Alerts Server members to prepare for the tournamnes and sends the guidelines for the matches

        Params:
        signup_channel(discord.channel): A channel labelled #signup in the Guild tour is running
        """
        countdown_duration = 5  # timer for registration
        countdown_end_time = datetime.now() + timedelta(minutes=countdown_duration)
        current_time = datetime.now()
        future_time = current_time + timedelta(minutes=countdown_duration)
        unix_timestamp = int(future_time.timestamp())
        embed = discord.Embed(
            title="Tournament Registration",
            description=f"Prepare for the upcoming tournament registration! You have <t:{unix_timestamp}:R> minutes to get ready.",
            color=discord.Color.blue(),
        )
        role_name = ServerStatManager.get_role(signup_channel.guild.id, "player_role")
        tour_role = discord.utils.get(signup_channel.guild.roles, name=role_name)
        await signup_channel.send(
            content=f"<@&{tour_role.id}>",
            embed=embed,
            delete_after=countdown_duration * 60,
        )
        while countdown_duration > 0:
            remaining_time = countdown_end_time - datetime.now()
            await asyncio.sleep(60)
            countdown_duration -= 1
        await self.start_registration(signup_channel)

    async def start_registration(self, signup_channel):
        """
        Runs the registration for the tournamnets. All messages from this function are deleted later on

        params:
        signup_channel(discord.channel): A channel labelled #signup in the Guild tour is running

        """
        self.registered_players = []
        view = ui.View()
        signup_button = SignupButton(on_signup_callback=self.register_player)
        view.add_item(signup_button)

        current_time = datetime.now()
        future_time = current_time + timedelta(seconds=self.registration_timer)
        unix_timestamp = int(future_time.timestamp())
        embed = discord.Embed(
            title="Tournament Registration",
            description=f"Registration is open! Click the button to sign up.\nHurry up! Registration closes <t:{unix_timestamp}:R>",
            color=discord.Color.green(),
        )
        role_name = ServerStatManager.get_role(signup_channel.guild.id, "player_role")
        tour_role = discord.utils.get(signup_channel.guild.roles, name=role_name)
        msg = await signup_channel.send(
            content=f"<@&{tour_role.id}>", embed=embed, view=view
        )  # Send to the signup_channel
        await asyncio.sleep(self.registration_timer)
        await msg.delete()
        tournament_data = load_tournament_data(signup_channel.guild.id)
        registered = len(tournament_data["registered_players"])
        await signup_channel.send(
            f"Registration has ended! Processing {registered} entries...",
            delete_after=60,
        )
        await self.end_registration(signup_channel)

    async def register_player(self, interaction: discord.Interaction):
        """
        Adds players to the temp json file created for the match, Assigns the roles to registered players
        """
        tournament_data = load_tournament_data(interaction.guild.id)
        if interaction.user.id not in tournament_data["registered_players"]:
            # Create Tour_Player role if it doesn't exist
            tour_player_role = discord.utils.get(
                interaction.guild.roles,
                name=ServerStatManager.get_role(interaction.guild.id, "player_role"),
            )
            if not tour_player_role:
                tour_player_role = await interaction.guild.create_role(
                    name=ServerStatManager.get_role(interaction.guild.id, "player_role")
                )
            chat_channel_id = ServerStatManager.get_tour_channel_ids(
                interaction.guild_id
            )["chat"]
            chat_channel = interaction.guild.get_channel(chat_channel_id)
            if chat_channel is not None:  # to avaiod crash
                await chat_channel.set_permissions(tour_player_role, send_messages=True)

            # Add role to player
            await interaction.user.add_roles(tour_player_role)
            tournament_data["registered_players"].append(interaction.user.id)
            save_tournament_data(interaction.guild.id, tournament_data)
            await interaction.response.send_message(
                f"You've successfully registered and received the {ServerStatManager.get_role(interaction.guild.id,"player_role")} role!",
                ephemeral=True,
            )
        else:

            await interaction.response.send_message(
                "You're already registered!", ephemeral=True
            )

    async def end_registration(self, signup_channel):
        """Validates registration to determine whter to continue or to end it"""
        try:
            tournament_data = load_tournament_data(signup_channel.guild.id)
            if len(tournament_data["registered_players"]) < 2:
                current_time = datetime.now()
                future_time = current_time + timedelta(hours=4)
                unix_timestamp = int(future_time.timestamp())
                embed = discord.Embed(
                    title="Next Tournament",
                    description=f"Watch Out for the next round <t:{unix_timestamp}:R>.",
                    color=discord.Color.blue(),
                )
                await signup_channel.send(embed=embed)

                for player_id in tournament_data["registered_players"]:
                    player = signup_channel.guild.get_member(player_id)
                    if player:
                        await self.remove_role(player)
                tournament_data["registered_players"] = {}
                save_tournament_data(signup_channel.guild.id, tournament_data)
                try:
                    os.remove(
                        os.path.join(
                            DATA_DIR, get_tournament_filename(signup_channel.guild.id)
                        )
                    )
                except FileNotFoundError:
                    pass  # File already doesn't exist
            else:
                chat_channel_id = ServerStatManager.get_tour_channel_ids(
                    signup_channel.guild.id
                )["chat"]
                chat_channel = signup_channel.guild.get_channel(chat_channel_id)
                embed = discord.Embed(
                    title="Match Conditions",
                    description=f"Conditions:Excellent\n"
                    f"Time:8 mins\n"
                    f"Penalty: On\n"
                    f"Extras: off\n",
                    color=discord.Color.blue(),
                )
                await chat_channel.send(embed=embed)
                await self.run_round(signup_channel)
        except Exception as e:
            errorHandler.handle(e, context="End Registration Error")

    async def run_round(self, signup_channel):
        """Creates fixtures and sends fixtures and handles unmantched players as well the fixtures get sent to the fixtures channel"""
        try:
            fixtures_channel_id = ServerStatManager.get_tour_channel_ids(
                signup_channel.guild.id
            )["fixtures"]
            fixtures_channel = signup_channel.guild.get_channel(fixtures_channel_id)
            await fixtures_channel.send("🏆 **New Tournament Round Starting!**")

            tournament_data = load_tournament_data(signup_channel.guild.id)
            players_with_pass = []

            # Clear previous round's matches
            tournament_data["matches"] = []

            # Shuffle players for random matchups
            random.shuffle(tournament_data["registered_players"])

            while len(tournament_data["registered_players"]) >= 2:
                players_in_match = tournament_data["registered_players"][-2:]
                match_id = len(tournament_data["matches"]) + 1
                tournament_data["registered_players"] = tournament_data[
                    "registered_players"
                ][
                    :-2
                ]  # remove matched players

                match_data = {
                    "match_id": match_id,
                    "players": players_in_match,
                    "status": "waiting",
                    "guild_id": signup_channel.guild.id,
                    "ready_players": [],
                    "results_submitted": False,
                    "winner": None,
                    "loser": None,
                }

                tournament_data["matches"].append(match_data)
            try:
                match_view = MatchView(tournament_data, fixtures_channel)
                role_name = ServerStatManager.get_role(
                    fixtures_channel.guild.id, "player_role"
                )
                tour_role = discord.utils.get(
                    fixtures_channel.guild.roles, name=role_name
                )
                message = await fixtures_channel.send(
                    content=f"<@&{tour_role.id}>", view=match_view
                )
                match_view.message = message
                await asyncio.sleep(match_view.timeout)
            except Exception as e:
                errorHandler.handle(e, context="Match View Error")

            # Handle players who couldn't be paired
            if len(tournament_data["registered_players"]) > 0:
                for player_id in tournament_data["registered_players"]:
                    players_with_pass.append(player_id)
                    await fixtures_channel.send(
                        f"<@{player_id}> has received a pass to the next round!"
                    )

                # Extend with players who get a pass
                if players_with_pass:
                    tournament_data["next_round_players"].extend(players_with_pass)

            # Save updated tournament data
            save_tournament_data(signup_channel.guild.id, tournament_data)
            await self.wait_for_all_matches(fixtures_channel)
        except Exception as e:
            print(f"An error occurred in run round: {e}")

    async def record_match_result(self, fixtures_channel, winner_id, loser_id):
        """Updates the json file with the winner and loser when called

        Params:
        winner_id (int): The id of the winner
        loser_id (int): The id of the loser
        fixtures_channel(discord.channel): The fixtures channels id

        """

        tournament_data = load_tournament_data(fixtures_channel.guild.id)

        # Find and update the match status
        for match in tournament_data["matches"]:
            if winner_id in match["players"]:
                if (
                    match["status"] in ["waiting", "ready"]
                    and not match["results_submitted"]
                ):
                    match["status"] = "completed"
                    match["winner"] = winner_id
                    match["loser"] = loser_id
                    match["results_submitted"] = True
                    # Add winner to next round if not already there
                    if winner_id not in tournament_data["next_round_players"]:
                        tournament_data["next_round_players"].append(winner_id)

                guild_id = match.get("guild_id")
                save_tournament_data(guild_id, tournament_data)

                if guild_id:
                    Games.save_game_result(guild_id, winner_id, 3, gameType.efootball)
                    Games.save_game_result(guild_id, loser_id, 0, gameType.efootball)
                break

    async def remove_role(self, player):
        """Removes the role from the player when player is eliminated either by losing or by timeout

        param:
        player (discord.Member): The player to remove the role from
        """
        tour_player_role = discord.utils.get(
            player.guild.roles,
            name=ServerStatManager.get_role(player.guild.id, "player_role"),
        )
        if tour_player_role:
            await player.remove_roles(tour_player_role)

    async def wait_for_all_matches(self, fixtures_channel):
        """
        Runs a loop to wait for matches to end instead of stalling the whole bot
        The updates the json with the relevant data
        """
        tournament_data = load_tournament_data(fixtures_channel.guild.id)
        for match in tournament_data["matches"]:
            if match.get("status") != "ready":
                ready_players = match.get("ready_players", [])
                match_players = match.get("players", [])
                if len(ready_players) == 0:  # No players are ready
                    match.update(
                        {
                            "status": "cancelled",
                            "results_submitted": True,
                            "winner": None,
                            "loser": None,
                        }
                    )
                    save_tournament_data(fixtures_channel.guild.id, tournament_data)
                    if (
                        len(match_players) == 2
                    ):  # Notify if there are exactly two players
                        await fixtures_channel.send(
                            f"⚠️ Match cancelled - timeout: <@{match_players[0]}> vs <@{match_players[1]}>",
                            delete_after=30,
                        )
                elif len(ready_players) == len(match_players):  # All players are ready
                    match["status"] = "ready"
                    save_tournament_data(
                        fixtures_channel.guild.id, tournament_data
                    )  # feeling paranoid
                elif len(ready_players) == 1:
                    winner_id = ready_players[0]
                    loser_id = next((p for p in match_players if p != winner_id), None)
                    await self.record_match_result(
                        fixtures_channel, winner_id, loser_id
                    )
                    await fixtures_channel.send(
                        f"⏰ Match timed out: <@{winner_id}> wins by default over <@{loser_id}>",
                        delete_after=60,
                    )
        await self.start_results_delay(fixtures_channel)

    async def prepare_next_round(self, fixtures_channel):
        """#Prepares for the next round by updating player lists and removing roles from eliminated players."""
        if fixtures_channel:
            try:

                tournament_data = load_tournament_data(fixtures_channel.guild.id)
                if tournament_data["next_round_players"]:
                    tournament_data["registered_players"] = tournament_data[
                        "next_round_players"
                    ][:]
                    tournament_data["next_round_players"] = []
                    save_tournament_data(fixtures_channel.guild.id, tournament_data)

                # If more than one player remains, start the next round
                if len(tournament_data["registered_players"]) > 1:
                    await asyncio.sleep(60)
                    await self.run_round(fixtures_channel)
                elif len(tournament_data["registered_players"]) == 1:
                    await self.declare_winner(fixtures_channel)

            except Exception as e:
                errorHandler.handle(e, context="Prepare Next Round Error")

            except FileNotFoundError:
                pass

    async def start_results_delay(self, fixtures_channel):
        """Starts the delay for displaying results. Handles and record all match results"""
        try:
            current_time = datetime.now()
            future_time = current_time + timedelta(minutes=20)
            unix_timestamp = int(future_time.timestamp())

            # Create the embed with the timeout information
            embed = discord.Embed(
                title="Tournament Matches",
                description=f"results submission <t:{unix_timestamp}:R>",
                color=discord.Color.blue(),
            )
            # Send the embed with the timeout message
            await fixtures_channel.send(embed=embed)
            countdown_duration = 20  # Timer for registration (in minutes)
            countdown_end_time = datetime.now() + timedelta(minutes=countdown_duration)
            while datetime.now() < countdown_end_time:
                remaining_time = countdown_end_time - datetime.now()
                await asyncio.sleep(60)

            tournament_data = load_tournament_data(fixtures_channel.guild.id)
            # Send results view for all matches marked as ready
            unresolved_matches = [
                match
                for match in tournament_data["matches"]
                if match.get("status") == "ready"
            ]
            for match in unresolved_matches:
                players = match["players"]
                if match.get("status") == "ready":
                    try:
                        results_view = ResultsView(
                            players,
                            tournament_data,
                            self.record_match_result,
                            fixtures_channel,
                        )
                        if fixtures_channel is None or not isinstance(
                            fixtures_channel, discord.TextChannel
                        ):
                            continue
                        current_time = datetime.now()
                        future_time = current_time + timedelta(
                            seconds=results_view.timeout
                        )
                        unix_timestamp = int(future_time.timestamp())

                        # Create the embed with the timeout information
                        embed = discord.Embed(
                            title="Tournament Matches",
                            description=f"Time out <t:{unix_timestamp}:R> ",
                            color=discord.Color.blue(),
                        )
                        # Send the embed with the timeout message
                        await fixtures_channel.send(embed=embed)

                        results_view.message = await fixtures_channel.send(
                            f"Confirm your match result:\n<@{players[0]}> vs <@{players[1]}> ",
                            view=results_view,
                        )
                        await asyncio.sleep(results_view.timeout)
                    except Exception as e:
                        print(f"Error sending match result message: {e}")
            await self.prepare_next_round(fixtures_channel)

        except Exception as e:
            errorHandler.handle(e, context="Start Results Delay Error")

    async def declare_winner(self, fixtures_channel):
        tournament_data = load_tournament_data(fixtures_channel.guild.id)
        final_winner_id = tournament_data["registered_players"][0]
        final_winner = fixtures_channel.guild.get_member(final_winner_id)
        champ_role = discord.utils.get(
            fixtures_channel.guild.roles,
            name=ServerStatManager.get_role(fixtures_channel.guild.id, "winner_role"),
        )
        if not champ_role:
            champ_role = await fixtures_channel.guild.create_role(
                name=ServerStatManager.get_role(
                    fixtures_channel.guild.id, "winner_role"
                )
            )
        Games.save_game_result(
            fixtures_channel.guild.id, final_winner_id, 10, gameType.efootball
        )
        # Remove champion role from previous champion if exists
        for member in fixtures_channel.guild.members:
            if champ_role in member.roles and member.id != final_winner_id:
                await member.remove_roles(champ_role)

        # Remove Tour_Player role from all participants
        tour_player_role = discord.utils.get(
            fixtures_channel.guild.roles,
            name=ServerStatManager.get_role(fixtures_channel.guild.id, "player_role"),
        )
        if tour_player_role:
            for member in fixtures_channel.guild.members:
                if tour_player_role in member.roles:
                    await member.remove_roles(tour_player_role)

        # Send congratulatory messages
        signup_channel_id = ServerStatManager.get_tour_channel_ids(
            fixtures_channel.guild.id
        )["signup"]
        if signup_channel_id:
            signup_channel = fixtures_channel.guild.get_channel(signup_channel_id)
            await final_winner.add_roles(champ_role)
            current_time = datetime.now()
            future_time = current_time + timedelta(hours=4)
            unix_timestamp = int(future_time.timestamp())
            embed = discord.Embed(
                title="🏆 **Tournament Complete!**",
                description=f"Congratulations to our new champion <@{final_winner_id}>!\n"
                f"They have been awarded the **{champ_role.mention}** role! 👑 and 10 extra points"
                f"Next Tour  \n<t:{unix_timestamp}:f> ",
                color=discord.Color.green(),
            )

            await signup_channel.send(
                content=f"{tour_player_role.mention}", embed=embed
            )
        try:
            os.remove(
                os.path.join(
                    DATA_DIR, get_tournament_filename(fixtures_channel.guild.id)
                )
            )
        except FileNotFoundError:
            pass

    # ============================================================================ #
    #                             TOURNAMENT ACTIVATION                            #
    # ============================================================================ #
    @app_commands.command(
        name="activate_tournament", description="Activate or deactivate the tournament."
    )
    @app_commands.guild_only()
    async def activate_tournament(self, interaction: discord.Interaction, state: str):
        """Start or stop the tournament"""
        if interaction.user.id not in ALLOWED_ID and not any(
            role.permissions.administrator
            or role.permissions.manage_roles
            or role.permissions.ban_members
            or role.permissions.kick_members
            or role.name
            == ServerStatManager.get_role(interaction.guild.id, "tour_manager_role")
            or interaction.user.id == interaction.user.guild.owner_id
            for role in interaction.user.roles
        ):
            embed = discord.Embed(
                title="Permission Denied",
                description="You are not allowed to invoke this command.",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        state = "on" if state.lower() == "on" else "off"
        interaction.guild.id = interaction.guild.id
        if state == "on":
            await interaction.response.send_message(
                "Tournament activated!", ephemeral=True
            )
            ServerStatManager.set_server_tourstate(interaction.guild.id, state)
            category = discord.utils.get(
                interaction.guild.categories, name="🏆 Quick-Tournament"
            )
            if category is None:
                await self.setup_guild_channel(interaction.guild)
            else:
                await interaction.followup.send(
                    "Tournament channels already exist.", ephemeral=True
                )
        else:
            await interaction.response.send_message(
                "Tournament deactivated and channels cleaned up.", ephemeral=True
            )
            ServerStatManager.set_server_tourstate(interaction.guild.id, state)
            ServerStatManager.set_channel_id(interaction.guild.id, "signup", "Null")
            ServerStatManager.set_channel_id(interaction.guild.id, "fixtures", "Null")
            ServerStatManager.set_channel_id(interaction.guild.id, "chat", "Null")
            tournament_file = os.path.join(
                DATA_DIR, get_tournament_filename(interaction.guild.id)
            )
            if os.path.exists(tournament_file):
                os.remove(tournament_file)
            category = discord.utils.get(
                interaction.guild.categories, name="🏆 Quick-Tournament"
            )
            if category:
                for channel in category.channels:
                    await channel.delete()
                await category.delete()
                await interaction.followup.send(
                    "Tournament channels removed.", ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "No tournament channels found to remove.", ephemeral=True
                )

    @app_commands.command(
        name="set_tour_role", description="Change the role for the tournaments"
    )
    @app_commands.guild_only()
    async def set_tour_role(
        self, interaction: discord.Interaction, new_role: str, role_type: str
    ):
        if interaction.user.id not in ALLOWED_ID and not any(
            role.permissions.administrator
            or role.permissions.manage_roles
            or role.permissions.ban_members
            or role.permissions.kick_members
            or role.name
            == ServerStatManager.get_role(interaction.guild.id, "tour_manager_role")
            or interaction.user.id == interaction.user.guild.owner_id
            for role in interaction.user.roles
        ):
            embed = discord.Embed(
                title="Permission Denied",
                description="You are not allowed to invoke this command.",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        if role_type == "player":
            ServerStatManager.set_role(interaction.guild.id, "player_role", new_role)
        elif role_type == "manager":
            ServerStatManager.set_role(
                interaction.guild.id, "tour_manager_role", new_role
            )
        else:
            ServerStatManager.set_role(interaction.guild.id, "winner_role", new_role)
        embed = discord.Embed(
            title="Role chnage success",
            description=f"Role {role_type} has been chnaged to {ServerStatManager.get_role(interaction.guild.id,"player_role")}",
            color=discord.Color.blue(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @activate_tournament.autocomplete("state")
    async def state_autocomplete(
        self, interaction: discord.Interaction, current: str = None
    ):
        # Provide autocomplete options for the "state" argument
        choices = ["on", "off"]
        return [
            app_commands.Choice(name=choice, value=choice)
            for choice in choices
            if current.lower() in choice.lower()
        ]

    @set_tour_role.autocomplete("role_type")
    async def state_autocomplete(
        self, interaction: discord.Interaction, current: str = None
    ):
        # Provide autocomplete options for the "state" argument
        choices = ["player", "manager", "winner"]
        return [
            app_commands.Choice(name=choice, value=choice)
            for choice in choices
            if current.lower() in choice.lower()
        ]

    @tasks.loop(hours=12)  # Run every 10 minutes
    async def daily_tournament_loop(self):
        try:
            for guild in self.client.guilds:
                server_stat = await ServerStatManager.get_server_stats(guild.id)
                if server_stat.get("tournament_state") != "on":
                    continue
                signup_channel_id = ServerStatManager.get_tour_channel_ids(
                    guild.id
                ).get("signup")
                signup_channel = guild.get_channel(signup_channel_id)
                if not signup_channel:
                    continue
                await self.prepare_registration(signup_channel)

        except Exception as e:
           errorHandler.handle(e, context="Daily Tournament Loop Error")
    @daily_tournament_loop.before_loop
    async def before_daily_tournament_loop(self):
        await self.client.wait_until_ready()


# ============================================================================ #
#                                SETUP FUNCTION                                #
# ============================================================================ #
async def setup(client):
    await client.add_cog(DailyTournament(client))
