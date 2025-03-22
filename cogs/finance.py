from settings import ErrorHandler# for Dir
import discord, typing
from discord import app_commands
from dbmanager import FinTech
from tabulate import tabulate
from discord.ext import commands, tasks
from datetime import datetime

errorHandler = ErrorHandler()

class FinTechListPaginationView(discord.ui.View):
    """Class responsible for the pagination used in the fintech class
    """
    def __init__(self, data, sep=10, timeout=60):
        super().__init__(timeout=timeout)
        self.data = data
        self.sep = sep
        self.current_page = 1

    def create_embed(self, data, total_pages):
        """Creates an embed with a structured table layout."""

        embed = discord.Embed(
            title=f"Upcoming Page {self.current_page} / {total_pages}",
            color=discord.Color.blue(),
        )

        # **Split headers into two parts for better readability**
        headers_1 = ["No.", "Name", "Category", "Status"]
        headers_2 = ["Amount", "Due", "Paid"]

        table_data_1 = []
        table_data_2 = []

        for idx, item in enumerate(data, start=(self.current_page - 1) * self.sep + 1):
            try:
                table_data_1.append([str(idx), item[1][:15], item[2], item[4]])
                table_data_2.append([str(item[3]),"-".join(str(item[7]).split("-")[1:]), "-".join(str(item[8]).split("-")[1:])])#from YYYY-MM-DD to MM-DD
            except IndexError as e:
                errorHandler.handle_exception(e)
                continue

        table_1 = tabulate(table_data_1, headers=headers_1, tablefmt="grid")
        table_2 = tabulate(table_data_2, headers=headers_2, tablefmt="grid")
        embed.description = f"**General Info:**\n```\n{table_1}\n```\n**Payment Details:**\n```\n{table_2}\n```"
        return embed

    def get_current_page_data(self):
        """Gets the data for the current page."""
        from_item = (self.current_page - 1) * self.sep
        until_item = from_item + self.sep
        return self.data[from_item:until_item]

    def get_total_pages(self):
        """Calculates the total number of pages."""
        return (len(self.data) - 1) // self.sep + 1

    async def update_message(self, interaction: discord.Interaction):
        """Updates the message with the new page's embed."""
        total_pages = self.get_total_pages()
        page_data = self.get_current_page_data()
        embed = self.create_embed(page_data, total_pages)

        await interaction.response.edit_message(embed=embed, view=self)

    # ========================== BUTTONS ========================== #
    @discord.ui.button(label="|<", style=discord.ButtonStyle.green)
    async def first_page_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.current_page = 1
        await self.update_message(interaction)

    @discord.ui.button(label="<", style=discord.ButtonStyle.primary)
    async def prev_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if self.current_page > 1:
            self.current_page -= 1
        await self.update_message(interaction)

    @discord.ui.button(label=">", style=discord.ButtonStyle.primary)
    async def next_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if self.current_page < self.get_total_pages():
            self.current_page += 1
        await self.update_message(interaction)

    @discord.ui.button(label=">|", style=discord.ButtonStyle.green)
    async def last_page_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.current_page = self.get_total_pages()
        await self.update_message(interaction)


class Finance(commands.Cog):
    """This class contains commands that manage financial data tracking.
    
    Features:
    - /fin_list: Lists tracked financial records (DM-only).
    - /add_payment: Adds a new payment record to track (DM-only).
    - Automated payment reminders for upcoming and overdue payments.
    """
    def __init__(self, client):
        self.client = client
        self.payment_reminder_loop.start()
        super().__init__()

    async def is_dm(self, interaction: discord.Interaction) -> bool:
        """Check if the interaction is happening in a DM."""
        return isinstance(interaction.channel, discord.DMChannel)

    @app_commands.command(name="fin_list", description="list of finance tracking")
    async def fin_list(self, interaction: discord.Interaction):
        """Lists all finance tracking records for the user in a paginated view.

        Args:
            interaction (discord.Interaction)
        """
        await interaction.response.defer()
        if not await self.is_dm(interaction):
            await interaction.response.send_message("This command can only be used in DMs!", ephemeral=True)
            return
        findata = FinTech.fintech_list(interaction.user.id)
        finPaginationView = FinTechListPaginationView(findata)
        await interaction.followup.send(
            embed=finPaginationView.create_embed(finPaginationView.get_current_page_data(),finPaginationView.get_total_pages(),),view=finPaginationView,
        )
        # Fetch the message object after it is sent
        finPaginationView.message = await interaction.original_response()

    @app_commands.command( name="add_payment", description="For a new record fill everthing to avoid unexpected errors")
    @app_commands.describe(
        category="Select a category",
        amount="payment amount",
        status="Set payment status",
        frequency="Set payment frequency",
        due_date="Select due date format YYYY-MM-DD",
    )
    async def add_payment(self,interaction: discord.Interaction,name: str,amount: int,status: str='active',frequency: str=None,due_date: str=None,category:str=None
    ):
        await interaction.response.defer()
        if not await self.is_dm(interaction):
            await interaction.response.send_message(
                "This command can only be used in DMs!", ephemeral=True
            )
            return
        choices = []
        titles = FinTech.fintech_list(interaction.user.id)
        for item in titles:
            choices.append(item[1])
        if name not in choices and (category is None or due_date is None or frequency is None):
            await interaction.response.send_message(
                "New records require category, due_date, frequency", ephemeral=True
            )
            return
        FinTech.update_table(interaction.user.id, name=name, category=category, amount=amount, due_date=due_date, status=status, frequency=frequency)
        await interaction.followup.send(f"Payment {name} has been added to your watch list")

    # ============================================================================ #
    #                                   AUtocomp                                   #
    # ============================================================================ #
    @add_payment.autocomplete("name")
    async def name_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> typing.List[app_commands.Choice[str]]:
        try:
            choices = []
            titles = FinTech.fintech_list(interaction.user.id)
            for item in titles:
                choices.append(item[1])
            filtered_choices = [
                app_commands.Choice(name=choice, value=choice)
                for choice in choices
                if current.lower() in choice.lower()
            ][:25]
            return filtered_choices
        except discord.errors.NotFound as e:
            errorHandler.handle_exception(e)
            return []
        except Exception as e:
            errorHandler.handle_exception(e)
            return []
        except discord.errors.HTTPException as e:
            errorHandler.handle_exception(e)
            if "Interaction has already been acknowledged" in str(e):
                pass

    @add_payment.autocomplete("category")
    async def category_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> typing.List[app_commands.Choice[str]]:
        categories = ["Subscription", "Bill", "Loan", "Salary", "Investment"]
        return [
            app_commands.Choice(name=category, value=category)
            for category in categories
            if current.lower() in category.lower()
        ]

    # STATUS AUTOCOMPLETE
    @add_payment.autocomplete("status")
    async def status_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> typing.List[app_commands.Choice[str]]:
        statuses = ["active", "paid"]
        # overdue will be swet when the paid hasnt been fixed after at least two days of pament passing
        return [
            app_commands.Choice(name=status, value=status)
            for status in statuses
            if current.lower() in status.lower()
        ]

    @add_payment.autocomplete("frequency")
    async def frequency_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> typing.List[app_commands.Choice[str]]:
        frequencies = ["One-Time", "Monthly", "Bi-Weekly", "Weekly"]
        return [
            app_commands.Choice(name=freq, value=freq)
            for freq in frequencies
            if current.lower() in freq.lower()
        ]

    @tasks.loop(hours=168)
    async def payment_reminder_loop(self):
        try:
            upcoming_payments = FinTech.check_due_dates()
            for reminder in upcoming_payments:
                user = self.client.get_user(reminder["user_id"])
                if user:
                    if reminder["status"] == "reminded":
                        print('here')
                        reminder["status"] = "overdue"
                        #set status to reminder and changes when the user calls add_payment to show payments been made
                        FinTech.update_payment_status(reminder["user_id"], reminder["name"], "overdue"
                        )
                    else:
                        FinTech.update_payment_status(reminder["user_id"], reminder["name"], "reminded")
                    unix_timestamp = int(datetime.strptime(reminder['due_date'], "%Y-%m-%d").timestamp())
                    embed = discord.Embed(
                        title=f"🔔 **Reminder:** {reminder['name']} Due on <t:{unix_timestamp}:D>",
                        description=f"**Payment Details**",
                        color=discord.Color.blue(),  # You can choose any color
                    )
                    # Add fields to the embed
                    embed.add_field(name="⚠️ Status", value=reminder["status"], inline=False)
                    
                    embed.add_field(name="💰 Amount Due",value=f"${reminder['amount']:.2f}",inline=True,)

                    embed.add_field(name="📍 Category", value=reminder["category"], inline=True)
                    
                    
                   
                    await user.send(embed=embed)

        except Exception as e:
            errorHandler.handle_exception(e)


async def setup(client):
    await client.add_cog(Finance(client))
