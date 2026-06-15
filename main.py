from client import Client
import settings

# Initializing the bot client
client = Client()

def run():
    client.run(settings.DISCORD_TOKEN, root_logger=True) #type: ignore
    

if __name__ == "__main__":
    run()
