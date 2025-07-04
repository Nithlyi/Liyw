import discord
from discord.ext import commands
from discord import app_commands
import logging

# Configuração de logging para o cog
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class OwnerCommands(commands.Cog):
    def __init__(self, bot: commands.Bot): # db_manager removido daqui
        self.bot = bot
        self.db = bot.db_connection # Acesse a instância do gerenciador de DB diretamente do bot

    async def cog_check(self, ctx: commands.Context):
        """
        Verifica se o usuário que invocou o comando de texto é o proprietário do bot.
        Este check é aplicado a todos os comandos de texto neste cog.
        """
        return await self.bot.is_owner(ctx.author)

    @app_commands.command(name="sync", description="Sincroniza os comandos de barra (apenas para o proprietário do bot).")
    async def sync(self, interaction: discord.Interaction):
        """
        Comando de barra para sincronizar os comandos de aplicação (slash commands).
        Verifica se o usuário é o proprietário do bot antes de executar.
        """
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("Você não tem permissão para usar este comando.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True) # Defer a resposta para evitar timeout
        try:
            # Sincroniza comandos globais
            synced_global = await self.bot.tree.sync()
            
            # Se TEST_GUILD_ID estiver configurado no bot, sincroniza lá também
            # Nota: TEST_GUILD_ID precisaria ser definido na sua classe MyBot em main.py
            # Ex: self.TEST_GUILD_ID = config.get('TEST_GUILD_ID')
            if hasattr(self.bot, 'TEST_GUILD_ID') and self.bot.TEST_GUILD_ID:
                test_guild = discord.Object(id=self.bot.TEST_GUILD_ID)
                self.bot.tree.copy_global_to(guild=test_guild) # Copia comandos globais para o servidor de teste
                synced_guild = await self.bot.tree.sync(guild=test_guild) # Sincroniza no servidor de teste
                await interaction.followup.send(
                    f"Comandos globais sincronizados ({len(synced_global)}). "
                    f"Comandos sincronizados para o servidor de testes ({len(synced_guild)}).", 
                    ephemeral=True
                )
            else:
                await interaction.followup.send(f"Comandos globais sincronizados ({len(synced_global)}).", ephemeral=True)
            
            logging.info(f"Comandos de barra sincronizados por {interaction.user.name} (ID: {interaction.user.id})")

        except Exception as e:
            logging.error(f"Erro ao sincronizar comandos de barra: {e}", exc_info=True)
            await interaction.followup.send(f"Ocorreu um erro ao sincronizar os comandos de barra: `{e}`", ephemeral=True)

    @app_commands.command(name="reload_cog", description="Recarrega um cog (apenas para o proprietário do bot).")
    @app_commands.describe(cog_name="O nome completo do cog (e.g., cogs.moderation.moderation_commands)")
    async def reload_cog(self, interaction: discord.Interaction, cog_name: str):
        """
        Comando de barra para recarregar um cog específico.
        Útil para aplicar mudanças no código sem reiniciar o bot.
        """
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("Você não tem permissão para usar este comando.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.reload_extension(cog_name)
            await interaction.followup.send(f"Cog `{cog_name}` recarregado com sucesso!", ephemeral=True)
            logging.info(f"Cog '{cog_name}' recarregado por {interaction.user.name} (ID: {interaction.user.id})")
        except Exception as e:
            await interaction.followup.send(f"Falha ao recarregar cog `{cog_name}`: `{e}`", ephemeral=True)
            logging.error(f"Falha ao recarregar cog '{cog_name}': {e}", exc_info=True)

    @app_commands.command(name="shutdown", description="Desliga o bot (apenas para o proprietário do bot).")
    async def shutdown(self, interaction: discord.Interaction):
        """
        Comando de barra para desligar o bot.
        """
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("Você não tem permissão para usar este comando.", ephemeral=True)
            return

        await interaction.response.send_message("Desligando o bot...", ephemeral=True)
        logging.info(f"Bot desligado por {interaction.user.name} (ID: {interaction.user.id})")
        await self.bot.close()

async def setup(bot: commands.Bot): # db_manager removido daqui
    """
    Função de setup para adicionar o cog ao bot.
    """
    await bot.add_cog(OwnerCommands(bot)) # db_manager removido daqui
