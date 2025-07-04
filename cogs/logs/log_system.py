import discord
from discord.ext import commands
import logging

# Configuração de logging para o cog
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class LogSystem(commands.Cog):
    def __init__(self, bot: commands.Bot): # db_manager removido daqui
        self.bot = bot
        self.db = bot.db_connection # Acesse a instância do gerenciador de DB diretamente do bot

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        """
        Registra mensagens deletadas em um canal de log.
        Você precisará configurar um canal de log, possivelmente usando o DB.
        """
        if message.author.bot: # Ignora mensagens de bots
            return

        # Exemplo de como você poderia usar o db_manager para obter um canal de log
        # log_channel_id = await self.db.get_guild_setting(message.guild.id, "log_channel_id")
        # if log_channel_id:
        #     log_channel = self.bot.get_channel(log_channel_id)
        #     if log_channel:
        #         embed = discord.Embed(
        #             title="Mensagem Deletada",
        #             description=f"**Autor:** {message.author.mention} (`{message.author}`)\n"
        #                                 f"**Canal:** {message.channel.mention}\n"
        #                                 f"**Conteúdo:**\n```\n{message.content}\n```",
        #             color=discord.Color.red()
        #         )
        #         await log_channel.send(embed=embed)
        # else:
        #     logging.info(f"Mensagem deletada no servidor {message.guild.name}, mas nenhum canal de log configurado.")

        logging.info(f"Mensagem deletada de {message.author} no canal #{message.channel.name}: {message.content}")

    # Você pode adicionar mais listeners aqui para outros eventos de log, como:
    # on_message_edit, on_member_join, on_member_remove, on_guild_channel_create, etc.

async def setup(bot: commands.Bot): # db_manager removido daqui
    """
    Função de setup para adicionar o cog ao bot.
    """
    await bot.add_cog(LogSystem(bot)) # db_manager removido daqui
