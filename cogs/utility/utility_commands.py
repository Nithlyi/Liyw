import discord
from discord.ext import commands
from discord import app_commands, ui # Importa ui para usar componentes
import datetime
import logging

# A linha abaixo é mantida caso você tenha uma função execute_query global
# Se execute_query for um método de uma classe db_manager, você precisaria
# passar a instância do db_manager para a cog, como feito nos outros cogs.
# Como o código fornecido não usa db_manager, e sim execute_query diretamente,
# e não há chamadas assíncronas para execute_query, manteremos assim.
# from database import execute_query 

# Configuração de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Nova View para o botão de download do avatar
class AvatarDownloadView(ui.View):
    def __init__(self, avatar_url: str):
        super().__init__(timeout=600) # Timeout de 10 minutos para o botão
        # Adiciona um botão de link. O URL é o link direto para download.
        self.add_item(ui.Button(label="Baixar Avatar", style=discord.ButtonStyle.link, url=avatar_url, emoji="💾"))

    async def on_timeout(self):
        # Desabilita o botão quando o tempo limite expira
        for item in self.children:
            item.disabled = True
        if self.message: # Se a mensagem foi armazenada
            await self.message.edit(view=self)


class UtilityCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="avatar", description="Exibe o avatar de um usuário e oferece a opção de download.")
    @app_commands.describe(member="O membro cujo avatar você deseja ver (opcional, padrão: você).")
    async def avatar(self, interaction: discord.Interaction, member: discord.Member = None):
        await interaction.response.defer(ephemeral=True) # Deferir para evitar timeout

        target_member = member or interaction.user # Se nenhum membro for especificado, usa o autor

        embed = discord.Embed(
            title=f"Avatar de {target_member.display_name}",
            color=discord.Color.blue()
        )
        embed.set_image(url=target_member.display_avatar.url) # Define o avatar como a imagem principal do embed
        embed.set_footer(text=f"ID do Usuário: {target_member.id}")

        # Cria a view com o botão de download
        view = AvatarDownloadView(target_member.display_avatar.url)

        # Envia a mensagem com o embed e a view (botão)
        # ephemeral=False para que o botão seja visível e clicável por todos
        # Armazena a mensagem na view para poder desabilitar o botão no timeout
        await interaction.followup.send(embed=embed, view=view, ephemeral=False)
        view.message = await interaction.original_response() # Armazena a mensagem para o timeout da view
        
        logging.info(f"Comando /avatar usado por {interaction.user.id} para {target_member.id} na guild {interaction.guild.id}.")


    @app_commands.command(name="serverinfo", description="Exibe informações detalhadas sobre o servidor.")
    async def serverinfo(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        if not guild:
            await interaction.followup.send("Este comando só pode ser usado em um servidor.", ephemeral=True)
            return

        # Contagem de membros
        total_members = guild.member_count
        human_members = len([m for m in guild.members if not m.bot])
        bot_members = len([m for m in guild.members if m.bot])

        # Contagem de canais
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        categories = len(guild.categories)
        total_channels = text_channels + voice_channels + categories

        # Data de criação do servidor
        created_at_unix = int(guild.created_at.timestamp())

        embed = discord.Embed(
            title=f"Informações do Servidor: {guild.name}",
            color=discord.Color.green()
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        
        embed.add_field(name="ID do Servidor", value=guild.id, inline=True)
        embed.add_field(name="Proprietário", value=guild.owner.mention if guild.owner else "Desconhecido", inline=True)
        embed.add_field(name="Criado em", value=f"<t:{created_at_unix}:F>", inline=False)
        
        embed.add_field(name="Membros", value=(
            f"Total: {total_members}\n"
            f"Humanos: {human_members}\n"
            f"Bots: {bot_members}"
        ), inline=True)
        
        embed.add_field(name="Canais", value=(
            f"Total: {total_channels}\n"
            f"Texto: {text_channels}\n"
            f"Voz: {voice_channels}\n"
            f"Categorias: {categories}"
        ), inline=True)

        embed.add_field(name="Cargos", value=len(guild.roles), inline=True)
        embed.add_field(name="Nível de Boost", value=f"Nível {guild.premium_tier} ({guild.premium_subscription_count} boosts)", inline=True)
        embed.add_field(name="Nível de Verificação", value=str(guild.verification_level).replace('_', ' ').title(), inline=True)
        embed.add_field(name="Notificações Padrão", value=str(guild.default_notifications).replace('_', ' ').title(), inline=True)

        await interaction.followup.send(embed=embed, ephemeral=False)
        logging.info(f"Comando /serverinfo usado por {interaction.user.id} na guild {interaction.guild.id}.")


    @app_commands.command(name="userinfo", description="Exibe informações detalhadas sobre um usuário.")
    @app_commands.describe(member="O membro cujo informações você deseja ver (opcional, padrão: você).")
    async def userinfo(self, interaction: discord.Interaction, member: discord.Member = None):
        await interaction.response.defer(ephemeral=True)

        target_member = member or interaction.user # Se nenhum membro for especificado, usa o autor

        # Data de criação da conta
        account_created_unix = int(target_member.created_at.timestamp())
        
        # Data de entrada no servidor (se for um membro)
        joined_at_unix = None
        if isinstance(target_member, discord.Member) and target_member.joined_at:
            joined_at_unix = int(target_member.joined_at.timestamp())

        embed = discord.Embed(
            title=f"Informações de {target_member.display_name}",
            color=discord.Color.purple()
        )
        embed.set_thumbnail(url=target_member.display_avatar.url)

        embed.add_field(name="Nome de Usuário", value=target_member.name, inline=True)
        embed.add_field(name="ID do Usuário", value=target_member.id, inline=True)
        embed.add_field(name="Bot?", value="Sim" if target_member.bot else "Não", inline=True)
        
        embed.add_field(name="Conta Criada em", value=f"<t:{account_created_unix}:F>", inline=False)
        if joined_at_unix:
            embed.add_field(name="Entrou no Servidor em", value=f"<t:{joined_at_unix}:F>", inline=False)
        
        if isinstance(target_member, discord.Member):
            # Cargos (excluindo @everyone e ordenando por posição)
            roles = sorted([role for role in target_member.roles if role.name != "@everyone"], key=lambda r: r.position, reverse=True)
            if roles:
                embed.add_field(name="Cargos", value=", ".join([role.mention for role in roles]), inline=False)
            else:
                embed.add_field(name="Cargos", value="Nenhum cargo especial.", inline=False)

            # Cargo mais alto (excluindo @everyone)
            top_role = target_member.top_role
            if top_role and top_role.name != "@everyone":
                embed.add_field(name="Cargo Mais Alto", value=top_role.mention, inline=True)
            else:
                embed.add_field(name="Cargo Mais Alto", value="Nenhum (apenas @everyone)", inline=True)

            # Status de Boost
            if target_member.premium_since:
                embed.add_field(name="Impulsionando o Servidor", value=f"Desde <t:{int(target_member.premium_since.timestamp())}:D>", inline=True)
            else:
                embed.add_field(name="Impulsionando o Servidor", value="Não", inline=True)
        
        await interaction.followup.send(embed=embed, ephemeral=False)
        logging.info(f"Comando /userinfo usado por {interaction.user.id} para {target_member.id} na guild {interaction.guild.id}.")


async def setup(bot: commands.Bot):
    await bot.add_cog(UtilityCommands(bot))
