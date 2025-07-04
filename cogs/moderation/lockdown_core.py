import discord
from discord.ext import commands, tasks
import datetime
import time
import logging
import re

# Não precisamos importar execute_query diretamente, pois usaremos self.db.
# from database import execute_query 

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def parse_duration(duration_str: str) -> datetime.timedelta:
    """Converte uma string de duração (ex: '30m', '1h') em um timedelta."""
    seconds = 0
    if not duration_str:
        raise ValueError("Duração não pode ser vazia.")
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
    if seconds > 2419200: # 28 dias em segundos
        raise ValueError("A duração máxima para silenciamento é de 28 dias.")
    return datetime.timedelta(seconds=seconds)


class LockdownCore(commands.Cog):
    def __init__(self, bot: commands.Bot): # db_manager removido daqui
        self.bot = bot
        self.db = bot.db_connection # Armazena a instância do gerenciador de DB
        self.lockdown_check.start()
        logging.info("LockdownCore cog inicializado.")

    def cog_unload(self):
        self.lockdown_check.cancel()
        logging.info("LockdownCore cog descarregado.")

    async def _is_channel_locked(self, channel_id: int) -> bool:
        """Verifica se um canal está em lockdown no DB."""
        try:
            result = await self.db.fetch_one( # Usando self.db.fetch_one
                "SELECT channel_id FROM locked_channels WHERE channel_id = ?",
                (channel_id,)
            )
            return result is not None
        except Exception as e:
            logging.error(f"Erro ao verificar status de lockdown no DB para canal {channel_id}: {e}", exc_info=True)
            return False

    async def _toggle_lockdown(self, channel: discord.TextChannel, lock: bool, reason: str = "Não especificado", locked_by: discord.Member = None, duration_seconds: int = None):
        """
        Alterna o estado de lockdown de um canal e atualiza o banco de dados.
        """
        everyone_role = channel.guild.default_role
        bot_member = channel.guild.me

        # Verifica as permissões do bot antes de tentar modificar o canal
        if not (channel.permissions_for(bot_member).manage_roles or channel.permissions_for(bot_member).manage_channels):
            logging.error(f"Bot sem permissão 'Gerenciar Cargos' ou 'Gerenciar Canais' para alterar permissões em #{channel.name} ({channel.id}).")
            return False, "Erro: Bot sem permissões necessárias ('Gerenciar Cargos' ou 'Gerenciar Canais') para modificar este canal."

        if lock:
            current_perms = channel.overwrites_for(everyone_role) # Obter as permissões atuais
            current_perms.send_messages = False
            
            db_query = "INSERT OR REPLACE INTO locked_channels (channel_id, guild_id, locked_until_timestamp, reason, locked_by_id) VALUES (?, ?, ?, ?, ?)"
            locked_until = None
            if duration_seconds:
                locked_until = int(time.time()) + duration_seconds
            
            db_success = False
            try:
                db_success = await self.db.execute_query(db_query, (channel.id, channel.guild.id, locked_until, reason, locked_by.id if locked_by else None)) # Usando self.db
            except Exception as e:
                logging.error(f"Falha ao registrar lockdown no DB para canal #{channel.name} ({channel.id}): {e}", exc_info=True)

            if not db_success:
                logging.error(f"Falha ao registrar lockdown no DB para canal #{channel.name} ({channel.id}).")
                return False, "Erro no banco de dados ao registrar lockdown."
            
            status_message = "bloqueado"
            log_message = f"Lockdown ativado em #{channel.name} ({channel.id}) por {locked_by.name if locked_by else 'Desconhecido'}. Razão: '{reason}'. Duração: {duration_seconds}s"
        else:
            current_perms = channel.overwrites_for(everyone_role) # Obter as permissões atuais
            current_perms.send_messages = None # Reseta para o estado neutro, permitindo que as permissões do servidor prevaleçam
            
            db_query = "DELETE FROM locked_channels WHERE channel_id = ?"
            db_success = False
            try:
                db_success = await self.db.execute_query(db_query, (channel.id,)) # Usando self.db
            except Exception as e:
                logging.error(f"Falha ao remover lockdown do DB para canal #{channel.name} ({channel.id}): {e}", exc_info=True)

            if not db_success:
                logging.error(f"Falha ao remover lockdown do DB para canal #{channel.name} ({channel.id}).")
                return False, "Erro no banco de dados ao remover lockdown."
            
            status_message = "desbloqueado"
            log_message = f"Lockdown desativado em #{channel.name} ({channel.id})."

        try:
            await channel.set_permissions(everyone_role, overwrite=current_perms, reason=reason)
            logging.info(log_message)
            return True, status_message
        except discord.Forbidden:
            logging.error(f"Bot sem permissão para mudar as permissões em #{channel.name} ({channel.id}). Certifique-se de que o bot tem 'Gerenciar Cargos' ou 'Gerenciar Canais' e que seu cargo está acima de @everyone.", exc_info=True)
            return False, "Erro: Não tenho permissão para modificar as permissões deste canal. Verifique as permissões 'Gerenciar Cargos' e 'Gerenciar Canais' para o cargo do bot e a hierarquia de cargos."
        except Exception as e:
            logging.error(f"Erro inesperado ao alternar lockdown em #{channel.name} ({channel.id}): {e}", exc_info=True)
            return False, f"Erro interno: {e}" 

    async def _send_lockdown_message(self, channel: discord.TextChannel, is_locked: bool, reason: str, duration_seconds: int = None):
        """Envia uma mensagem informativa sobre o estado de lockdown."""
        embed = discord.Embed()
        if is_locked:
            embed.title = "🔒 Canal Bloqueado"
            embed.description = f"Este canal foi bloqueado. Ninguém pode enviar mensagens aqui."
            embed.color = discord.Color.red()
            if reason:
                embed.add_field(name="Motivo", value=reason, inline=False)
            if duration_seconds:
                duration_str = str(datetime.timedelta(seconds=duration_seconds))
                embed.add_field(name="Duração", value=f"Por `{duration_str}`", inline=False)
            embed.set_footer(text="Aguarde até ser desbloqueado por um moderador ou automaticamente.")
        else:
            embed.title = "🔓 Canal Desbloqueado"
            embed.description = "Este canal foi desbloqueado! Agora você pode enviar mensagens novamente."
            embed.color = discord.Color.green()
            if reason:
                embed.add_field(name="Motivo do desbloqueio", value=reason, inline=False)
            embed.set_footer(text="Obrigado pela paciência!")

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            logging.error(f"Bot sem permissão para enviar mensagem em #{channel.name} ({channel.id}).")
        except Exception as e:
            logging.error(f"Erro ao enviar mensagem de lockdown/desbloqueio em #{channel.name} ({channel.id}): {e}", exc_info=True)

    @tasks.loop(minutes=1)
    async def lockdown_check(self):
        await self.bot.wait_until_ready()

        current_time = int(time.time())
        expired_lockdowns = []
        try:
            expired_lockdowns = await self.db.fetch_all( # Usando self.db.fetch_all
                "SELECT channel_id, guild_id, reason FROM locked_channels WHERE locked_until_timestamp IS NOT NULL AND locked_until_timestamp <= ?",
                (current_time,)
            )
        except Exception as e:
            logging.error(f"Erro ao buscar lockdowns expirados do DB: {e}", exc_info=True)
            return # Não continua se houver erro no DB

        if expired_lockdowns:
            logging.info(f"Encontrados {len(expired_lockdowns)} canais com lockdown expirado.")
            for channel_id, guild_id, reason in expired_lockdowns:
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    logging.warning(f"Guild {guild_id} não encontrada para lockdown expirado do canal {channel_id}. Removendo do DB.")
                    try:
                        await self.db.execute_query("DELETE FROM locked_channels WHERE channel_id = ?", (channel_id,)) # Usando self.db
                    except Exception as e:
                        logging.error(f"Erro ao remover canal {channel_id} do DB após guild não encontrada: {e}", exc_info=True)
                    continue

                channel = guild.get_channel(channel_id)
                if not channel or not isinstance(channel, discord.TextChannel):
                    logging.warning(f"Canal {channel_id} não encontrado ou não é de texto para lockdown expirado na guild {guild_id}. Removendo do DB.")
                    try:
                        await self.db.execute_query("DELETE FROM locked_channels WHERE channel_id = ?", (channel_id,)) # Usando self.db
                    except Exception as e:
                        logging.error(f"Erro ao remover canal {channel_id} do DB após canal não encontrado: {e}", exc_info=True)
                    continue
                
                logging.info(f"Desbloqueando canal {channel.name} ({channel.id}) automaticamente.")
                success, _ = await self._toggle_lockdown(channel, False, f"Lockdown automático expirado. Motivo original: {reason}")
                if success:
                    await self._send_lockdown_message(channel, False, f"Lockdown automático expirado.")


    @lockdown_check.before_loop
    async def before_lockdown_check(self):
        await self.bot.wait_until_ready()
        logging.info("Iniciando verificação de lockdown persistente...")
        all_locked_channels = []
        try:
            all_locked_channels = await self.db.fetch_all( # Usando self.db.fetch_all
                "SELECT channel_id, guild_id, reason, locked_by_id, locked_until_timestamp FROM locked_channels"
            )
        except Exception as e:
            logging.error(f"Erro ao buscar lockdowns persistentes do DB no carregamento: {e}", exc_info=True)
            return # Não continua se houver erro no DB

        if all_locked_channels:
            logging.info(f"Encontrados {len(all_locked_channels)} canais com lockdown persistente no DB.")
            for channel_id, guild_id, reason, locked_by_id, locked_until_timestamp in all_locked_channels:
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    logging.warning(f"Guild {guild_id} não encontrada para canal {channel_id} no carregamento. Removendo do DB.")
                    try:
                        await self.db.execute_query("DELETE FROM locked_channels WHERE channel_id = ?", (channel_id,)) # Usando self.db
                    except Exception as e:
                        logging.error(f"Erro ao remover canal {channel_id} do DB após guild não encontrada no carregamento: {e}", exc_info=True)
                    continue

                channel = guild.get_channel(channel_id)
                if not channel or not isinstance(channel, discord.TextChannel):
                    logging.warning(f"Canal {channel_id} não encontrado ou não é de texto no carregamento para guild {guild_id}. Removendo do DB.")
                    try:
                        await self.db.execute_query("DELETE FROM locked_channels WHERE channel_id = ?", (channel_id,)) # Usando self.db
                    except Exception as e:
                        logging.error(f"Erro ao remover canal {channel_id} do DB após canal não encontrado no carregamento: {e}", exc_info=True)
                    continue
                
                # Se o lockdown já expirou na hora do carregamento, desbloqueia e remove do DB
                if locked_until_timestamp and locked_until_timestamp <= int(time.time()):
                    logging.info(f"Lockdown para canal {channel.name} ({channel.id}) já expirou no carregamento. Desbloqueando.")
                    await self._toggle_lockdown(channel, False, f"Lockdown expirado na reinicialização do bot. Motivo original: {reason}")
                else:
                    logging.info(f"Aplicando lockdown persistente em #{channel.name} ({channel.id}).")
                    # Recalcula a duração restante para passar para _toggle_lockdown, se houver
                    remaining_duration = (locked_until_timestamp - int(time.time())) if locked_until_timestamp else None
                    success, _ = await self._toggle_lockdown(
                        channel, 
                        True, 
                        reason, 
                        guild.get_member(locked_by_id) if locked_by_id else None, 
                        remaining_duration
                    )
                    if not success:
                        logging.error(f"Falha ao aplicar lockdown persistente em #{channel.name} ({channel.id}).")
        else:
            logging.info("Nenhum canal em lockdown persistente para carregar.")


async def setup(bot: commands.Bot): # db_manager removido daqui
    """
    Função de setup para adicionar o cog ao bot.
    """
    await bot.add_cog(LockdownCore(bot)) # db_manager removido daqui
    logging.info("LockdownCore cog adicionado ao bot.")
