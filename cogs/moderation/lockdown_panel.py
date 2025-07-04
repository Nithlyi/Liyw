import discord
from discord.ext import commands
from discord import app_commands, ui
import logging

# Importa o cog principal de lockdown. É importante que LockdownCore seja carregado antes de LockdownPanel.
from cogs.moderation.lockdown_core import LockdownCore 

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class LockdownPanelView(ui.View):
    """View persistente para o painel de controle de lockdown."""
    def __init__(self, bot: commands.Bot, guild_id: int): # db_manager removido daqui
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id
        self.db = bot.db_connection # Armazena a instância do gerenciador de DB
        self.message = None # Para armazenar a referência à mensagem do painel

    async def get_lockdown_core_cog(self) -> LockdownCore:
        """Obtém a instância do LockdownCore cog."""
        cog = self.bot.get_cog("LockdownCore")
        if cog is None:
            logging.error("LockdownCore cog não encontrado. O painel de lockdown pode não funcionar corretamente.")
        return cog

    async def refresh_panel(self, guild_id: int, bot_client: commands.Bot):
        """Atualiza a mensagem do painel de lockdown com o estado atual do canal."""
        logging.info(f"[refresh_panel_lockdown] Iniciando refresh do painel para guild_id: {guild_id}")
        
        panel_data = None
        try:
            panel_data = await self.db.fetch_one( # Usando self.db
                "SELECT channel_id, message_id FROM lockdown_panel_settings WHERE guild_id = ?",
                (guild_id,)
            )
        except Exception as e:
            logging.error(f"Erro ao buscar dados do painel de lockdown no DB para guild {guild_id}: {e}", exc_info=True)
            return # Aborta se houver erro no DB

        if not panel_data or panel_data[0] is None or panel_data[1] is None:
            logging.warning(f"[refresh_panel_lockdown] Nenhum dado de canal/mensagem válido encontrado no DB para o painel de lockdown da guild {guild_id}. Não foi possível atualizar o painel.")
            try:
                await self.db.execute_query("DELETE FROM lockdown_panel_settings WHERE guild_id = ?", (guild_id,)) # Usando self.db
            except Exception as e:
                logging.error(f"Erro ao deletar entrada inválida do painel de lockdown no DB para guild {guild_id}: {e}", exc_info=True)
            return

        panel_channel_id, panel_message_id = panel_data
        
        guild = bot_client.get_guild(guild_id)
        if not guild:
            logging.warning(f"[refresh_panel_lockdown] Guild {guild_id} não encontrada durante refresh. Removendo painel do DB.")
            try:
                await self.db.execute_query("DELETE FROM lockdown_panel_settings WHERE guild_id = ?", (guild_id,)) # Usando self.db
            except Exception as e:
                logging.error(f"Erro ao deletar painel de lockdown do DB após guild não encontrada: {e}", exc_info=True)
            return

        panel_channel = None
        try:
            panel_channel = await guild.fetch_channel(panel_channel_id)
            if not isinstance(panel_channel, discord.TextChannel):
                logging.warning(f"[refresh_panel_lockdown] Canal do painel {panel_channel_id} não é um canal de texto. Removendo do DB.")
                try:
                    await self.db.execute_query("DELETE FROM lockdown_panel_settings WHERE guild_id = ?", (guild_id,)) # Usando self.db
                except Exception as e:
                    logging.error(f"Erro ao deletar painel de lockdown do DB após canal não ser de texto: {e}", exc_info=True)
                return
        except discord.NotFound:
            logging.error(f"[refresh_panel_lockdown] Canal do painel {panel_channel_id} NÃO ENCONTRADO durante refresh. Removendo do DB.")
            try:
                await self.db.execute_query("DELETE FROM lockdown_panel_settings WHERE guild_id = ?", (guild_id,)) # Usando self.db
            except Exception as e:
                logging.error(f"Erro ao deletar painel de lockdown do DB após canal não encontrado: {e}", exc_info=True)
            return
        except discord.Forbidden:
            logging.error(f"[refresh_panel_lockdown] Bot sem permissão para buscar canal do painel {panel_channel_id} durante refresh. Verifique as permissões 'Ver Canais'.")
            return
        except Exception as e:
            logging.error(f"[refresh_panel_lockdown] Erro inesperado ao buscar canal do painel {panel_channel_id} durante refresh: {e}", exc_info=True)
            return

        message = None
        try:
            message = await panel_channel.fetch_message(panel_message_id)
            self.message = message
            logging.info(f"[refresh_panel_lockdown] Mensagem do painel {panel_message_id} encontrada.")
        except discord.NotFound:
            logging.error(f"[refresh_panel_lockdown] Mensagem do painel {panel_message_id} NÃO ENCONTRADA no canal {panel_channel_id}. Removendo do DB.")
            try:
                await self.db.execute_query("DELETE FROM lockdown_panel_settings WHERE guild_id = ?", (guild_id,)) # Usando self.db
            except Exception as e:
                logging.error(f"Erro ao deletar painel de lockdown do DB após mensagem não encontrada: {e}", exc_info=True)
            if panel_channel:
                try: await panel_channel.send(f"⚠️ O painel de lockdown foi perdido! Por favor, use `/lockdown_panel setup` para configurá-lo novamente.", delete_after=30)
                except: pass
            return
        except discord.Forbidden:
            logging.error(f"[refresh_panel_lockdown] Bot sem permissão para ler histórico de mensagens no canal {panel_channel_id}. Não é possível atualizar o painel.")
            return
        except Exception as e:
            logging.error(f"[refresh_panel_lockdown] Erro inesperado ao buscar mensagem {panel_message_id}: {e}", exc_info=True)
            return

        # Obter o status de lockdown do canal principal (geralmente o canal do painel ou um canal padrão)
        lockdown_core = await self.get_lockdown_core_cog()
        is_panel_channel_locked = False
        if lockdown_core:
            is_panel_channel_locked = await lockdown_core._is_channel_locked(panel_channel_id)
        else:
            logging.warning("LockdownCore cog não encontrado ao tentar verificar o estado do canal no refresh do painel.")
        
        status = "Ativado (Canais Bloqueados)" if is_panel_channel_locked else "Desativado (Canais Desbloqueados)"
        color = discord.Color.red() if is_panel_channel_locked else discord.Color.green()

        embed = discord.Embed(
            title="Painel de Controle de Lockdown",
            description=f"Status: **{status}**\n\nUse os botões para controlar o acesso aos canais.",
            color=color
        )
        embed.add_field(name="Canais Afetados (Padrão)", value=f"O canal atual ({panel_channel.mention})", inline=False)
        embed.set_footer(text="Ao ativar, o canal do painel será bloqueado. Para bloquear todos, use o comando /lockdown_all_channels.")

        self.clear_items()

        # Botões do painel: 'Bloquear Canal', 'Desbloquear Canal'
        # Adiciona o botão correto baseado no estado atual do canal
        if is_panel_channel_locked:
            self.add_item(ui.Button(label="Desbloquear Canal", style=discord.ButtonStyle.success, custom_id="lockdown_panel_unlock_channel"))
        else:
            self.add_item(ui.Button(label="Bloquear Canal", style=discord.ButtonStyle.danger, custom_id="lockdown_panel_lock_channel"))
        
        # Botões para "Todos os Canais"
        self.add_item(ui.Button(label="Bloquear TODOS os Canais", style=discord.ButtonStyle.danger, custom_id="lockdown_panel_lock_all"))
        self.add_item(ui.Button(label="Desbloquear TODOS os Canais", style=discord.ButtonStyle.success, custom_id="lockdown_panel_unlock_all"))

        # Re-adicionar a view persistente à mensagem
        # Criar uma nova instância da view para garantir que os callbacks funcionem corretamente
        new_view_instance = LockdownPanelView(bot_client, guild_id) # db_manager removido daqui
        new_view_instance.message = message # Garante que a nova view tenha referência à mensagem

        try:
            logging.info(f"[refresh_panel_lockdown] Tentando editar mensagem {message.id} com novo embed e nova view...")
            await message.edit(embed=embed, view=new_view_instance)
            # Adicione a nova instância da view ao bot para torná-la persistente
            bot_client.add_view(new_view_instance, message_id=message.id)
            logging.info(f"[refresh_panel_lockdown] Painel de Lockdown atualizado com sucesso com NOVA VIEW para guild {guild_id}.")
        except discord.Forbidden:
            logging.error(f"[refresh_panel_lockdown] Bot sem permissão para editar a mensagem do painel {message.id} no canal {panel_channel_id}. Verifique as permissões 'Gerenciar Mensagens'.")
        except Exception as e:
            logging.error(f"[refresh_panel_lockdown] Erro inesperado ao editar a mensagem do painel {message.id} na guild {guild_id} durante refresh: {e}", exc_info=True)


    @ui.button(label="Bloquear Canal", style=discord.ButtonStyle.danger, custom_id="lockdown_panel_lock_channel")
    async def lock_channel_button_callback(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        logging.info(f"[lock_channel_button_callback] Iniciando para guild {self.guild_id}, canal {interaction.channel.id} por {interaction.user.id}")

        lockdown_core = await self.get_lockdown_core_cog()
        if not lockdown_core:
            await interaction.followup.send("Erro: O sistema de lockdown principal não está carregado. Por favor, contate um administrador.", ephemeral=True)
            return

        success, status_message = await lockdown_core._toggle_lockdown(
            channel=interaction.channel,
            lock=True,
            reason=f"Ativado via Painel de Lockdown por {interaction.user.name}",
            locked_by=interaction.user
        )

        if success:
            await interaction.followup.send(f"O canal {interaction.channel.mention} foi bloqueado com sucesso.", ephemeral=True)
            await lockdown_core._send_lockdown_message(interaction.channel, True, f"Ativado via Painel de Lockdown por {interaction.user.name}")
            await self.refresh_panel(self.guild_id, interaction.client)
        else:
            await interaction.followup.send(status_message, ephemeral=True)

    @ui.button(label="Desbloquear Canal", style=discord.ButtonStyle.success, custom_id="lockdown_panel_unlock_channel")
    async def unlock_channel_button_callback(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        logging.info(f"[unlock_channel_button_callback] Iniciando para guild {self.guild_id}, canal {interaction.channel.id} por {interaction.user.id}")

        lockdown_core = await self.get_lockdown_core_cog()
        if not lockdown_core:
            await interaction.followup.send("Erro: O sistema de lockdown principal não está carregado. Por favor, contate um administrador.", ephemeral=True)
            return
        
        is_locked = await lockdown_core._is_channel_locked(interaction.channel.id)
        if not is_locked:
            await interaction.followup.send(f"O canal {interaction.channel.mention} não está atualmente em lockdown pelo sistema (ou não está registrado no DB).", ephemeral=True)
            await self.refresh_panel(self.guild_id, interaction.client)
            return

        success, status_message = await lockdown_core._toggle_lockdown(
            channel=interaction.channel,
            lock=False,
            reason=f"Desativado via Painel de Lockdown por {interaction.user.name}"
        )

        if success:
            await interaction.followup.send(f"O canal {interaction.channel.mention} foi desbloqueado com sucesso.", ephemeral=True)
            await lockdown_core._send_lockdown_message(interaction.channel, False, f"Desativado via Painel de Lockdown por {interaction.user.name}")
            await self.refresh_panel(self.guild_id, interaction.client)
        else:
            await interaction.followup.send(status_message, ephemeral=True)

    @ui.button(label="Bloquear TODOS os Canais", style=discord.ButtonStyle.danger, custom_id="lockdown_panel_lock_all")
    async def lock_all_channels_button_callback(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        logging.info(f"[lock_all_channels_button_callback] Iniciando para guild {self.guild_id} por {interaction.user.id}")

        if not interaction.guild:
            await interaction.followup.send("Este comando só pode ser usado em um servidor.", ephemeral=True)
            return

        lockdown_core = await self.get_lockdown_core_cog()
        if not lockdown_core:
            await interaction.followup.send("Erro: O sistema de lockdown principal não está carregado. Por favor, contate um administrador.", ephemeral=True)
            return

        locked_count = 0
        skipped_channels = [] # Nova lista para canais explicitamente pulados (já marcados no DB)
        failed_channels = [] # Lista para canais que falharam por erro ou permissão
        
        for channel in interaction.guild.text_channels:
            try:
                # Verifica se o canal já está marcado como bloqueado no DB
                is_locked_in_db = await lockdown_core._is_channel_locked(channel.id)
                if is_locked_in_db:
                    logging.info(f"Canal #{channel.name} ({channel.id}) já está marcado como bloqueado no DB, pulando.")
                    skipped_channels.append(channel.name)
                    continue

                # Tenta alternar o lockdown
                success, msg = await lockdown_core._toggle_lockdown(
                    channel=channel,
                    lock=True,
                    reason=f"Lockdown geral ativado via Painel por {interaction.user.name}",
                    locked_by=interaction.user
                )
                if success:
                    locked_count += 1
                    await lockdown_core._send_lockdown_message(channel, True, f"Lockdown geral ativado por {interaction.user.name}")
                else:
                    # Se success for False, msg contém a razão do _toggle_lockdown
                    failed_channels.append(f"{channel.name} ({msg})")
            except Exception as e:
                logging.error(f"Erro inesperado ao tentar bloquear canal {channel.name} ({channel.id}): {e}", exc_info=True)
                failed_channels.append(f"{channel.name} (Erro interno: {e})")

        response_message = f"Foram bloqueados {locked_count} canais de texto."
        if skipped_channels:
            response_message += f"\n\n**Canal(is) já marcado(s) como bloqueado(s) no sistema (pulado(s)):**\n{', '.join(skipped_channels)}"
        if failed_channels:
            response_message += f"\n\n**Falha ao bloquear:**\n{'; '.join(failed_channels)}\n\nPor favor, verifique as permissões do bot ('Gerenciar Cargos' e 'Gerenciar Canais') e a hierarquia de cargos."
        
        await interaction.followup.send(response_message, ephemeral=True)
        await self.refresh_panel(self.guild_id, interaction.client)

    @ui.button(label="Desbloquear TODOS os Canais", style=discord.ButtonStyle.success, custom_id="lockdown_panel_unlock_all")
    async def unlock_all_channels_button_callback(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        logging.info(f"[unlock_all_channels_button_callback] Iniciando para guild {self.guild_id} por {interaction.user.id}")

        if not interaction.guild:
            await interaction.followup.send("Este comando só pode ser usado em um servidor.", ephemeral=True)
            return

        lockdown_core = await self.get_lockdown_core_cog()
        if not lockdown_core:
            await interaction.followup.send("Erro: O sistema de lockdown principal não está carregado. Por favor, contate um administrador.", ephemeral=True)
            return

        unlocked_count = 0
        failed_channels = []

        # Buscar todos os canais que estão em lockdown pelo nosso DB
        locked_channels_data = []
        try:
            locked_channels_data = await self.db.fetch_all( # Usando self.db
                "SELECT channel_id FROM locked_channels WHERE guild_id = ?",
                (interaction.guild.id,)
            )
        except Exception as e:
            logging.error(f"Erro ao buscar canais bloqueados do DB para guild {self.guild_id}: {e}", exc_info=True)
            await interaction.followup.send("Ocorreu um erro ao buscar canais bloqueados no banco de dados.", ephemeral=True)
            return

        locked_channel_ids = [row[0] for row in locked_channels_data]

        for channel_id in locked_channel_ids:
            channel = interaction.guild.get_channel(channel_id)
            if not channel or not isinstance(channel, discord.TextChannel):
                logging.warning(f"Canal {channel_id} do DB não encontrado ou não é de texto. Removendo do DB.")
                try:
                    await self.db.execute_query("DELETE FROM locked_channels WHERE channel_id = ?", (channel_id,)) # Usando self.db
                except Exception as e:
                    logging.error(f"Erro ao remover canal {channel_id} do DB após não encontrado: {e}", exc_info=True)
                continue

            try:
                success, msg = await lockdown_core._toggle_lockdown(
                    channel=channel,
                    lock=False,
                    reason=f"Lockdown geral desativado via Painel por {interaction.user.name}"
                )
                if success:
                    unlocked_count += 1
                    await lockdown_core._send_lockdown_message(channel, False, f"Lockdown geral desativado por {interaction.user.name}")
                else:
                    failed_channels.append(f"{channel.name} ({msg})")
            except Exception as e:
                logging.error(f"Erro ao tentar desbloquear canal {channel.name} ({channel.id}): {e}", exc_info=True)
                failed_channels.append(f"{channel.name} (Erro interno: {e})")

        response_message = f"Foram desbloqueados {unlocked_count} canais de texto."
        if failed_channels:
            response_message += f"\n\n**Falha ao desbloquear:**\n{'; '.join(failed_channels)}\n\nPor favor, verifique as permissões do bot ('Gerenciar Cargos' e 'Gerenciar Canais') e a hierarquia de cargos."
        
        await interaction.followup.send(response_message, ephemeral=True)
        await self.refresh_panel(self.guild_id, interaction.client)


class LockdownPanel(commands.Cog):
    def __init__(self, bot: commands.Bot): # db_manager removido daqui
        self.bot = bot
        self.db = bot.db_connection # Armazena a instância do gerenciador de DB
        self.bot.loop.create_task(self.ensure_persistent_panel_view())

    async def ensure_persistent_panel_view(self):
        await self.bot.wait_until_ready()
        logging.info("Tentando carregar painéis de Lockdown persistentes...")
        
        panel_datas = []
        try:
            panel_datas = await self.db.fetch_all("SELECT guild_id, channel_id, message_id FROM lockdown_panel_settings") # Usando self.db
        except Exception as e:
            logging.error(f"Erro ao buscar painéis persistentes de lockdown do DB: {e}", exc_info=True)
            return # Aborta se houver erro no DB

        logging.info(f"[ensure_persistent_panel_view] Dados lidos do DB: {panel_datas}")
        
        if panel_datas:
            for guild_id, channel_id, message_id in panel_datas:
                if channel_id is None or message_id is None:
                    logging.warning(f"[ensure_persistent_panel_view] Pulando entrada inválida no DB para guild {guild_id} (channel_id ou message_id é None). Removendo do DB.")
                    try:
                        await self.db.execute_query("DELETE FROM lockdown_panel_settings WHERE guild_id = ?", (guild_id,)) # Usando self.db
                    except Exception as e:
                        logging.error(f"Erro ao deletar entrada inválida do painel de lockdown no DB: {e}", exc_info=True)
                    continue
                
                try:
                    guild = self.bot.get_guild(guild_id)
                    if not guild:
                        logging.warning(f"Guild {guild_id} não encontrada para painel persistente de lockdown. Removendo do DB.")
                        try:
                            await self.db.execute_query("DELETE FROM lockdown_panel_settings WHERE guild_id = ?", (guild_id,)) # Usando self.db
                        except Exception as e:
                            logging.error(f"Erro ao deletar painel de lockdown do DB após guild não encontrada: {e}", exc_info=True)
                        continue
                    
                    channel = await guild.fetch_channel(channel_id)
                    if not isinstance(channel, discord.TextChannel):
                        logging.warning(f"Canal {channel_id} não é de texto para painel persistente de lockdown na guild {guild_id}. Removendo do DB.")
                        try:
                            await self.db.execute_query("DELETE FROM lockdown_panel_settings WHERE guild_id = ?", (guild_id,)) # Usando self.db
                        except Exception as e:
                            logging.error(f"Erro ao deletar painel de lockdown do DB após canal não ser de texto: {e}", exc_info=True)
                        continue

                    message = await channel.fetch_message(message_id)
                    view = LockdownPanelView(self.bot, guild_id) # db_manager removido daqui
                    view.message = message
                    self.bot.add_view(view, message_id=message.id)
                    logging.info(f"Painel de Lockdown persistente carregado para guild {guild_id} no canal {channel_id}, mensagem {message_id}.")
                except discord.NotFound:
                    logging.warning(f"Mensagem do painel de Lockdown ({message_id}) ou canal ({channel_id}) não encontrada. Removendo do DB para evitar carregamentos futuros.")
                    try:
                        await self.db.execute_query("DELETE FROM lockdown_panel_settings WHERE message_id = ?", (message_id,)) # Usando self.db
                    except Exception as e:
                        logging.error(f"Erro ao deletar painel de lockdown do DB após mensagem/canal não encontrado: {e}", exc_info=True)
                except discord.Forbidden:
                    logging.error(f"Bot sem permissão para acessar o canal {channel_id} ou mensagem {message_id} na guild {guild_id}. Não foi possível carregar o painel persistente de lockdown.")
                except Exception as e:
                    logging.error(f"Erro inesperado ao carregar painel persistente de lockdown para guild {guild_id}, mensagem {message_id}: {e}", exc_info=True)
        else:
            logging.info("Nenhum painel de Lockdown persistente para carregar.")

    @app_commands.command(name="lockdown_panel_setup", description="Configura ou move o painel de controle de lockdown para o canal atual.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_lockdown_panel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild.id
        
        old_panel_data = None
        try:
            old_panel_data = await self.db.fetch_one( # Usando self.db
                "SELECT channel_id, message_id FROM lockdown_panel_settings WHERE guild_id = ?",
                (guild_id,)
            )
        except Exception as e:
            logging.error(f"Erro ao buscar dados antigos do painel de lockdown no DB para guild {guild_id}: {e}", exc_info=True)
            await interaction.followup.send("Ocorreu um erro ao buscar configurações antigas do painel.", ephemeral=True)
            return

        if old_panel_data and (old_panel_data[0] is not None and old_panel_data[1] is not None): 
            old_channel_id, old_message_id = old_panel_data
            try:
                old_channel = await interaction.guild.fetch_channel(old_channel_id)
                if isinstance(old_channel, discord.TextChannel):
                    old_message = await old_channel.fetch_message(old_message_id)
                    await old_message.delete()
                    logging.info(f"[setup_lockdown_panel] Mensagem do painel de lockdown antigo ({old_message_id}) deletada do canal {old_channel_id}.")
                else:
                    logging.warning(f"[setup_lockdown_panel] Canal antigo {old_channel_id} não é de texto. Não foi possível deletar a mensagem.")
            except discord.NotFound:
                logging.warning(f"[setup_lockdown_panel] Mensagem do painel de lockdown ({old_message_id}) não encontrada para deletar no canal {old_channel_id}.")
            except discord.Forbidden:
                logging.error(f"[setup_lockdown_panel] Bot sem permissão para deletar a mensagem do painel antigo ({old_message_id}) no canal {old_channel_id}. Verifique as permissões 'Gerenciar Mensagens'.")
            except Exception as e:
                logging.error(f"[setup_lockdown_panel] Erro ao deletar painel de lockdown antigo: {e}", exc_info=True)
            
            try:
                await self.db.execute_query("DELETE FROM lockdown_panel_settings WHERE guild_id = ?", (guild_id,)) # Usando self.db
            except Exception as e:
                logging.error(f"Erro ao deletar entrada antiga do painel de lockdown do DB para guild {guild_id}: {e}", exc_info=True)
        elif old_panel_data: 
            logging.warning(f"[setup_lockdown_panel] Entrada antiga de painel com IDs None para guild {guild_id}. Apenas deletando do DB.")
            try:
                await self.db.execute_query("DELETE FROM lockdown_panel_settings WHERE guild_id = ?", (guild_id,)) # Usando self.db
            except Exception as e:
                logging.error(f"Erro ao deletar entrada inválida do painel de lockdown do DB: {e}", exc_info=True)

        # O estado inicial do painel vai depender do estado do canal atual
        lockdown_core = self.bot.get_cog("LockdownCore")
        is_panel_channel_locked = False
        if lockdown_core:
            is_panel_channel_locked = await lockdown_core._is_channel_locked(interaction.channel.id)
        else:
            logging.warning("LockdownCore cog não encontrado ao tentar verificar o estado do canal no setup do painel.")

        status = "Ativado (Canais Bloqueados)" if is_panel_channel_locked else "Desativado (Canais Desbloqueados)"
        color = discord.Color.red() if is_panel_channel_locked else discord.Color.green()

        embed = discord.Embed(
            title="Painel de Controle de Lockdown",
            description=f"Status: **{status}**\n\nUse os botões para controlar o acesso aos canais.",
            color=color
        )
        embed.add_field(name="Canais Afetados (Padrão)", value=f"O canal atual ({interaction.channel.mention})", inline=False)
        embed.set_footer(text="Ao ativar, o canal do painel será bloqueado. Para bloquear todos, use o comando /lockdown_all_channels.")


        view = LockdownPanelView(self.bot, guild_id) # db_manager removido daqui
        
        try:
            panel_message = await interaction.channel.send(embed=embed, view=view)
            view.message = panel_message 

            logging.info(f"[setup_lockdown_panel] Tentando salvar no DB: guild_id={guild_id}, channel_id={interaction.channel.id}, message_id={panel_message.id}")

            success_db_insert = await self.db.execute_query( # Usando self.db
                "INSERT OR REPLACE INTO lockdown_panel_settings (guild_id, channel_id, message_id) VALUES (?, ?, ?)",
                (guild_id, interaction.channel.id, panel_message.id)
            )
            if success_db_insert:
                logging.info(f"[setup_lockdown_panel] Dados do painel de lockdown salvos com sucesso no DB para guild {guild_id}.")
            else:
                logging.error(f"[setup_lockdown_panel] Falha ao salvar dados do painel de lockdown no DB para guild {guild_id}.")

            self.bot.add_view(view, message_id=panel_message.id) 
            await interaction.followup.send(f"Painel de controle de lockdown configurado neste canal: {interaction.channel.mention}", ephemeral=True)
            logging.info(f"Painel de Lockdown configurado/movido por {interaction.user.id} para canal {interaction.channel.id} na guild {guild_id}. Mensagem ID: {panel_message.id}.")
        except discord.Forbidden:
            await interaction.followup.send("Não tenho permissão para enviar mensagens neste canal. Por favor, verifique as minhas permissões.", ephemeral=True)
            logging.error(f"Bot sem permissão para enviar painel de lockdown no canal {interaction.channel.id} na guild {guild_id}.")
        except Exception as e:
            await interaction.followup.send(f"Ocorreu um erro ao configurar o painel: {e}", ephemeral=True)
            logging.error(f"Erro inesperado ao configurar painel de lockdown na guild {guild_id}: {e}", exc_info=True)

    @app_commands.command(name="lockdown_panel_delete", description="Deleta o painel de controle de lockdown existente.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def delete_lockdown_panel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild.id
        
        panel_data = None
        try:
            panel_data = await self.db.fetch_one( # Usando self.db
                "SELECT channel_id, message_id FROM lockdown_panel_settings WHERE guild_id = ?",
                (guild_id,)
            )
        except Exception as e:
            logging.error(f"Erro ao buscar dados do painel de lockdown para deletar no DB para guild {guild_id}: {e}", exc_info=True)
            await interaction.followup.send("Ocorreu um erro ao buscar o painel de lockdown para deletar.", ephemeral=True)
            return

        if not panel_data:
            await interaction.followup.send("Nenhum painel de controle de lockdown encontrado para deletar.", ephemeral=True)
            logging.info(f"Tentativa de deletar painel de lockdown, mas nenhum painel encontrado para guild {guild_id}.")
            return

        channel_id, message_id = panel_data
        
        if channel_id is None or message_id is None:
            logging.warning(f"Entrada inválida no DB para guild {guild_id} (channel_id ou message_id é None). Apenas deletando do DB.")
            try:
                await self.db.execute_query("DELETE FROM lockdown_panel_settings WHERE guild_id = ?", (guild_id,)) # Usando self.db
            except Exception as e:
                logging.error(f"Erro ao deletar entrada inválida do painel de lockdown do DB: {e}", exc_info=True)
            await interaction.followup.send("Painel de controle de lockdown deletado com sucesso (entrada inválida no DB).", ephemeral=True)
            return

        try:
            channel = await interaction.guild.fetch_channel(channel_id)
            if isinstance(channel, discord.TextChannel):
                message = await channel.fetch_message(message_id)
                await message.delete()
                logging.info(f"Mensagem do painel de lockdown ({message_id}) deletada do canal {channel_id}.")
                
                # Após deletar a mensagem, remova a entrada do DB
                success_db_delete = await self.db.execute_query("DELETE FROM lockdown_panel_settings WHERE guild_id = ?", (guild_id,))
                if success_db_delete:
                    logging.info(f"Entrada do painel de lockdown deletada do DB para guild {guild_id}.")
                    await interaction.followup.send("Painel de controle de lockdown deletado com sucesso.", ephemeral=True)
                else:
                    logging.error(f"Falha ao deletar entrada do painel de lockdown do DB para guild {guild_id}.")
                    await interaction.followup.send("Painel deletado do Discord, mas ocorreu um erro ao remover a entrada do banco de dados.", ephemeral=True)
            else:
                logging.warning(f"Canal {channel_id} não é de texto. Não foi possível deletar a mensagem do painel.")
                await interaction.followup.send("O canal do painel não é um canal de texto válido. Removendo a entrada do banco de dados.", ephemeral=True)
                try:
                    await self.db.execute_query("DELETE FROM lockdown_panel_settings WHERE guild_id = ?", (guild_id,))
                except Exception as e:
                    logging.error(f"Erro ao deletar entrada do painel de lockdown do DB após canal inválido: {e}", exc_info=True)
        except discord.NotFound:
            logging.warning(f"Mensagem do painel de lockdown ({message_id}) ou canal ({channel_id}) não encontrada. Removendo do DB.")
            try:
                await self.db.execute_query("DELETE FROM lockdown_panel_settings WHERE guild_id = ?", (guild_id,))
            except Exception as e:
                logging.error(f"Erro ao deletar entrada do painel de lockdown do DB após mensagem/canal não encontrado: {e}", exc_info=True)
            await interaction.followup.send("Painel de controle de lockdown não encontrado no Discord, mas a entrada foi removida do banco de dados.", ephemeral=True)
        except discord.Forbidden:
            logging.error(f"Bot sem permissão para deletar a mensagem do painel ({message_id}) no canal {channel_id}. Verifique as permissões 'Gerenciar Mensagens'.")
            await interaction.followup.send("Não tenho permissão para deletar a mensagem do painel. Por favor, verifique as minhas permissões.", ephemeral=True)
        except Exception as e:
            logging.error(f"Erro inesperado ao deletar painel de lockdown: {e}", exc_info=True)
            await interaction.followup.send(f"Ocorreu um erro ao deletar o painel: {e}", ephemeral=True)


async def setup(bot: commands.Bot): # db_manager removido daqui
    """
    Função de setup para adicionar o cog ao bot.
    """
    await bot.add_cog(LockdownPanel(bot)) # db_manager removido daqui
    logging.info("LockdownPanel cog adicionado ao bot.")
