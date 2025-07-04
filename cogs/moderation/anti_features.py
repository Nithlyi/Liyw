import discord
from discord.ext import commands
from discord import app_commands, ui
import logging
import json
import asyncio

logger = logging.getLogger(__name__)

# --- Funções Auxiliares para Embeds (Reutilizadas) ---
def _create_embed_from_data(embed_data: dict, member: discord.Member = None, guild: discord.Guild = None):
    """Cria um discord.Embed a partir de um dicionário de dados, formatando variáveis."""
    embed = discord.Embed()
    
    if embed_data.get('title'):
        embed.title = embed_data['title'].format(
            member=member,
            guild=guild,
            member_name=member.display_name if member else 'N/A',
            member_count=guild.member_count if guild else 'N/A'
        )
    else:
        embed.title = ""

    if embed_data.get('description'):
        embed.description = embed_data['description'].format(
            member=member,
            guild=guild,
            member_name=member.display_name if member else 'N/A',
            member_count=guild.member_count if guild else 'N/A'
        )
    else:
        embed.description = ""
    
    if embed_data.get('color') is not None:
        try:
            color_value = embed_data['color']
            if isinstance(color_value, str):
                color_str = color_value.strip()
                if color_str.startswith('#'):
                    embed.color = discord.Color(int(color_str[1:], 16))
                elif color_str.startswith('0x'):
                    embed.color = discord.Color(int(color_str, 16))
                else:
                    embed.color = discord.Color(int(color_str))
            elif isinstance(color_value, int):
                embed.color = discord.Color(color_value)
        except (ValueError, TypeError):
            logging.warning(f"Cor inválida no embed: {embed_data.get('color')}. Usando cor padrão.")
            embed.color = discord.Color.default()
    else:
        embed.color = discord.Color.default()

    if embed_data.get('image_url'):
        embed.set_image(url=embed_data['image_url'])
    
    if embed_data.get('thumbnail_url'):
        embed.set_thumbnail(url=embed_data['thumbnail_url'])

    if embed_data.get('footer_text'):
        embed.set_footer(text=embed_data['footer_text'].format(
            member=member,
            guild=guild,
            member_name=member.display_name if member else 'N/A',
            member_count=guild.member_count if guild else 'N/A'
        ), icon_url=embed_data.get('footer_icon_url'))

    if embed_data.get('author_name'):
        embed.set_author(name=embed_data['author_name'].format(
            member=member,
            guild=guild,
            member_name=member.display_name if member else 'N/A',
            member_count=guild.member_count if guild else 'N/A'
        ), icon_url=embed_data.get('author_icon_url'))
    
    if 'fields' in embed_data:
        for field in embed_data['fields']:
            field_name = str(field.get('name', ''))
            field_value = str(field.get('value', ''))
            embed.add_field(name=field_name, value=field_value, inline=field.get('inline', False))

    return embed

# --- Configurações Padrão para os Recursos Anti ---
DEFAULT_ANTI_SPAM_CONFIG = {
    "enabled": False,
    "threshold": 5, # Mensagens em um período
    "time_window_seconds": 5, # Período em segundos
    "action": "delete", # "delete", "mute", "kick", "ban"
    "mute_duration_minutes": 5, # Se a ação for mute
    "warn_message": "Por favor, não faça spam!",
    "log_channel_id": None
}

DEFAULT_ANTI_LINK_CONFIG = {
    "enabled": False,
    "action": "delete", # "delete", "warn", "mute", "kick", "ban"
    "allowed_channels": [], # Lista de IDs de canais onde links são permitidos
    "allowed_roles": [], # Lista de IDs de cargos que podem enviar links
    "warn_message": "Links não são permitidos aqui!",
    "log_channel_id": None
}

DEFAULT_ANTI_INVITE_CONFIG = {
    "enabled": False,
    "action": "delete", # "delete", "warn", "mute", "kick", "ban"
    "allowed_channels": [],
    "allowed_roles": [],
    "warn_message": "Convites de outros servidores não são permitidos!",
    "log_channel_id": None
}

DEFAULT_ANTI_FLOOD_CONFIG = {
    "enabled": False,
    "message_count": 10, # Mensagens em um período
    "time_window_seconds": 10, # Período em segundos
    "action": "warn", # "warn", "mute", "kick", "ban"
    "mute_duration_minutes": 10,
    "warn_message": "Por favor, diminua a velocidade de suas mensagens (flood detectado)!",
    "log_channel_id": None
}

# --- Modals de Configuração ---

class AntiSpamConfigModal(ui.Modal, title="Configurar Anti-Spam"):
    def __init__(self, bot: commands.Bot, guild_id: int, current_config: dict):
        super().__init__()
        self.bot = bot
        self.guild_id = guild_id
        self.current_config = current_config

        self.enabled = ui.TextInput(label="Ativar Anti-Spam (True/False)", default=str(current_config.get("enabled", False)), required=True, max_length=5)
        self.threshold = ui.TextInput(label="Limite de Mensagens (Ex: 5)", default=str(current_config.get("threshold", 5)), required=True, max_length=3)
        self.time_window = ui.TextInput(label="Janela de Tempo (segundos, Ex: 5)", default=str(current_config.get("time_window_seconds", 5)), required=True, max_length=3)
        self.action = ui.TextInput(label="Ação (delete, warn, mute, kick, ban)", default=current_config.get("action", "delete"), required=True, max_length=10)
        self.mute_duration = ui.TextInput(label="Duração Mute (minutos, se ação for mute)", default=str(current_config.get("mute_duration_minutes", 5)), required=False, max_length=4)
        
        self.add_item(self.enabled)
        self.add_item(self.threshold)
        self.add_item(self.time_window)
        self.add_item(self.action)
        self.add_item(self.mute_duration)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            new_config = {
                "enabled": self.enabled.value.lower() == 'true',
                "threshold": int(self.threshold.value),
                "time_window_seconds": int(self.time_window.value),
                "action": self.action.value.lower(),
                "mute_duration_minutes": int(self.mute_duration.value) if self.mute_duration.value else 0,
                "warn_message": self.current_config.get("warn_message", DEFAULT_ANTI_SPAM_CONFIG["warn_message"]),
                "log_channel_id": self.current_config.get("log_channel_id", DEFAULT_ANTI_SPAM_CONFIG["log_channel_id"])
            }
            await self.bot.db_connection.execute_query(
                "INSERT OR IGNORE INTO anti_features_settings (guild_id) VALUES (?)", (self.guild_id,)
            )
            await self.bot.db_connection.execute_query(
                "UPDATE anti_features_settings SET anti_spam_config_json = ? WHERE guild_id = ?",
                (json.dumps(new_config), self.guild_id)
            )
            await interaction.followup.send("Configurações de Anti-Spam salvas com sucesso!", ephemeral=True)

            # --- Lógica para atualizar o painel principal ---
            # Acessa a instância da cog e, através dela, a instância da AntiFeaturesControlView
            anti_features_cog = self.bot.get_cog("AntiFeatures")
            if anti_features_cog and anti_features_cog.control_view:
                await anti_features_cog.control_view._update_panel_embed(interaction)
            else:
                logger.warning("Não foi possível encontrar a cog AntiFeatures ou a control_view para atualizar o painel.")

        except ValueError:
            await interaction.followup.send("Entrada inválida. Verifique os valores numéricos e booleanos.", ephemeral=True)
        except Exception as e:
            logger.error(f"Erro ao salvar config de Anti-Spam para guild {self.guild_id}: {e}", exc_info=True)
            await interaction.followup.send(f"Ocorreu um erro ao salvar as configurações: {e}", ephemeral=True)

class AntiLinkConfigModal(ui.Modal, title="Configurar Anti-Link"):
    def __init__(self, bot: commands.Bot, guild_id: int, current_config: dict):
        super().__init__()
        self.bot = bot
        self.guild_id = guild_id
        self.current_config = current_config

        self.enabled = ui.TextInput(label="Ativar Anti-Link (True/False)", default=str(current_config.get("enabled", False)), required=True, max_length=5)
        self.action = ui.TextInput(label="Ação (delete, warn, mute, kick, ban)", default=current_config.get("action", "delete"), required=True, max_length=10)
        self.allowed_channels = ui.TextInput(label="Canais Permitidos (IDs separados por vírgula)", default=",".join(map(str, current_config.get("allowed_channels", []))), required=False, max_length=200)
        self.allowed_roles = ui.TextInput(label="Cargos Permitidos (IDs separados por vírgula)", default=",".join(map(str, current_config.get("allowed_roles", []))), required=False, max_length=200)
        
        self.add_item(self.enabled)
        self.add_item(self.action)
        self.add_item(self.allowed_channels)
        self.add_item(self.allowed_roles)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            allowed_channels_list = [int(x.strip()) for x in self.allowed_channels.value.split(',') if x.strip()]
            allowed_roles_list = [int(x.strip()) for x in self.allowed_roles.value.split(',') if x.strip()]

            new_config = {
                "enabled": self.enabled.value.lower() == 'true',
                "action": self.action.value.lower(),
                "allowed_channels": allowed_channels_list,
                "allowed_roles": allowed_roles_list,
                "warn_message": self.current_config.get("warn_message", DEFAULT_ANTI_LINK_CONFIG["warn_message"]),
                "log_channel_id": self.current_config.get("log_channel_id", DEFAULT_ANTI_LINK_CONFIG["log_channel_id"])
            }
            await self.bot.db_connection.execute_query(
                "INSERT OR IGNORE INTO anti_features_settings (guild_id) VALUES (?)", (self.guild_id,)
            )
            await self.bot.db_connection.execute_query(
                "UPDATE anti_features_settings SET anti_link_config_json = ? WHERE guild_id = ?",
                (json.dumps(new_config), self.guild_id)
            )
            await interaction.followup.send("Configurações de Anti-Link salvas com sucesso!", ephemeral=True)

            # --- Lógica para atualizar o painel principal ---
            anti_features_cog = self.bot.get_cog("AntiFeatures")
            if anti_features_cog and anti_features_cog.control_view:
                await anti_features_cog.control_view._update_panel_embed(interaction)
            else:
                logger.warning("Não foi possível encontrar a cog AntiFeatures ou a control_view para atualizar o painel.")

        except ValueError:
            await interaction.followup.send("Entrada inválida. Verifique os valores booleanos e IDs numéricos.", ephemeral=True)
        except Exception as e:
            logger.error(f"Erro ao salvar config de Anti-Link para guild {self.guild_id}: {e}", exc_info=True)
            await interaction.followup.send(f"Ocorreu um erro ao salvar as configurações: {e}", ephemeral=True)

class AntiInviteConfigModal(ui.Modal, title="Configurar Anti-Convite"):
    def __init__(self, bot: commands.Bot, guild_id: int, current_config: dict):
        super().__init__()
        self.bot = bot
        self.guild_id = guild_id
        self.current_config = current_config

        self.enabled = ui.TextInput(label="Ativar Anti-Convite (True/False)", default=str(current_config.get("enabled", False)), required=True, max_length=5)
        self.action = ui.TextInput(label="Ação (delete, warn, mute, kick, ban)", default=current_config.get("action", "delete"), required=True, max_length=10)
        self.allowed_channels = ui.TextInput(label="Canais Permitidos (IDs separados por vírgula)", default=",".join(map(str, current_config.get("allowed_channels", []))), required=False, max_length=200)
        self.allowed_roles = ui.TextInput(label="Cargos Permitidos (IDs separados por vírgula)", default=",".join(map(str, current_config.get("allowed_roles", []))), required=False, max_length=200)
        
        self.add_item(self.enabled)
        self.add_item(self.action)
        self.add_item(self.allowed_channels)
        self.add_item(self.allowed_roles)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            allowed_channels_list = [int(x.strip()) for x in self.allowed_channels.value.split(',') if x.strip()]
            allowed_roles_list = [int(x.strip()) for x in self.allowed_roles.value.split(',') if x.strip()]

            new_config = {
                "enabled": self.enabled.value.lower() == 'true',
                "action": self.action.value.lower(),
                "allowed_channels": allowed_channels_list,
                "allowed_roles": allowed_roles_list,
                "warn_message": self.current_config.get("warn_message", DEFAULT_ANTI_INVITE_CONFIG["warn_message"]),
                "log_channel_id": self.current_config.get("log_channel_id", DEFAULT_ANTI_INVITE_CONFIG["log_channel_id"])
            }
            await self.bot.db_connection.execute_query(
                "INSERT OR IGNORE INTO anti_features_settings (guild_id) VALUES (?)", (self.guild_id,)
            )
            await self.bot.db_connection.execute_query(
                "UPDATE anti_features_settings SET anti_invite_config_json = ? WHERE guild_id = ?",
                (json.dumps(new_config), self.guild_id)
            )
            await interaction.followup.send("Configurações de Anti-Convite salvas com sucesso!", ephemeral=True)

            # --- Lógica para atualizar o painel principal ---
            anti_features_cog = self.bot.get_cog("AntiFeatures")
            if anti_features_cog and anti_features_cog.control_view:
                await anti_features_cog.control_view._update_panel_embed(interaction)
            else:
                logger.warning("Não foi possível encontrar a cog AntiFeatures ou a control_view para atualizar o painel.")

        except ValueError:
            await interaction.followup.send("Entrada inválida. Verifique os valores booleanos e IDs numéricos.", ephemeral=True)
        except Exception as e:
            logger.error(f"Erro ao salvar config de Anti-Convite para guild {self.guild_id}: {e}", exc_info=True)
            await interaction.followup.send(f"Ocorreu um erro ao salvar as configurações: {e}", ephemeral=True)

class AntiFloodConfigModal(ui.Modal, title="Configurar Anti-Flood"):
    def __init__(self, bot: commands.Bot, guild_id: int, current_config: dict):
        super().__init__()
        self.bot = bot
        self.guild_id = guild_id
        self.current_config = current_config

        self.enabled = ui.TextInput(label="Ativar Anti-Flood (True/False)", default=str(current_config.get("enabled", False)), required=True, max_length=5)
        self.message_count = ui.TextInput(label="Contagem de Mensagens (Ex: 10)", default=str(current_config.get("message_count", 10)), required=True, max_length=3)
        self.time_window = ui.TextInput(label="Janela de Tempo (segundos, Ex: 10)", default=str(current_config.get("time_window_seconds", 10)), required=True, max_length=3)
        self.action = ui.TextInput(label="Ação (warn, mute, kick, ban)", default=current_config.get("action", "warn"), required=True, max_length=10)
        self.mute_duration = ui.TextInput(label="Duração Mute (minutos, se ação for mute)", default=str(current_config.get("mute_duration_minutes", 10)), required=False, max_length=4)
        
        self.add_item(self.enabled)
        self.add_item(self.message_count)
        self.add_item(self.time_window)
        self.add_item(self.action)
        self.add_item(self.mute_duration)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            new_config = {
                "enabled": self.enabled.value.lower() == 'true',
                "message_count": int(self.message_count.value),
                "time_window_seconds": int(self.time_window.value),
                "action": self.action.value.lower(),
                "mute_duration_minutes": int(self.mute_duration.value) if self.mute_duration.value else 0,
                "warn_message": self.current_config.get("warn_message", DEFAULT_ANTI_FLOOD_CONFIG["warn_message"]),
                "log_channel_id": self.current_config.get("log_channel_id", DEFAULT_ANTI_FLOOD_CONFIG["log_channel_id"])
            }
            await self.bot.db_connection.execute_query(
                "INSERT OR IGNORE INTO anti_features_settings (guild_id) VALUES (?)", (self.guild_id,)
            )
            await self.bot.db_connection.execute_query(
                "UPDATE anti_features_settings SET anti_flood_config_json = ? WHERE guild_id = ?",
                (json.dumps(new_config), self.guild_id)
            )
            await interaction.followup.send("Configurações de Anti-Flood salvas com sucesso!", ephemeral=True)

            # --- Lógica para atualizar o painel principal ---
            anti_features_cog = self.bot.get_cog("AntiFeatures")
            if anti_features_cog and anti_features_cog.control_view:
                await anti_features_cog.control_view._update_panel_embed(interaction)
            else:
                logger.warning("Não foi possível encontrar a cog AntiFeatures ou a control_view para atualizar o painel.")

        except ValueError:
            await interaction.followup.send("Entrada inválida. Verifique os valores numéricos e booleanos.", ephemeral=True)
        except Exception as e:
            logger.error(f"Erro ao salvar config de Anti-Flood para guild {self.guild_id}: {e}", exc_info=True)
            await interaction.followup.send(f"Ocorreu um erro ao salvar as configurações: {e}", ephemeral=True)


# --- View Principal do Painel de Anti-Recursos ---
class AntiFeaturesControlView(ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None) # View persistente
        self.bot = bot

    async def _get_guild_config(self, guild_id: int):
        """Busca as configurações JSON para um guild_id."""
        settings = await self.bot.db_connection.fetch_one(
            "SELECT anti_spam_config_json, anti_link_config_json, anti_invite_config_json, anti_flood_config_json FROM anti_features_settings WHERE guild_id = ?",
            (guild_id,)
        )
        configs = {
            "anti_spam": DEFAULT_ANTI_SPAM_CONFIG.copy(),
            "anti_link": DEFAULT_ANTI_LINK_CONFIG.copy(),
            "anti_invite": DEFAULT_ANTI_INVITE_CONFIG.copy(),
            "anti_flood": DEFAULT_ANTI_FLOOD_CONFIG.copy()
        }

        if settings:
            for key, default_config in zip(
                ["anti_spam", "anti_link", "anti_invite", "anti_flood"],
                [DEFAULT_ANTI_SPAM_CONFIG, DEFAULT_ANTI_LINK_CONFIG, DEFAULT_ANTI_INVITE_CONFIG, DEFAULT_ANTI_FLOOD_CONFIG]
            ):
                json_data = settings[f"{key}_config_json"]
                if json_data:
                    try:
                        loaded_config = json.loads(json_data)
                        # Atualiza com os valores padrão para garantir que todas as chaves existam
                        configs[key].update(loaded_config)
                    except json.JSONDecodeError:
                        logger.error(f"Erro ao decodificar JSON para {key} na guild {guild_id}. Usando padrão.")
        return configs

    async def _update_panel_embed(self, interaction: discord.Interaction):
        """Atualiza o embed do painel para refletir o status atual das configurações."""
        configs = await self._get_guild_config(interaction.guild_id)

        embed = discord.Embed(
            title="Painel de Controle Anti-Recursos",
            description="Configure as proteções anti-spam, anti-link, anti-convite e anti-flood do servidor.",
            color=discord.Color.dark_red()
        )

        embed.add_field(
            name="Anti-Spam",
            value=f"Status: **{'Ativado' if configs['anti_spam']['enabled'] else 'Desativado'}**\n"
                  f"Limite: {configs['anti_spam']['threshold']} msgs/{configs['anti_spam']['time_window_seconds']}s\n"
                  f"Ação: {configs['anti_spam']['action'].capitalize()}",
            inline=False
        )
        embed.add_field(
            name="Anti-Link",
            value=f"Status: **{'Ativado' if configs['anti_link']['enabled'] else 'Desativado'}**\n"
                  f"Ação: {configs['anti_link']['action'].capitalize()}",
            inline=False
        )
        embed.add_field(
            name="Anti-Convite",
            value=f"Status: **{'Ativado' if configs['anti_invite']['enabled'] else 'Desativado'}**\n"
                  f"Ação: {configs['anti_invite']['action'].capitalize()}",
            inline=False
        )
        embed.add_field(
            name="Anti-Flood",
            value=f"Status: **{'Ativado' if configs['anti_flood']['enabled'] else 'Desativado'}**\n"
                  f"Limite: {configs['anti_flood']['message_count']} msgs/{configs['anti_flood']['time_window_seconds']}s\n"
                  f"Ação: {configs['anti_flood']['action'].capitalize()}",
            inline=False
        )
        
        # Tenta editar a mensagem original do painel
        try:
            panel_settings = await self.bot.db_connection.fetch_one(
                "SELECT panel_channel_id, panel_message_id FROM anti_features_settings WHERE guild_id = ?",
                (interaction.guild_id,)
            )
            if panel_settings and panel_settings['panel_channel_id'] and panel_settings['panel_message_id']:
                channel = self.bot.get_channel(panel_settings['panel_channel_id'])
                if channel:
                    message = await channel.fetch_message(panel_settings['panel_message_id'])
                    await message.edit(embed=embed, view=self)
        except Exception as e:
            logger.error(f"Erro ao atualizar embed do painel Anti-Recursos na guild {interaction.guild_id}: {e}", exc_info=True)


    @ui.button(label="Configurar Anti-Spam", style=discord.ButtonStyle.primary, custom_id="anti_spam_config")
    async def anti_spam_button(self, interaction: discord.Interaction, button: ui.Button):
        configs = await self._get_guild_config(interaction.guild_id)
        modal = AntiSpamConfigModal(self.bot, interaction.guild_id, configs["anti_spam"])
        await interaction.response.send_modal(modal)
        # Removido: await asyncio.sleep(1) e await self._update_panel_embed(interaction)
        # A atualização será feita pelo on_submit do modal.


    @ui.button(label="Configurar Anti-Link", style=discord.ButtonStyle.primary, custom_id="anti_link_config")
    async def anti_link_button(self, interaction: discord.Interaction, button: ui.Button):
        configs = await self._get_guild_config(interaction.guild_id)
        modal = AntiLinkConfigModal(self.bot, interaction.guild_id, configs["anti_link"])
        await interaction.response.send_modal(modal)
        # Removido: await asyncio.sleep(1) e await self._update_panel_embed(interaction)

    @ui.button(label="Configurar Anti-Convite", style=discord.ButtonStyle.primary, custom_id="anti_invite_config")
    async def anti_invite_button(self, interaction: discord.Interaction, button: ui.Button):
        configs = await self._get_guild_config(interaction.guild_id)
        modal = AntiInviteConfigModal(self.bot, interaction.guild_id, configs["anti_invite"])
        await interaction.response.send_modal(modal)
        # Removido: await asyncio.sleep(1) e await self._update_panel_embed(interaction)

    @ui.button(label="Configurar Anti-Flood", style=discord.ButtonStyle.primary, custom_id="anti_flood_config")
    async def anti_flood_button(self, interaction: discord.Interaction, button: ui.Button):
        configs = await self._get_guild_config(interaction.guild_id)
        modal = AntiFloodConfigModal(self.bot, interaction.guild_id, configs["anti_flood"])
        await interaction.response.send_modal(modal)
        # Removido: await asyncio.sleep(1) e await self._update_panel_embed(interaction)


class AntiFeatures(commands.Cog):
    anti_features_group = app_commands.Group(name="antifeatures", description="Comandos para gerenciar recursos anti-spam/link/flood.")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Armazena a instância da View persistente como um atributo da cog
        self.control_view = AntiFeaturesControlView(bot=self.bot)
        self.bot.add_view(self.control_view)

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Verificando painéis persistentes de Anti-Recursos...")
        # Busca todos os painéis de anti-recursos configurados em todos os servidores
        all_panel_settings = await self.bot.db_connection.fetch_all(
            "SELECT guild_id, panel_channel_id, panel_message_id FROM anti_features_settings WHERE panel_channel_id IS NOT NULL AND panel_message_id IS NOT NULL"
        )

        for settings in all_panel_settings:
            guild_id = settings['guild_id']
            channel_id = settings['panel_channel_id']
            message_id = settings['panel_message_id']

            guild = self.bot.get_guild(guild_id)
            if not guild:
                logger.warning(f"Guild {guild_id} não encontrada para painel Anti-Recursos. Limpando registro.")
                await self.bot.db_connection.execute_query(
                    "UPDATE anti_features_settings SET panel_channel_id = NULL, panel_message_id = NULL WHERE guild_id = ?",
                    (guild_id,)
                )
                continue

            channel = guild.get_channel(channel_id)
            if not channel or not isinstance(channel, discord.TextChannel):
                logger.warning(f"Canal {channel_id} para painel Anti-Recursos na guild {guild.name} não encontrado ou não é um canal de texto. Limpando registro.")
                await self.bot.db_connection.execute_query(
                    "UPDATE anti_features_settings SET panel_channel_id = NULL, panel_message_id = NULL WHERE guild_id = ?",
                    (guild_id,)
                )
                continue

            try:
                # Apenas tenta buscar a mensagem. A View persistente será re-anexada pelo discord.py.
                # Não é necessário editar a mensagem aqui para evitar a tag "editado".
                await channel.fetch_message(message_id)
                logger.info(f"Painel Anti-Recursos na guild {guild.name} ({guild.id}) encontrado e persistência garantida (sem edição).")
            except discord.NotFound:
                logger.warning(f"Mensagem do painel Anti-Recursos não encontrada no canal {channel_id} da guild {guild.id}. O registro pode estar obsoleto. Limpando registro.")
                await self.bot.db_connection.execute_query(
                    "UPDATE anti_features_settings SET panel_channel_id = NULL, panel_message_id = NULL WHERE guild_id = ?",
                    (guild_id,)
                )
            except discord.Forbidden:
                logger.warning(f"Não tenho permissão para buscar a mensagem do painel Anti-Recursos no canal {channel_id} da guild {guild.id}.")
            except Exception as e:
                logger.error(f"Erro inesperado ao verificar painel Anti-Recursos no on_ready para guild {guild.id}: {e}", exc_info=True)


    @anti_features_group.command(name="setpanel", description="Define o canal onde o painel de controle Anti-Recursos será enviado.")
    @app_commands.describe(channel="O canal para enviar o painel.")
    @app_commands.default_permissions(administrator=True)
    async def set_anti_features_panel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await interaction.response.defer(ephemeral=True)

        # Usa a instância da View persistente armazenada na cog
        view = self.control_view
        
        # Obtém as configurações atuais para exibir no embed inicial
        configs = await view._get_guild_config(interaction.guild_id)
        
        embed = discord.Embed(
            title="Painel de Controle Anti-Recursos",
            description="Configure as proteções anti-spam, anti-link, anti-convite e anti-flood do servidor.",
            color=discord.Color.dark_red()
        )
        embed.add_field(
            name="Anti-Spam",
            value=f"Status: **{'Ativado' if configs['anti_spam']['enabled'] else 'Desativado'}**",
            inline=True
        )
        embed.add_field(
            name="Anti-Link",
            value=f"Status: **{'Ativado' if configs['anti_link']['enabled'] else 'Desativado'}**",
            inline=True
        )
        embed.add_field(
            name="Anti-Convite",
            value=f"Status: **{'Ativado' if configs['anti_invite']['enabled'] else 'Desativado'}**",
            inline=True
        )
        embed.add_field(
            name="Anti-Flood",
            value=f"Status: **{'Ativado' if configs['anti_flood']['enabled'] else 'Desativado'}**",
            inline=True
        )

        try:
            message = await channel.send(embed=embed, view=view)
            await self.bot.db_connection.execute_query(
                "INSERT OR IGNORE INTO anti_features_settings (guild_id) VALUES (?)",
                (interaction.guild_id,)
            )
            await self.bot.db_connection.execute_query(
                "UPDATE anti_features_settings SET panel_channel_id = ?, panel_message_id = ? WHERE guild_id = ?",
                (channel.id, message.id, interaction.guild_id)
            )
            await interaction.followup.send(f"Painel de controle Anti-Recursos enviado e configurado para {channel.mention}!", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send(f"Não tenho permissão para enviar mensagens em {channel.mention}.", ephemeral=True)
        except Exception as e:
            logger.error(f"Erro ao enviar painel Anti-Recursos: {e}", exc_info=True)
            await interaction.followup.send(f"Ocorreu um erro ao enviar o painel: {e}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(AntiFeatures(bot))

