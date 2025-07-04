import discord
from discord.ext import commands
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class GeneralEventListeners(commands.Cog):
    def __init__(self, bot: commands.Bot): # db_manager removido daqui
        self.bot = bot
        self.db = bot.db_connection # Acesse a instância do gerenciador de DB diretamente do bot
        logging.info("Cog 'GeneralEventListeners' inicializado.")

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        """Ações quando o bot entra em um novo servidor."""
        logging.info(f"O bot entrou no servidor: {guild.name} (ID: {guild.id}).")
        # Envie uma mensagem de boas-vindas no canal padrão ou em um canal específico
        try:
            default_channel = guild.system_channel or next((c for c in guild.text_channels if c.permissions_for(guild.me).send_messages), None)
            if default_channel:
                embed = discord.Embed(
                    title=f"Olá, {guild.name}!",
                    description="Obrigado por me adicionar! Sou um bot multifuncional e estou aqui para ajudar.",
                    color=discord.Color.green()
                )
                embed.add_field(name="Primeiros Passos", value="Use `/help` para ver meus comandos.\nUse `/ticket_setup` e `/welcome_leave_panel` para configurar as principais funções.", inline=False)
                await default_channel.send(embed=embed)
        except Exception as e:
            logging.error(f"Erro ao enviar mensagem de boas-vindas no novo servidor {guild.name}: {e}")

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        """Ações quando o bot é removido de um servidor."""
        logging.info(f"O bot foi removido do servidor: {guild.name} (ID: {guild.id}).")
        # Opcional: Limpar dados do DB relacionados a este servidor
        # Exemplo: await self.db.execute_query("DELETE FROM some_table WHERE guild_id = ?", (guild.id,))


async def setup(bot: commands.Bot): # db_manager removido daqui
    """
    Função de setup para adicionar o cog ao bot.
    """
    await bot.add_cog(GeneralEventListeners(bot)) # db_manager removido daqui
