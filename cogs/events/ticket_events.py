import discord
from discord.ext import commands
import logging

# Este arquivo pode ser usado para eventos relacionados a tickets que não estão
# diretamente ligados à criação/fechamento ou gerenciamento do painel.
# Por exemplo, eventos de log específicos de tickets, ou interações mais complexas.

# No seu setup principal (main.py), certifique-se de que este cog seja carregado
# APENAS SE você remover os listeners de eventos de ticket de cogs/utility/ticket_system.py,
# para evitar duplicação ou comportamento inesperado.
# Se a funcionalidade principal de tickets já lida com on_ready, on_member_join, etc.,
# carregar este cog pode causar problemas se ele tentar registrar os mesmos ouvintes.

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class TicketEvents(commands.Cog):
    def __init__(self, bot: commands.Bot, db_manager): # Adicione db_manager aqui
        self.bot = bot
        self.db = db_manager # Armazena a instância do gerenciador de DB
        logging.info("Cog 'TicketEvents' inicializado com db_manager. (Atualmente sem ouvintes de eventos para evitar conflitos).")

    # Exemplo de um ouvinte de evento que poderia ser colocado aqui,
    # SE NÃO ESTIVER JÁ EM cogs/utility/ticket_system.py
    # @commands.Cog.listener()
    # async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
    #     # Lógica para reagir a reações em mensagens de ticket, por exemplo
    #     if payload.guild_id is None:
    #         return # Ignora DMs
    #     logging.info(f"Reação detectada: {payload.emoji.name} em {payload.channel_id}")

async def setup(bot: commands.Bot, db_manager): # Adicione db_manager aqui
    """
    Função de setup para adicionar o cog ao bot.
    """
    await bot.add_cog(TicketEvents(bot, db_manager)) # Passe db_manager para a classe TicketEvents
