import os
import asyncio
import logging
import discord
from discord.ext import commands
from flask import Flask, jsonify
from threading import Thread
import json

# Configure logging for the bot
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import init_db from your database.py
from database import init_db

# --- Configuration Loading ---
try:
    with open('config.json', 'r') as f:
        config = json.load(f)
    DISCORD_BOT_TOKEN = config.get('DISCORD_BOT_TOKEN')
    PREFIX = config.get('PREFIX', '!')
    OWNER_IDS = config.get('OWNER_IDS', []) # List of owner IDs for owner commands
except FileNotFoundError:
    logger.critical("config.json not found! Please create a config.json with your bot token.")
    DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
    PREFIX = os.getenv('BOT_PREFIX', '!')
    OWNER_IDS = [int(x) for x in os.getenv('BOT_OWNER_IDS', '').split(',') if x]
    if not DISCORD_BOT_TOKEN:
        raise ValueError("DISCORD_BOT_TOKEN not found in config.json or environment variables.")
except json.JSONDecodeError:
    logger.critical("Error decoding config.json. Please check its format.")
    raise

# --- Bot Setup ---
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True  # Required for welcome/leave, moderation, etc.
        intents.message_content = True # Required to read message content
        super().__init__(command_prefix=PREFIX, intents=intents, owner_ids=OWNER_IDS)
        self.db_connection = None # Inicializa db_connection, será a instância do DatabaseManager
        self.flask_app = Flask(__name__)
        self.setup_flask_routes()

    async def setup_hook(self):
        logger.info("Inicializando o banco de dados...")
        try:
            # Atribui a instância do DatabaseManager ao objeto bot
            # init_db() deve retornar uma instância da sua classe DatabaseManager
            self.db_connection = await init_db()
            logger.info("Banco de dados inicializado com sucesso.")
        except Exception as e:
            logger.critical(f"Ocorreu um erro crítico ao iniciar o bot: {e}")
            await self.close()
            return

        # Load cogs
        initial_extensions = [
            'cogs.owner.owner_commands',
            'cogs.logs.log_system',
            'cogs.moderation.moderation_commands',
            'cogs.moderation.lockdown_core',
            'cogs.moderation.lockdown_panel',
            'cogs.events.raid_protection',
            'cogs.events.welcome_leave',
            'cogs.events.event_listeners',
            'cogs.utility.ticket_system',
            'cogs.utility.embed_creator',
            'cogs.utility.backup_commands',
            # 'cogs.utility.say_command', # Comentado porque o arquivo não foi encontrado no log
            'cogs.utility.utility_commands',
            'cogs.diversion.diversion_commands',
            'cogs.diversion.marriage_system',
            'cogs.utility.alt_checker',
            'cogs.moderation.anti_features' # Adicione esta linha para carregar a nova cog
        ]

        final_load_order = []
        for extension in initial_extensions:
            try:
                # Não passe db_manager aqui. Os cogs o acessarão via bot.db_connection
                await self.load_extension(extension)
                final_load_order.append(extension)
            except Exception as e:
                logger.error(f"Falha ao carregar a extensão {extension}: {e}")
        logger.info(f"Ordem final de carregamento dos Cogs: {final_load_order}")

        # Sync application commands (slash commands)
        try:
            await self.tree.sync()
            logger.info("Comandos de aplicação sincronizados com sucesso.")
        except Exception as e:
            logger.error(f"Falha ao sincronizar comandos de aplicação: {e}")

    async def on_ready(self):
        logger.info(f'Logado como {self.user} (ID: {self.user.id})')
        logger.info(f'Prefixo do bot: {self.command_prefix}')
        logger.info(f'Servidores conectados: {len(self.guilds)}')
        for guild in self.guilds:
            logger.info(f'- {guild.name} (ID: {guild.id})')

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return # Ignore command not found errors
        logger.error(f"Erro no comando '{ctx.command}': {error}")
        await ctx.send(f"Ocorreu um erro: {error}")

    def setup_flask_routes(self):
        @self.flask_app.route('/')
        def home():
            return jsonify({"status": "Bot is running", "user": str(self.user)})

    def run_flask_server(self):
        logger.info("Flask server thread started.")
        self.flask_app.run(host='0.0.0.0', port=8080, debug=False)

# --- Main Execution ---
if __name__ == "__main__":
    bot = MyBot()

    # Start Flask server in a separate thread
    flask_thread = Thread(target=bot.run_flask_server)
    flask_thread.daemon = True # Daemonize thread so it exits when main program exits
    flask_thread.start()

    # Run the Discord bot
    try:
        bot.run(DISCORD_BOT_TOKEN)
    except discord.LoginFailure:
        logger.critical("Token do bot inválido. Verifique seu DISCORD_BOT_TOKEN.")
    except Exception as e:
        logger.critical(f"Ocorreu um erro crítico ao iniciar o bot: {e}")
