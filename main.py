from client import Client
import settings

# Initializing the bot client
client = Client()


# Function to start the bot
def run():
    client.run(settings.DISCORD_TOKEN, root_logger=True)


if __name__ == "__main__":
    run()
