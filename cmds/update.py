from discord import app_commands
from discord.ext import commands
import os, discord, typing
from settings import *

DATA_DIR = "data"

os.makedirs(DATA_DIR, exist_ok=True)


class Update(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.versions = ["ver_1.0"]
        self.current = "ver_1.0"

    def create_embed(self, data):
        """Create an embed with a link to the update requested

        Args:
            data (json): OCntains details about the requested update

        Returns:
            embed: Discord embed with links
        """
        url = f"https://austindwomoh.xyz/{data['version']}"

        embed = discord.Embed(
            title=f"[Update {data['version']}]({url})",  # Title with a clickable link
            description=f"**Release Date:** {data['release_date']}\n\n{data['notes']}",
            color=discord.Color.blue(),
        )
        return embed  # Return the embed

    @app_commands.command(
        name="update_version_data",
        description="Get update details for each bot version",
    )
    async def update_version_data(
        self, interaction: discord.Interaction, version: str = None
    ):
        """Invokes the command to check version data

        Args:
            interaction (discord.Interaction): from discord
            version (str, optional): the version the user wants to check. Defaults to None. and uses the current version number
        """
        if not version:
            await interaction.response.send_message(
                "Please provide a version number.", ephemeral=True
            )
            return
#mock data but will use this for now till it gets too large
        data = {
            "ver_1.0": {
                "version": "ver_1.0",
                "release_date": "2025-03-04",
                "notes": "Bug fixes and performance improvements.",
            },
        }

        embed = self.create_embed(data["ver_1.0"])
        await interaction.response.send_message(embed=embed)

    @update_version_data.autocomplete("version")
    async def type_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> typing.List[app_commands.Choice[str]]:
        try:
            choices = self.versions
            filtered_choices = [
                app_commands.Choice(name=choice, value=choice)
                for choice in choices
                if current.lower() in choice.lower()
            ]
            return filtered_choices
        except discord.errors.NotFound:
            # Ignore the "Unknown interaction" error
            return []
        except Exception as e:
            errorHandler = ErrorHandler()
            errorHandler.handle_exception(e)
            return []
        except discord.errors.HTTPException as e:
            if "Interaction has already been acknowledged" in str(e):#this helps avoid it keep calling it self which it keeps doing for some reason
                pass


async def setup(client):
    await client.add_cog(Update(client))
