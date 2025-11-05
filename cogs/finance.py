from settings import ErrorHandler
import discord
import typing
from discord import app_commands
from dbmanager import FinTech
from discord.ext import commands, tasks
from datetime import datetime, timedelta

errorHandler = ErrorHandler()
#TODO: Auto Complete for names
#TODO: Redesign the pagination view to be more modern and card-based
#TODO: The date is failing on the add_payment

class FinTechPaginationView(discord.ui.View):
    """Modern pagination view for financial tracking with card-based layout."""
    
    def __init__(self, data, items_per_page=5, timeout=180):
        super().__init__(timeout=timeout)
        self.data = data
        self.items_per_page = items_per_page
        self.current_page = 1
        self.update_buttons()

    def create_embed(self):
        """Creates a modern card-based embed for financial data."""
        total_pages = self.get_total_pages()
        
        embed = discord.Embed(
            title="💰 Financial Tracker",
            description=f"*Your payment overview and upcoming bills*",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        page_data = self.get_current_page_data()
        
        if not page_data:
            embed.description = "No payments tracked yet. Use `/add_payment` to get started!"
            embed.color = discord.Color.greyple()
            return embed
        
        # Calculate summary stats
        total_amount = sum(float(item['amount']) for item in self.data)
        total_paid = sum(float(item['total_paid']) for item in self.data)
        remaining = total_amount - total_paid
        
        # Add summary header
        embed.add_field(
            name="📊 Summary",
            value=f"```\nTotal Due:  ${total_amount:,.2f}\nTotal Paid: ${total_paid:,.2f}\nRemaining:  ${remaining:,.2f}\n```",
            inline=False
        )
        
        # Add each payment as a card
        for idx, item in enumerate(page_data, start=(self.current_page - 1) * self.items_per_page + 1):
            try:
                # item structure: dict with keys (id, name, category, amount, total_paid, status, frequency, due_date, last_paid_date)
                name = item['name']
                category = item.get('category') or "Uncategorized"
                amount = float(item['amount'])
                total_paid_amount = float(item['total_paid'])
                status = item['status']
                frequency = item['frequency']
                due_date = item['due_date']
                last_paid = item.get('last_paid_date')
                
                # Status emoji mapping
                status_emoji = {
                    'pending': '⏳',
                    'paid': '✅',
                    'overdue': '🚨',
                    'cancelled': '❌',
                    'active': '🔵',
                    'reminded': '⚠️'
                }
                emoji = status_emoji.get(status.lower(), '📌')
                
                # Calculate days until due
                days_until = ""
                if due_date:
                    try:
                        due = datetime.strptime(str(due_date), "%Y-%m-%d")
                        delta = (due - datetime.now()).days
                        if delta < 0:
                            days_until = f"**{abs(delta)} days overdue**"
                        elif delta == 0:
                            days_until = "**Due today!**"
                        elif delta <= 3:
                            days_until = f"Due in {delta} days"
                        else:
                            days_until = f"Due in {delta} days"
                    except ValueError:
                        days_until = str(due_date)
                
                # Build payment card
                remaining_amount = amount - total_paid_amount
                payment_info = []
                
                if remaining_amount > 0:
                    payment_info.append(f"**Amount Due:** ${amount:,.2f}")
                    if total_paid_amount > 0:
                        payment_info.append(f"**Paid:** ${total_paid_amount:,.2f} (${remaining_amount:,.2f} left)")
                else:
                    payment_info.append(f"**Amount:** ${amount:,.2f} ✓ Paid")
                
                if frequency:
                    payment_info.append(f"**Frequency:** {frequency}")
                
                if days_until:
                    payment_info.append(f"**Due Date:** {days_until}")
                
                if last_paid:
                    try:
                        last_paid_date = datetime.strptime(str(last_paid), "%Y-%m-%d")
                        payment_info.append(f"**Last Paid:** {last_paid_date.strftime('%b %d, %Y')}")
                    except ValueError:
                        pass
                
                # Add the payment card
                field_name = f"{emoji} {idx}. {name}"
                if category != "Uncategorized":
                    field_name += f" • {category}"
                
                embed.add_field(
                    name=field_name,
                    value="\n".join(payment_info),
                    inline=False
                )
                
            except (IndexError, ValueError, TypeError) as e:
                errorHandler.handle(e, context=f"Error processing payment item: {item}")
                continue
        
        # Footer with page info
        embed.set_footer(text=f"Page {self.current_page} of {total_pages} • {len(self.data)} total payments")
        
        return embed

    def get_current_page_data(self):
        """Gets the data for the current page."""
        start_idx = (self.current_page - 1) * self.items_per_page
        end_idx = start_idx + self.items_per_page
        return self.data[start_idx:end_idx]

    def get_total_pages(self):
        """Calculates the total number of pages."""
        if not self.data:
            return 1
        return (len(self.data) - 1) // self.items_per_page + 1

    def update_buttons(self):
        """Enable/disable buttons based on current page."""
        total_pages = self.get_total_pages()
        
        self.first_page_button.disabled = self.current_page == 1
        self.prev_button.disabled = self.current_page == 1
        self.next_button.disabled = self.current_page >= total_pages
        self.last_page_button.disabled = self.current_page >= total_pages

    async def update_message(self, interaction: discord.Interaction):
        """Updates the message with the new page's embed."""
        self.update_buttons()
        embed = self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    # ========================== BUTTONS ========================== #
    @discord.ui.button(emoji="⏮️", style=discord.ButtonStyle.secondary, row=0)
    async def first_page_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Go to first page."""
        self.current_page = 1
        await self.update_message(interaction)

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.primary, row=0)
    async def prev_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Go to previous page."""
        if self.current_page > 1:
            self.current_page -= 1
        await self.update_message(interaction)

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.primary, row=0)
    async def next_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Go to next page."""
        if self.current_page < self.get_total_pages():
            self.current_page += 1
        await self.update_message(interaction)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary, row=0)
    async def last_page_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Go to last page."""
        self.current_page = self.get_total_pages()
        await self.update_message(interaction)

    @discord.ui.button(label="Refresh", emoji="🔄", style=discord.ButtonStyle.green, row=1)
    async def refresh_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Refresh the payment data."""
        # Caller should handle refreshing data
        await interaction.response.send_message(
            "♻️ Refreshing payment data...", 
            ephemeral=True, 
            delete_after=2
        )


class PaymentFilterView(discord.ui.View):
    """View for filtering payment list by status or category."""
    
    def __init__(self, user_id: int, timeout=60):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.filter_type = None
        self.filter_value = None

    @discord.ui.select(
        placeholder="Filter by status...",
        options=[
            discord.SelectOption(label="All Payments", value="all", emoji="📋"),
            discord.SelectOption(label="Pending", value="pending", emoji="⏳"),
            discord.SelectOption(label="Paid", value="paid", emoji="✅"),
            discord.SelectOption(label="Overdue", value="overdue", emoji="🚨"),
            discord.SelectOption(label="Active", value="active", emoji="🔵"),
        ],
        row=0
    )
    async def filter_status(self, interaction: discord.Interaction, select: discord.ui.Select):
        """Filter payments by status."""
        self.filter_type = "status"
        self.filter_value = select.values[0]
        
        # Fetch filtered data
        all_data = await FinTech.fintech_list(self.user_id)
        
        if self.filter_value == "all":
            filtered_data = all_data
        else:
            filtered_data = [item for item in all_data if item['status'].lower() == self.filter_value]
        
        if not filtered_data:
            await interaction.response.send_message(
                f"No payments found with status: **{self.filter_value}**",
                ephemeral=True
            )
            return
        
        # Create new pagination view with filtered data
        view = FinTechPaginationView(filtered_data)
        embed = view.create_embed()
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class Finance(commands.Cog):
    """Financial tracking and payment management system.
    
    Features:
    - Track bills, subscriptions, loans, and other payments
    - Automated payment reminders for upcoming and overdue bills
    - Detailed payment history and statistics
    - DM-only for privacy
    """
    
    def __init__(self, client):
        self.client = client
        self.payment_reminder_loop.start()
        super().__init__()

    def cog_unload(self):
        """Clean up when cog is unloaded."""
        self.payment_reminder_loop.cancel()

    async def is_dm(self, interaction: discord.Interaction) -> bool:
        """Check if the interaction is happening in a DM."""
        return isinstance(interaction.channel, discord.DMChannel)

    @app_commands.command(name="fin_list", description="View your tracked payments and bills")
    @app_commands.dm_only()
    async def fin_list(self, interaction: discord.Interaction):
        """Lists all finance tracking records for the user in a modern card-based view.

        Args:
            interaction (discord.Interaction): The interaction instance
        """
        try:
            await interaction.response.defer(thinking=True, ephemeral=True)
            
            findata = await FinTech.fintech_list(interaction.user.id)
            
            if not findata:
                embed = discord.Embed(
                    title="💰 Financial Tracker",
                    description="You haven't added any payments yet!\n\nUse `/add_payment` to start tracking your bills and subscriptions.",
                    color=discord.Color.greyple()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Create pagination view
            view = FinTechPaginationView(findata)
            embed = view.create_embed()
            
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            
        except discord.DiscordException as e:
            errorHandler.handle(e, context="Error in fin_list command.")
            await interaction.followup.send(
                "❌ An error occurred while fetching your payment list.",
                ephemeral=True
            )
        except Exception as e:
            errorHandler.handle(e, context="Unexpected error in fin_list command.")
            await interaction.followup.send(
                "❌ An unexpected error occurred.",
                ephemeral=True
            )

    @app_commands.command(
        name="add_payment",
        description="Add or update a payment record"
    )
    @app_commands.describe(
        name="Payment name (e.g., 'Netflix', 'Rent', 'Car Insurance')",
        amount="Payment amount in dollars",
        category="Payment category",
        status="Current payment status",
        frequency="How often this payment occurs",
        due_date="Next due date (YYYY-MM-DD format)"
    )
    @app_commands.dm_only()
    async def add_payment(
        self,
        interaction: discord.Interaction,
        name: str,
        amount: float,
        status: str = 'pending',
        frequency: str = None,
        due_date: str = None,
        category: str = None
    ):
        """Adds new payment or updates existing payment data.

        Args:
            interaction: Bot interaction
            name: Payment name (required)
            amount: Amount to pay (required)
            status: Payment status (default: pending)
            frequency: Payment frequency (required for new records)
            due_date: Due date in YYYY-MM-DD format (required for new records)
            category: Payment category (required for new records)
        """
        try:
            await interaction.response.defer(thinking=True, ephemeral=True)
            
            # Validate amount
            if amount <= 0:
                await interaction.followup.send(
                    "❌ Amount must be greater than 0!",
                    ephemeral=True
                )
                return
            
            # Check if payment exists
            existing_payments = await FinTech.fintech_list(interaction.user.id)
            payment_names = [item['name'] for item in existing_payments]
            is_new_payment = name not in payment_names
            
            # Validate required fields for new payments
            if is_new_payment:
                missing_fields = []
                if not category:
                    missing_fields.append("category")
                if not due_date:
                    missing_fields.append("due_date")
                if not frequency:
                    missing_fields.append("frequency")
                
                if missing_fields:
                    await interaction.followup.send(
                        f"❌ New payments require: **{', '.join(missing_fields)}**\n\n"
                        f"Please provide all required fields.",
                        ephemeral=True
                    )
                    return
                
                # Validate date format
                try:
                    datetime.strptime(due_date, "%Y-%m-%d")
                except ValueError:
                    await interaction.followup.send(
                        f"❌ Invalid date format: `{due_date}`\n\n"
                        f"Please use **YYYY-MM-DD** format (e.g., 2025-12-31)",
                        ephemeral=True
                    )
                    return
            
            # Update or insert payment
            response = await FinTech.update_payment(
                user_id=interaction.user.id,
                name=name,
                category=category,
                amount=amount,
                due_date=due_date,
                status=status,
                frequency=frequency
            )
            
            # Extract response data
            next_due_date = response.get("updated_due") or response.get("due_date")
            total_paid = response.get("new_total", 0)
            was_inserted = response.get("inserted", False)
            
            # Create success embed
            action = "Added" if was_inserted or is_new_payment else "Updated"
            embed = discord.Embed(
                title=f"✅ Payment {action}",
                description=f"**{name}** has been successfully {action.lower()}.",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            
            # Add payment details
            embed.add_field(
                name="💰 Amount",
                value=f"${amount:,.2f}",
                inline=True
            )
            
            if category:
                embed.add_field(
                    name="📍 Category",
                    value=category,
                    inline=True
                )
            
            embed.add_field(
                name="⚠️ Status",
                value=status.capitalize(),
                inline=True
            )
            
            if next_due_date:
                try:
                    due = datetime.strptime(str(next_due_date), "%Y-%m-%d")
                    unix_timestamp = int(due.timestamp())
                    embed.add_field(
                        name="📅 Next Due Date",
                        value=f"<t:{unix_timestamp}:D> (<t:{unix_timestamp}:R>)",
                        inline=False
                    )
                except (ValueError, TypeError):
                    embed.add_field(
                        name="📅 Next Due Date",
                        value=str(next_due_date),
                        inline=False
                    )
            
            # Show payment progress only for updates (not new payments)
            if not was_inserted and total_paid and total_paid > 0:
                if total_paid < amount:
                    remaining = amount - total_paid
                    embed.add_field(
                        name="💵 Payment Progress",
                        value=f"Paid: ${total_paid:,.2f} | Remaining: ${remaining:,.2f}",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="💵 Payment Status",
                        value=f"Total Paid: ${total_paid:,.2f} ✓",
                        inline=False
                    )
            
            if frequency:
                embed.add_field(
                    name="🔄 Frequency",
                    value=frequency.capitalize(),
                    inline=True
                )
            
            embed.set_footer(text="Use /fin_list to view all your payments")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except discord.DiscordException as e:
            errorHandler.handle(e, context="Error in add_payment command.")
            await interaction.followup.send(
                "❌ An error occurred while saving your payment.",
                ephemeral=True
            )
        except Exception as e:
            errorHandler.handle(e, context="Unexpected error in add_payment command.")
            await interaction.followup.send(
                "❌ An unexpected error occurred.",
                ephemeral=True
            )

    # ============================================================================ #
    #                               AUTOCOMPLETE                                    #
    # ============================================================================ #
    
    @add_payment.autocomplete("name")
    async def name_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> typing.List[app_commands.Choice[str]]:
        """Autocomplete for payment names."""
        try:
            existing_payments = await FinTech.fintech_list(interaction.user.id)
            payment_names = [item[1] for item in existing_payments]
            print(payment_names)
            # Filter based on current input
            filtered = [
                app_commands.Choice(name=name, value=name)
                for name in payment_names
                if current.lower() in name.lower()
            ][:25]
            
            return filtered
        except Exception:
            return []

    @add_payment.autocomplete("category")
    async def category_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> typing.List[app_commands.Choice[str]]:
        """Autocomplete for payment categories."""
        categories = [
            ("💳 Subscription", "Subscription"),
            ("📄 Bill", "Bill"),
            ("💰 Loan", "Loan"),
            ("💵 Salary", "Salary"),
            ("📈 Investment", "Investment"),
            ("🏠 Rent/Mortgage", "Rent/Mortgage"),
            ("🚗 Transportation", "Transportation"),
            ("🍔 Food & Dining", "Food & Dining"),
            ("🏥 Healthcare", "Healthcare"),
            ("🎓 Education", "Education"),
            ("🎮 Entertainment", "Entertainment"),
            ("📦 Other", "Other")
        ]
        
        return [
            app_commands.Choice(name=name, value=value)
            for name, value in categories
            if current.lower() in name.lower() or current.lower() in value.lower()
        ][:25]

    @add_payment.autocomplete("status")
    async def status_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> typing.List[app_commands.Choice[str]]:
        """Autocomplete for payment status."""
        statuses = [
            ("⏳ Pending", "pending"),
            ("✅ Paid", "paid"),
            ("🚨 Overdue", "overdue"),
            ("🔵 Active", "active"),
            ("❌ Cancelled", "cancelled")
        ]
        
        return [
            app_commands.Choice(name=name, value=value)
            for name, value in statuses
            if current.lower() in name.lower() or current.lower() in value.lower()
        ]

    @add_payment.autocomplete("frequency")
    async def frequency_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> typing.List[app_commands.Choice[str]]:
        """Autocomplete for payment frequency."""
        frequencies = [
            ("🔁 Once (One-time payment)", "once"),
            ("📅 Monthly", "monthly"),
            ("📆 Yearly", "yearly"),
            ("🗓️ Weekly", "weekly"),
            ("📋 Bi-Weekly", "bi-weekly"),
            ("💫 Quarterly", "quarterly")
        ]
        
        return [
            app_commands.Choice(name=name, value=value)
            for name, value in frequencies
            if current.lower() in name.lower() or current.lower() in value.lower()
        ]

    # ============================================================================ #
    #                           AUTOMATED REMINDERS                                 #
    # ============================================================================ #
    
    @tasks.loop(hours=24)
    async def payment_reminder_loop(self):
        """Check for upcoming and overdue payments daily and send reminders."""
        try:
            upcoming_payments = await FinTech.check_due_dates()
            
            for reminder in upcoming_payments:
                try:
                    user = self.client.get_user(reminder["user_id"])
                    if not user:
                        continue
                    
                    # Update status based on current state
                    current_status = reminder.get("status", "pending")
                    
                    # Parse due date
                    try:
                        due_date = datetime.strptime(reminder['due_date'], "%Y-%m-%d")
                        unix_timestamp = int(due_date.timestamp())
                        days_until = (due_date - datetime.now()).days
                    except (ValueError, KeyError):
                        continue
                    
                    # Determine urgency and update status
                    if days_until < 0:
                        # Overdue
                        if current_status == "reminded":
                            await FinTech.update_payment_status(
                                reminder["user_id"],
                                reminder["name"],
                                "overdue"
                            )
                        urgency_color = discord.Color.red()
                        urgency_emoji = "🚨"
                        urgency_text = f"**OVERDUE by {abs(days_until)} days!**"
                    elif days_until == 0:
                        # Due today
                        urgency_color = discord.Color.orange()
                        urgency_emoji = "⚠️"
                        urgency_text = "**DUE TODAY!**"
                    elif days_until <= 3:
                        # Due soon
                        if current_status != "reminded":
                            await FinTech.update_payment_status(
                                reminder["user_id"],
                                reminder["name"],
                                "reminded"
                            )
                        urgency_color = discord.Color.gold()
                        urgency_emoji = "⏰"
                        urgency_text = f"Due in {days_until} days"
                    else:
                        # Not urgent enough to send reminder
                        continue
                    
                    # Create reminder embed
                    embed = discord.Embed(
                        title=f"{urgency_emoji} Payment Reminder: {reminder['name']}",
                        description=urgency_text,
                        color=urgency_color,
                        timestamp=datetime.now()
                    )
                    
                    embed.add_field(
                        name="💰 Amount Due",
                        value=f"${reminder['amount']:,.2f}",
                        inline=True
                    )
                    
                    if reminder.get('category'):
                        embed.add_field(
                            name="📍 Category",
                            value=reminder['category'],
                            inline=True
                        )
                    
                    embed.add_field(
                        name="⚠️ Status",
                        value=reminder.get('status', 'pending').capitalize(),
                        inline=True
                    )
                    
                    embed.add_field(
                        name="📅 Due Date",
                        value=f"<t:{unix_timestamp}:D> (<t:{unix_timestamp}:R>)",
                        inline=False
                    )
                    
                    embed.set_footer(
                        text="Use /add_payment to mark as paid • /fin_list to view all payments"
                    )
                    
                    await user.send(embed=embed)
                    
                except discord.Forbidden:
                    # User has DMs disabled
                    continue
                except Exception as e:
                    errorHandler.handle(
                        e,
                        context=f"Error sending reminder to user {reminder.get('user_id')}"
                    )
                    continue
                    
        except Exception as e:
            errorHandler.handle(e, context="Error in payment reminder loop.")

    @payment_reminder_loop.before_loop
    async def before_payment_reminder_loop(self):
        """Wait until the bot is ready before starting the reminder loop."""
        await self.client.wait_until_ready()


async def setup(client):
    await client.add_cog(Finance(client))