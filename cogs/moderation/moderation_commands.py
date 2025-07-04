# cogs/moderation/moderation_commands.py
import discord
from discord.ext import commands
from discord import app_commands, ui
import datetime
import logging
import re # Para parsing do tempo
from typing import Optional # Importa Optional para tipagem
from database import adapt_query_placeholders
# Assumindo que BaseChannelSelectView está definida em outro lugar e importada
# from .views import BaseChannelSelectView

# Configuração de logging
logger = logging.getLogger(__name__)

# --- Funções Auxiliares para Parsing de Tempo ---
def parse_duration(duration_str: str) -> datetime.timedelta:
    """
    Parses a duration string (e.g., "1h", "30m", "2d") into a datetime.timedelta object.
    Supports: s (seconds), m (minutes), h (hours), d (days).
    """
    seconds = 0
    if not duration_str:
        raise ValueError("Duração não pode ser vazia.")

    # Regex para encontrar números e unidades (s, m, h, d)
    parts = re.findall(r'(\d+)([smhd])', duration_str.lower())
    if not parts:
        raise ValueError("Formato de duração inválido. Use, por exemplo: '30m', '1h', '2d'.")

    for value, unit in parts:
        value = int(value)
        if unit == 's':
            seconds += value
        elif unit == 'm':
            seconds += value * 60
        elif unit == 'h':
            seconds += value * 3600
        elif unit == 'd':
            seconds += value * 86400
    
    # Discord API timeout limit is 28 days (2419200 seconds)
    if seconds > 2419200:
        raise ValueError("A duração máxima para silenciamento é de 28 dias.")

    return datetime.timedelta(seconds=seconds)


# --- Modals para Ações de Moderação ---
class WarnModal(ui.Modal, title="Advertir Usuário"):
    def __init__(self, target_member: discord.Member, target_channel: discord.TextChannel, bot_instance):
        super().__init__()
        self.target_member = target_member
        self.target_channel = target_channel
        self.db = bot_instance.db_connection # Acessa db_connection do bot

        self.reason = ui.TextInput(
            label="Razão da Advertência",
            placeholder="Descreva o motivo da advertência...",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=500
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        reason_text = self.reason.value

        success = False
        try:
            # Assumindo que self.db.execute_query retorna True para sucesso
            success = await self.db.execute_query( # Usando self.db
                adapt_query_placeholders("INSERT INTO moderation_logs (guild_id, action, target_id, moderator_id, reason) VALUES (?, ?, ?, ?, ?)"),
                (interaction.guild_id, "warn", self.target_member.id, interaction.user.id, reason_text)
            )
        except Exception as e:
            logger.error(f"Erro ao registrar advertência no DB para {self.target_member.id}: {e}", exc_info=True)
            await interaction.followup.send("Ocorreu um erro ao registrar a advertência no banco de dados.", ephemeral=True)
            return

        if success:
            embed = discord.Embed(
                title="Advertência Registrada",
                description=f"O usuário {self.target_member.mention} foi advertido.",
                color=discord.Color.orange()
            )
            embed.add_field(name="Moderador", value=interaction.user.mention, inline=True)
            embed.add_field(name="Razão", value=reason_text, inline=False)
            embed.add_field(name="Canal da Advertência", value=self.target_channel.mention, inline=True)
            embed.set_footer(text=f"ID do Usuário: {self.target_member.id}")

            try:
                await self.target_channel.send(embed=embed)
                await interaction.followup.send(f"Advertência enviada para {self.target_channel.mention}!", ephemeral=True)
                logger.info(f"Advertência registrada para {self.target_member.id} por {interaction.user.id} na guild {interaction.guild.id} e enviada para {self.target_channel.name}. Razão: {reason_text}")
            except discord.Forbidden:
                await interaction.followup.send(f"Não tenho permissão para enviar mensagens em {self.target_channel.mention}.", ephemeral=True)
                logger.error(f"Permissão negada ao enviar advertência para {self.target_channel.name} na guild {interaction.guild.id}.")
            except Exception as e:
                await interaction.followup.send(f"Ocorreu um erro ao enviar a advertência: {e}", ephemeral=True)
                logger.error(f"Erro ao enviar advertência para {self.target_channel.name}: {e}", exc_info=True)

            try:
                dm_embed = discord.Embed(
                    title="Você foi Advertido(a)!",
                    description=f"Você recebeu uma advertência no servidor **{interaction.guild.name}**.",
                    color=discord.Color.orange()
                )
                dm_embed.add_field(name="Razão", value=reason_text, inline=False)
                dm_embed.add_field(name="Canal", value=self.target_channel.mention, inline=True)
                dm_embed.set_footer(text="Por favor, revise as regras do servidor para evitar futuras advertências.")
                await self.target_member.send(embed=dm_embed)
                logger.info(f"DM de advertência enviada para {self.target_member.id}.")
            except discord.Forbidden:
                logger.warning(f"Não foi possível enviar DM de advertência para {self.target_member.id}.")
            except Exception as e:
                logger.error(f"Erro ao enviar DM de advertência para {self.target_member.id}: {e}", exc_info=True)
        else:
            await interaction.followup.send("Ocorreu um erro ao registrar a advertência no banco de dados.", ephemeral=True)
            logger.error(f"Erro ao registrar advertência no DB para {self.target_member.id} por {interaction.user.id} na guild {interaction.guild_id}.")


class KickModal(ui.Modal, title="Expulsar Usuário"):
    def __init__(self, target_member: discord.Member, target_channel: discord.TextChannel, bot_instance):
        super().__init__()
        self.target_member = target_member
        self.target_channel = target_channel
        self.db = bot_instance.db_connection # Acessa db_connection do bot
        self.reason = ui.TextInput(
            label="Razão da Expulsão",
            placeholder="Descreva o motivo da expulsão...",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=500
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        reason_text = self.reason.value

        if not self.target_member:
            await interaction.followup.send("Membro alvo não encontrado para expulsão.", ephemeral=True)
            return

        if not interaction.guild.me.guild_permissions.kick_members:
            await interaction.followup.send("Não tenho permissão para expulsar membros.", ephemeral=True)
            return
        if interaction.user.top_role <= self.target_member.top_role and interaction.user.id != interaction.guild.owner_id:
            await interaction.followup.send("Você não pode expulsar um membro com cargo igual ou superior ao seu.", ephemeral=True)
            return
        if self.target_member.id == interaction.user.id:
            await interaction.followup.send("Você não pode expulsar a si mesmo.", ephemeral=True)
            return
        if self.target_member.id == interaction.guild.owner_id:
            await interaction.followup.send("Você não pode expulsar o proprietário do servidor.", ephemeral=True)
            return
        if self.target_member.bot and not interaction.user.guild_permissions.manage_guild:
            await interaction.followup.send("Você não pode expulsar um bot a menos que seja um administrador.", ephemeral=True)
            return

        try:
            try:
                dm_embed = discord.Embed(
                    title="Você foi Expulso(a)!",
                    description=f"Você foi expulso(a) do servidor **{interaction.guild.name}**.",
                    color=discord.Color.red()
                )
                dm_embed.add_field(name="Razão", value=reason_text, inline=False)
                dm_embed.set_footer(text="Esta ação é permanente. Você pode tentar entrar novamente se for um erro.")
                await self.target_member.send(embed=dm_embed)
                logger.info(f"DM de expulsão enviada para {self.target_member.id}.")
            except discord.Forbidden:
                logger.warning(f"Não foi possível enviar DM de expulsão para {self.target_member.id}.")
            except Exception as e:
                logger.error(f"Erro ao enviar DM de expulsão para {self.target_member.id}: {e}", exc_info=True)

            await self.target_member.kick(reason=reason_text)
            
            success = False
            try:
                success = await self.db.execute_query( # Usando self.db
                    adapt_query_placeholders("INSERT INTO moderation_logs (guild_id, action, target_id, moderator_id, reason) VALUES (?, ?, ?, ?, ?)"),
                    (interaction.guild.id, "kick", self.target_member.id, interaction.user.id, reason_text)
                )
            except Exception as e:
                logger.error(f"Erro ao registrar expulsão no DB para {self.target_member.id}: {e}", exc_info=True)
                # Não precisa retornar aqui, pois a expulsão já foi feita. Apenas logar.

            embed = discord.Embed(
                title="Usuário Expulso",
                description=f"O usuário {self.target_member.mention} foi expulso.",
                color=discord.Color.red()
            )
            embed.add_field(name="Moderador", value=interaction.user.mention, inline=True)
            embed.add_field(name="Razão", value=reason_text, inline=False)
            embed.add_field(name="Canal da Expulsão", value=self.target_channel.mention, inline=True)
            embed.set_footer(text=f"ID do Usuário: {self.target_member.id}")

            try:
                await self.target_channel.send(embed=embed)
                await interaction.followup.send(f"Expulsão enviada para {self.target_channel.mention}!", ephemeral=True)
                logger.info(f"Expulsão registrada para {self.target_member.id} por {interaction.user.id} na guild {interaction.guild.id} e enviada para {self.target_channel.name}. Razão: {reason_text}")
            except discord.Forbidden:
                await interaction.followup.send(f"Não tenho permissão para enviar mensagens em {self.target_channel.mention}.", ephemeral=True)
                logger.error(f"Permissão negada ao enviar expulsão para {self.target_channel.name} na guild {interaction.guild.id}.")
            except Exception as e:
                await interaction.followup.send(f"Ocorreu um erro ao enviar a expulsão: {e}", ephemeral=True)
                logger.error(f"Erro ao enviar expulsão para {self.target_channel.name}: {e}", exc_info=True)

        except discord.Forbidden:
            await interaction.followup.send("Não tenho permissão para expulsar este membro.", ephemeral=True)
            logger.error(f"Permissão negada ao expulsar {self.target_member.id} na guild {interaction.guild.id}.")
        except Exception as e:
            await interaction.followup.send(f"Ocorreu um erro ao expulsar o membro: {e}", ephemeral=True)
            logger.error(f"Erro inesperado ao expulsar {self.target_member.id}: {e}", exc_info=True)


class BanModal(ui.Modal, title="Banir Usuário"):
    def __init__(self, target_member: discord.Member, target_channel: discord.TextChannel, bot_instance):
        super().__init__()
        self.target_member = target_member
        self.target_channel = target_channel
        self.db = bot_instance.db_connection # Acessa db_connection do bot
        self.reason = ui.TextInput(
            label="Razão do Banimento",
            placeholder="Descreva o motivo do banimento...",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=500
        )
        self.add_item(self.reason)
        self.delete_message_days = ui.TextInput(
            label="Deletar Histórico de Mensagens (dias)",
            placeholder="Número de dias (0 a 7) para deletar mensagens. Padrão: 0",
            style=discord.TextStyle.short,
            required=False,
            default="0"
        )
        self.add_item(self.delete_message_days)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        reason_text = self.reason.value
        delete_days = 0
        try:
            delete_days = int(self.delete_message_days.value)
            if not 0 <= delete_days <= 7:
                await interaction.followup.send("O número de dias para deletar histórico deve ser entre 0 e 7.", ephemeral=True)
                return
        except ValueError:
            await interaction.followup.send("Por favor, insira um número válido para deletar histórico de mensagens.", ephemeral=True)
            return

        if not self.target_member:
            await interaction.followup.send("Membro alvo não encontrado para banimento.", ephemeral=True)
            return

        if not interaction.guild.me.guild_permissions.ban_members:
            await interaction.followup.send("Não tenho permissão para banir membros.", ephemeral=True)
            return
        if interaction.user.top_role <= self.target_member.top_role and interaction.user.id != interaction.guild.owner_id:
            await interaction.followup.send("Você não pode banir um membro com cargo igual ou superior ao seu.", ephemeral=True)
            return
        if self.target_member.id == interaction.user.id:
            await interaction.followup.send("Você não pode banir a si mesmo.", ephemeral=True)
            return
        if self.target_member.id == interaction.guild.owner_id:
            await interaction.followup.send("Você não pode banir o proprietário do servidor.", ephemeral=True)
            return
        if self.target_member.bot and not interaction.user.guild_permissions.manage_guild:
            await interaction.followup.send("Você não pode banir um bot a menos que seja um administrador.", ephemeral=True)
            return

        try:
            try:
                dm_embed = discord.Embed(
                    title="Você foi Banido(a)!",
                    description=f"Você foi banido(a) do servidor **{interaction.guild.name}**.",
                    color=discord.Color.dark_red()
                )
                dm_embed.add_field(name="Razão", value=reason_text, inline=False)
                dm_embed.set_footer(text="Esta ação é permanente e impede que você entre novamente.")
                await self.target_member.send(embed=dm_embed)
                logger.info(f"DM de banimento enviada para {self.target_member.id}.")
            except discord.Forbidden:
                logger.warning(f"Não foi possível enviar DM de banimento para {self.target_member.id}.")
            except Exception as e:
                logger.error(f"Erro ao enviar DM de banimento para {self.target_member.id}: {e}", exc_info=True)

            await self.target_member.ban(reason=reason_text, delete_message_days=delete_days)
            
            success = False
            try:
                success = await self.db.execute_query( # Usando self.db
                    adapt_query_placeholders("INSERT INTO moderation_logs (guild_id, action, target_id, moderator_id, reason) VALUES (?, ?, ?, ?, ?)"),
                    (interaction.guild.id, "ban", self.target_member.id, interaction.user.id, reason_text)
                )
            except Exception as e:
                logger.error(f"Erro ao registrar banimento no DB para {self.target_member.id}: {e}", exc_info=True)
                # Não precisa retornar aqui, pois o banimento já foi feito. Apenas logar.

            embed = discord.Embed(
                title="Usuário Banido",
                description=f"O usuário {self.target_member.mention} foi banido.",
                color=discord.Color.dark_red()
            )
            embed.add_field(name="Moderador", value=interaction.user.mention, inline=True)
            embed.add_field(name="Razão", value=reason_text, inline=False)
            embed.add_field(name="Mensagens Deletadas (dias)", value=delete_days, inline=True)
            embed.add_field(name="Canal do Banimento", value=self.target_channel.mention, inline=True)
            embed.set_footer(text=f"ID do Usuário: {self.target_member.id}")

            try:
                await self.target_channel.send(embed=embed)
                await interaction.followup.send(f"Banimento enviado para {self.target_channel.mention}!", ephemeral=True)
                logger.info(f"Banimento registrado para {self.target_member.id} por {interaction.user.id} na guild {interaction.guild.id} e enviada para {self.target_channel.name}. Razão: {reason_text}. Mensagens deletadas: {delete_days} dias.")
            except discord.Forbidden:
                await interaction.followup.send(f"Não tenho permissão para enviar mensagens em {self.target_channel.mention}.", ephemeral=True)
                logger.error(f"Permissão negada ao enviar banimento para {self.target_channel.name} na guild {interaction.guild.id}.")
            except Exception as e:
                await interaction.followup.send(f"Ocorreu um erro ao enviar o banimento: {e}", ephemeral=True)
                logger.error(f"Erro ao enviar banimento para {self.target_channel.name}: {e}", exc_info=True)

        except discord.Forbidden:
            await interaction.followup.send("Não tenho permissão para banir este membro.", ephemeral=True)
            logger.error(f"Permissão negada ao banir {self.target_member.id} na guild {interaction.guild.id}.")
        except Exception as e:
            await interaction.followup.send(f"Ocorreu um erro ao banir o membro: {e}", ephemeral=True)
            logger.error(f"Erro inesperado ao banir {self.target_member.id}: {e}", exc_info=True)


class MuteModal(ui.Modal, title="Silenciar Usuário"):
    def __init__(self, target_member: discord.Member, target_channel: discord.TextChannel, bot_instance):
        super().__init__()
        self.target_member = target_member
        self.target_channel = target_channel
        self.bot = bot_instance # Armazena a instância do bot
        self.db = bot_instance.db_connection # Acessa db_connection do bot

        self.duration_input = ui.TextInput(
            label="Duração do Silenciamento (ex: 30m, 1h, 2d)",
            placeholder="Ex: 30m para 30 minutos, 1h para 1 hora, 2d para 2 dias (máx: 28d)",
            style=discord.TextStyle.short,
            required=True
        )
        self.add_item(self.duration_input)
        self.reason = ui.TextInput(
            label="Razão do Silenciamento",
            placeholder="Descreva o motivo do silenciamento...",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=500
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        reason_text = self.reason.value
        duration_str = self.duration_input.value

        if not self.target_member:
            await interaction.followup.send("Membro alvo não encontrado para silenciamento.", ephemeral=True)
            return

        # No need for permission checks here, they should be done in the command before showing the modal

        try:
            duration = parse_duration(duration_str)
            timeout_until = datetime.datetime.now(datetime.timezone.utc) + duration

            # Apply timeout
            await self.target_member.timeout(timeout_until, reason=reason_text)

            # Log the action
            success = False
            try:
                success = await self.db.execute_query(
                    adapt_query_placeholders("INSERT INTO moderation_logs (guild_id, action, target_id, moderator_id, reason, duration) VALUES (?, ?, ?, ?, ?, ?)"),
                    (interaction.guild.id, "timeout", self.target_member.id, interaction.user.id, reason_text, duration.total_seconds())
                )
            except Exception as e:
                logger.error(f"Erro ao registrar silenciamento no DB para {self.target_member.id}: {e}", exc_info=True)
                # Continue even if logging fails

            # Send notification embed to the channel where the command was used
            embed = discord.Embed(
                title="Usuário Silenciado",
                description=f"O usuário {self.target_member.mention} foi silenciado.",
                color=discord.Color.yellow()
            )
            embed.add_field(name="Moderador", value=interaction.user.mention, inline=True)
            embed.add_field(name="Razão", value=reason_text, inline=False)
            embed.add_field(name="Duração", value=str(duration), inline=True)
            embed.add_field(name="Silenciado Até", value=discord.utils.format_dt(timeout_until, 'F'), inline=False)
            embed.add_field(name="Canal do Silenciamento", value=self.target_channel.mention, inline=True)
            embed.set_footer(text=f"ID do Usuário: {self.target_member.id}")

            try:
                await self.target_channel.send(embed=embed)
                await interaction.followup.send(f"Usuário {self.target_member.mention} silenciado por {duration_str}!", ephemeral=True)
                logger.info(f"Silenciamento registrado para {self.target_member.id} por {interaction.user.id} na guild {interaction.guild.id} e enviado para {self.target_channel.name}. Razão: {reason_text}. Duração: {duration_str}")
            except discord.Forbidden:
                await interaction.followup.send(f"Não tenho permissão para enviar mensagens em {self.target_channel.mention}.", ephemeral=True)
                logger.error(f"Permissão negada ao enviar notificação de silenciamento para {self.target_channel.name} na guild {interaction.guild.id}.")
            except Exception as e:
                await interaction.followup.send(f"Ocorreu um erro ao enviar a notificação: {e}", ephemeral=True)
                logger.error(f"Erro ao enviar notificação de silenciamento para {self.target_channel.name}: {e}", exc_info=True)

            # Attempt to send DM
            try:
                dm_embed = discord.Embed(
                    title="Você foi Silenciado(a)!",
                    description=f"Você foi silenciado(a) no servidor **{interaction.guild.name}**.",
                    color=discord.Color.yellow()
                )
                dm_embed.add_field(name="Moderador", value=interaction.user.mention, inline=True)
                dm_embed.add_field(name="Razão", value=reason_text, inline=False)
                dm_embed.add_field(name="Duração", value=str(duration), inline=True)
                 # Use format_dt for the timestamp
                dm_embed.add_field(name="Silenciado Até", value=discord.utils.format_dt(timeout_until, 'F'), inline=False)
                dm_embed.set_footer(text="Por favor, revise as regras do servidor para evitar futuras ações.")
                await self.target_member.send(embed=dm_embed)
                logger.info(f"DM de silenciamento enviada para {self.target_member.id}.")
            except discord.Forbidden:
                logger.warning(f"Não foi possível enviar DM de silenciamento para {self.target_member.id}.")
            except Exception as e:
                logger.error(f"Erro ao enviar DM de silenciamento para {self.target_member.id}: {e}", exc_info=True)

        except ValueError as ve:
            await interaction.followup.send(f"Erro ao analisar a duração: {ve}", ephemeral=True)
            logger.warning(f"Falha ao analisar duração '{duration_str}' para silenciamento de {self.target_member.id}: {ve}")
        except discord.Forbidden:
             await interaction.followup.send("Não tenho permissão para silenciar este membro.", ephemeral=True)
             logger.error(f"Permissão negada ao silenciar {self.target_member.id} na guild {interaction.guild.id}.")
        except Exception as e:
             await interaction.followup.send(f"Ocorreu um erro ao silenciar o membro: {e}", ephemeral=True)
             logger.error(f"Erro inesperado ao silenciar {self.target_member.id}: {e}", exc_info=True)


# Assuming this is part of the ModerationCommands cog
class ModerationCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_connection = bot.db_connection # Armazena a conexão do banco de dados

    @app_commands.command(name="warn", description="Adverte um membro.")
    @app_commands.describe(member="O membro a ser advertido.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn(self, interaction: discord.Interaction, member: discord.Member):
         # Permission and target checks (already in the original code, keep them)
        if interaction.user.top_role <= member.top_role and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message("Você não pode advertir um membro com cargo igual ou superior ao seu.", ephemeral=True)
            return
        if member.id == interaction.user.id:
            await interaction.response.send_message("Você não pode advertir a si mesmo.", ephemeral=True)
            return
        if member.id == interaction.guild.owner_id:
            await interaction.response.send_message("Você não pode advertir o proprietário do servidor.", ephemeral=True)
            return
        if member.bot and not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Você não pode advertir um bot a menos que seja um administrador.", ephemeral=True)
            return
        if not interaction.guild.me.guild_permissions.moderate_members:
            await interaction.response.send_message("Não tenho permissão para advertir membros (moderate_members).", ephemeral=True)
            return

        await interaction.response.send_modal(WarnModal(member, interaction.channel, self.bot))


    @app_commands.command(name="kick", description="Expulsa um membro do servidor.")
    @app_commands.describe(member="O membro a ser expulso.")
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, member: discord.Member):
        # Permission and target checks (already in the original code, keep them)
        if not interaction.guild.me.guild_permissions.kick_members:
            await interaction.response.send_message("Não tenho permissão para expulsar membros.", ephemeral=True)
            return
        if interaction.user.top_role <= member.top_role and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message("Você não pode expulsar um membro com cargo igual ou superior ao seu.", ephemeral=True)
            return
        if member.id == interaction.user.id:
            await interaction.response.send_message("Você não pode expulsar a si mesmo.", ephemeral=True)
            return
        if member.id == interaction.guild.owner_id:
            await interaction.response.send_message("Você não pode expulsar o proprietário do servidor.", ephemeral=True)
            return
        if member.bot and not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Você não pode expulsar um bot a menos que seja um administrador.", ephemeral=True)
            return

        await interaction.response.send_modal(KickModal(member, interaction.channel, self.bot))


    @app_commands.command(name="ban", description="Bane um membro do servidor.")
    @app_commands.describe(member="O membro a ser banido.")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, member: discord.Member):
        # Permission and target checks (already in the original code, keep them)
        if not interaction.guild.me.guild_permissions.ban_members:
            await interaction.response.send_message("Não tenho permissão para banir membros.", ephemeral=True)
            return
        if interaction.user.top_role <= member.top_role and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message("Você não pode banir um membro com cargo igual ou superior ao seu.", ephemeral=True)
            return
        if member.id == interaction.user.id:
            await interaction.response.send_message("Você não pode banir a si mesmo.", ephemeral=True)
            return
        if member.id == interaction.guild.owner_id:
            await interaction.response.send_message("Você não pode banir o proprietário do servidor.", ephemeral=True)
            return
        if member.bot and not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Você não pode banir um bot a menos que seja um administrador.", ephemeral=True)
            return

        await interaction.response.send_modal(BanModal(member, interaction.channel, self.bot))


    @app_commands.command(name="mute", description="Silencia um membro por um tempo determinado.")
    @app_commands.describe(member="O membro a ser silenciado.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def mute(self, interaction: discord.Interaction, member: discord.Member):
        # Permission and target checks
        if interaction.user.top_role <= member.top_role and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message("Você não pode silenciar um membro com cargo igual ou superior ao seu.", ephemeral=True)
            return
        if member.id == interaction.user.id:
            await interaction.response.send_message("Você não pode silenciar a si mesmo.", ephemeral=True)
            return
        if member.id == interaction.guild.owner_id:
            await interaction.response.send_message("Você não pode silenciar o proprietário do servidor.", ephemeral=True)
            return
        if member.bot and not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Você não pode silenciar um bot a menos que seja um administrador.", ephemeral=True)
            return
        if not interaction.guild.me.guild_permissions.moderate_members:
            await interaction.response.send_message("Não tenho permissão para silenciar membros (moderate_members).", ephemeral=True)
            return
        
        # Show the MuteModal
        await interaction.response.send_modal(MuteModal(member, interaction.channel, self.bot))


    @app_commands.command(name="unmute", description="Remove o silenciamento de um membro.")
    @app_commands.describe(member="O membro a ter o silenciamento removido.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def unmute(self, interaction: discord.Interaction, member: discord.Member):
        # Permission and target checks
        if interaction.user.top_role <= member.top_role and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message("Você não pode remover o silenciamento de um membro com cargo igual ou superior ao seu.", ephemeral=True)
            return
        if member.id == interaction.user.id:
            await interaction.response.send_message("Você não pode remover o silenciamento de si mesmo.", ephemeral=True)
            return
        if member.id == interaction.guild.owner_id:
            await interaction.response.send_message("Você não pode remover o silenciamento do proprietário do servidor.", ephemeral=True)
            return
        if member.bot and not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Você não pode remover o silenciamento de um bot a menos que seja um administrador.", ephemeral=True)
            return
        if not interaction.guild.me.guild_permissions.moderate_members:
            await interaction.response.send_message("Não tenho permissão para remover silenciamento de membros (moderate_members).", ephemeral=True)
            return

        # Check if the member is actually timed out
        if not member.is_timed_out():
            await interaction.response.send_message(f"{member.mention} não está silenciado(a).", ephemeral=True)
            return
        
        # Show the UnmuteModal
        await interaction.response.send_modal(UnmuteModal(member, interaction.channel, self.bot))


class UnmuteModal(ui.Modal, title="Remover Silenciamento"):
    def __init__(self, target_member: discord.Member, target_channel: discord.TextChannel, bot_instance):
        super().__init__()
        self.target_member = target_member
        self.target_channel = target_channel
        self.bot = bot_instance # Armazena a instância do bot
        self.db = bot_instance.db_connection

        self.reason = ui.TextInput(
            label="Razão para remover o silenciamento",
            placeholder="Descreva o motivo da remoção...",
            style=discord.TextStyle.paragraph,
            required=False, # Reason is optional for unmute
            max_length=500
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        reason_text = self.reason.value if self.reason.value else "Nenhuma razão fornecida."

        if not self.target_member.is_timed_out():
             await interaction.followup.send(f"{self.target_member.mention} não está silenciado(a).", ephemeral=True)
             return

        try:
            # Remove timeout
            await self.target_member.timeout(None, reason=reason_text)

            # Log the action
            success = False
            try:
                success = await self.db.execute_query(
                    adapt_query_placeholders("INSERT INTO moderation_logs (guild_id, action, target_id, moderator_id, reason) VALUES (?, ?, ?, ?, ?)"),
                    (interaction.guild.id, "unmute", self.target_member.id, interaction.user.id, reason_text)
                )
            except Exception as e:
                logger.error(f"Erro ao registrar remoção de silenciamento no DB para {self.target_member.id}: {e}", exc_info=True)
                # Continue even if logging fails

            # Send notification embed to the channel where the command was used
            embed = discord.Embed(
                title="Silenciamento Removido",
                description=f"O silenciamento de {self.target_member.mention} foi removido.",
                color=discord.Color.green()
            )
            embed.add_field(name="Moderador", value=interaction.user.mention, inline=True)
            embed.add_field(name="Razão", value=reason_text, inline=False)
            embed.add_field(name="Canal da Notificação", value=self.target_channel.mention, inline=True)
            embed.set_footer(text=f"ID do Usuário: {self.target_member.id}")

            try:
                await self.target_channel.send(embed=embed)
                await interaction.followup.send(f"Silenciamento removido para {self.target_member.mention}!", ephemeral=True)
                logger.info(f"Silenciamento removido para {self.target_member.id} por {interaction.user.id} na guild {interaction.guild.id} e enviado para {self.target_channel.name}. Razão: {reason_text}")
            except discord.Forbidden:
                await interaction.followup.send(f"Não tenho permissão para enviar mensagens em {self.target_channel.mention}.", ephemeral=True)
                logger.error(f"Permissão negada ao enviar notificação de remoção de silenciamento para {self.target_channel.name} na guild {interaction.guild.id}.")
            except Exception as e:
                await interaction.followup.send(f"Ocorreu um erro ao enviar a notificação: {e}", ephemeral=True)
                logger.error(f"Erro ao enviar notificação de remoção de silenciamento para {self.target_channel.name}: {e}", exc_info=True)

            # Attempt to send DM
            try:
                dm_embed = discord.Embed(
                    title="Seu Silenciamento Foi Removido!",
                    description=f"Seu silenciamento no servidor **{interaction.guild.name}** foi removido.",
                    color=discord.Color.green()
                )
                dm_embed.add_field(name="Razão", value=reason_text, inline=False)
                dm_embed.add_field(name="Moderador", value=interaction.user.mention, inline=True)
                dm_embed.set_footer(text="Você agora pode falar no servidor novamente.")
                await self.target_member.send(embed=dm_embed)
                logger.info(f"DM de remoção de silenciamento enviada para {self.target_member.id}.")
            except discord.Forbidden:
                logger.warning(f"Não foi possível enviar DM de remoção de silenciamento para {self.target_member.id}.")
            except Exception as e:
                logger.error(f"Erro ao enviar DM de remoção de silenciamento para {self.target_member.id}: {e}", exc_info=True)

        except discord.Forbidden:
             await interaction.followup.send("Não tenho permissão para remover o silenciamento deste membro.", ephemeral=True)
             logger.error(f"Permissão negada ao remover silenciamento de {self.target_member.id} na guild {interaction.guild.id}.")
        except Exception as e:
             await interaction.followup.send(f"Ocorreu um erro ao remover o silenciamento: {e}", ephemeral=True)
             logger.error(f"Erro inesperado ao remover silenciamento de {self.target_member.id}: {e}", exc_info=True)


async def setup(bot):
    await bot.add_cog(ModerationCommands(bot))