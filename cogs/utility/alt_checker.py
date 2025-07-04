import discord
from discord.ext import commands
from discord import app_commands
import logging

logger = logging.getLogger(__name__)

class AltChecker(commands.Cog):
    # Define o grupo para checar contas alternativas/nicks como um atributo de classe.
    checkalts_group = app_commands.Group(name="checkalts", description="Comandos para verificar contas alternativas e nicks parecidos.")

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @checkalts_group.command(name="names", description="Verifica por membros com nomes de usuário ou nicks parecidos no servidor.")
    @app_commands.describe(query="O nome ou parte do nome para procurar.")
    @app_commands.default_permissions(kick_members=True) # Permissão para kickar membros é razoável para usar este comando
    async def checkalts_names(self, interaction: discord.Interaction, query: str):
        """
        Verifica por membros no servidor com nomes de usuário, nicks ou nomes globais
        que contenham a query fornecida.
        """
        await interaction.response.defer(ephemeral=True, thinking=True) # Defer a resposta para dar tempo de processar

        guild = interaction.guild
        if not guild:
            await interaction.followup.send("Este comando só pode ser usado em um servidor.", ephemeral=True)
            return

        query_lower = query.lower()
        found_members = []

        # Itera por todos os membros do servidor
        for member in guild.members:
            # Verifica se a query está presente no nome de usuário, nome de exibição (nick) ou nome global
            if query_lower in member.name.lower() or \
               (member.display_name and query_lower in member.display_name.lower()) or \
               (member.global_name and query_lower in member.global_name.lower()):
                found_members.append(member)
        
        if not found_members:
            await interaction.followup.send(f"Nenhum membro encontrado com nomes parecidos com '{query}'.", ephemeral=True)
            return

        response_message = f"Membros com nomes parecidos com '{query}':\n\n"
        for member in found_members:
            response_message += (
                f"**{member.display_name}** (`{member.name}` | ID: `{member.id}`)\n"
                f"  - Nickname: {member.nick or 'N/A'}\n"
                f"  - Global Name: {member.global_name or 'N/A'}\n"
                f"  - Entrou no Discord: <t:{int(member.created_at.timestamp())}:F>\n" # Data de criação da conta Discord
                f"  - Entrou no Servidor: <t:{int(member.joined_at.timestamp())}:F>\n\n" # Data de entrada no servidor
            )
        
        # Divide a mensagem se for muito longa para o Discord (limite de 2000 caracteres por mensagem)
        # Usamos 1900 para ter uma margem de segurança.
        if len(response_message) > 1900:
            parts = [response_message[i:i+1900] for i in range(0, len(response_message), 1900)]
            for i, part in enumerate(parts):
                if i == 0:
                    # A primeira parte é enviada como followup da interação original
                    await interaction.followup.send(f"Resultados para '{query}' (Parte {i+1}):\n{part}", ephemeral=True)
                else:
                    # Partes subsequentes são enviadas como mensagens normais no mesmo canal, ainda efêmeras.
                    await interaction.channel.send(f"Resultados para '{query}' (Parte {i+1}):\n{part}", ephemeral=True)
        else:
            await interaction.followup.send(response_message, ephemeral=True)


async def setup(bot):
    # Adiciona a cog ao bot. Isso registrará automaticamente o grupo de comandos
    # definido como atributo de classe (checkalts_group)
    await bot.add_cog(AltChecker(bot))

