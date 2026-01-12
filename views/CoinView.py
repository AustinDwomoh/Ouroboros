import discord,random,asyncio
from discord import ButtonStyle
from discord.ui import Button,View
from settings import ErrorHandler

errorHandler =ErrorHandler()
class CoinFlipView(View):
    CHOICE_1 = "Heads"
    CHOICE_2 ="Tails"
    def __init__(self):
        super().__init__(timeout=30)
        self.user_choices = {}

    @discord.ui.button(
        label=CHOICE_1, style=ButtonStyle.blurple, custom_id=CHOICE_1.lower()
    )
    async def head_button(
        self, interaction: discord.Interaction, button: Button
    ):
        await self.handle_choice(interaction, CoinFlipView.CHOICE_1)

    @discord.ui.button(
        label=CHOICE_2, style=ButtonStyle.green, custom_id=CHOICE_2.lower()
    )
    async def tails_button(
        self, interaction: discord.Interaction, button: Button
    ):
        await self.handle_choice(interaction, CoinFlipView.CHOICE_2)

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
                result = random.choice([CoinFlipView.CHOICE_1, CoinFlipView.CHOICE_2])
                results.append(result)
                await interaction.followup.edit_message(
                    interaction.message.id,
                    content=f"Throw {i + 1}: Coin landed on **{result}**.",
                )

             # Count results
            head_count = results.count(CoinFlipView.CHOICE_1)
            tails_count = results.count(CoinFlipView.CHOICE_2)

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
           embed = errorHandler.help_embed()
           errorHandler.handle(e,context=f'Coinflip start command interaction')
           await interaction.response.send_message(embed=embed)

