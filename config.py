# config.py
import os # Importa o módulo os para acessar variáveis de ambiente
from dotenv import load_dotenv # Importa load_dotenv para carregar o .env

# Carrega as variáveis de ambiente do arquivo .env
# É importante que esta linha esteja aqui se você quiser que config.py use o .env
load_dotenv()

# Seu token do bot do Discord. Mantenha-o seguro e não o compartilhe!
# Ele será lido da variável de ambiente DISCORD_BOT_TOKEN no seu arquivo .env
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN") 

# Prefixo para comandos de texto (ex: !help, !ping)
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!") # Lê do .env, com padrão '!'

# ID do seu servidor de testes (guild ID) para sincronização rápida de comandos de barra.
# Se você quiser que os comandos de barra sincronizem globalmente (pode levar até 1 hora),
# defina TEST_GUILD_ID como None no seu .env.
# Converte para int, se não for possível, define como None.
TEST_GUILD_ID = os.getenv("TEST_GUILD_ID")
if TEST_GUILD_ID:
    try:
        TEST_GUILD_ID = int(TEST_GUILD_ID)
    except ValueError:
        TEST_GUILD_ID = None

# ID da aplicação do seu bot (Application ID). Encontrado no Portal do Desenvolvedor do Discord.
# Converte para int, se não for possível, define como None.
DISCORD_BOT_APPLICATION_ID = os.getenv("DISCORD_BOT_APPLICATION_ID")
if DISCORD_BOT_APPLICATION_ID:
    try:
        DISCORD_BOT_APPLICATION_ID = int(DISCORD_BOT_APPLICATION_ID)
    except ValueError:
        DISCORD_BOT_APPLICATION_ID = None

# ID do proprietário do bot (seu ID de usuário do Discord)
# Usado para comandos restritos ao proprietário.
# Converte para int, se não for possível, define como None.
OWNER_ID = os.getenv("OWNER_ID")
if OWNER_ID:
    try:
        OWNER_ID = int(OWNER_ID)
    except ValueError:
        OWNER_ID = None
