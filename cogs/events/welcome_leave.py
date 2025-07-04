import discord
from discord.ext import commands
from discord import app_commands, ui
import logging
import json

# Não precisamos importar execute_query diretamente, pois usaremos self.db
# from database import execute_query

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Funções Auxiliares para Embeds ---
def _create_embed_from_data(embed_data: dict, member: discord.Member = None, guild: discord.Guild = None):
    """Cria um discord.Embed a partir de um dicionário de dados, formatando variáveis."""
    embed = discord.Embed()
    
    # Título (opcional)
    if embed_data.get('title'):
        embed.title = embed_data['title'].format(
            member=member,
            guild=guild,
            member_name=member.display_name if member else 'N/A',
            member_count=guild.member_count if guild else 'N/A'
        )
    else:
        embed.title = "" # Garante que é uma string vazia

    # Descrição (opcional)
    if embed_data.get('description'):
        embed.description = embed_data['description'].format(
            member=member,
            guild=guild,
            member_name=member.display_name if member else 'N/A',
            member_count=guild.member_count if guild else 'N/A'
        )
    else:
        embed.description = "" # Garante que é uma string vazia
    
    # Cor (opcional)
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

    # Imagem (opcional)
    if embed_data.get('image_url'):
        embed.set_image(url=embed_data['image_url'])
    
    # Rodapé (opcional)
    if embed_data.get('footer_text'):
        embed.set_footer(text=embed_data['footer_text'].format(
            member=member,
            guild=guild,
            member_name=member.display_name if member else 'N/A',
            member_count=guild.member_count if guild else 'N/A'
        ), icon_url=embed_data.get('footer_icon_url'))

    # Autor (opcional)
    if embed_data.get('author_name'):
        embed.set_author(name=embed_data['author_name'].format(
            member=member,
            guild=guild,
            member_name=member.display_name if member else 'N/A',
            member_count=guild.member_count if guild else 'N/A'
        ), icon_url=embed_data.get('author_icon_url'))
    
    # Campos (opcional) - Embora não configuráveis aqui, é bom ter para consistência
    if 'fields' in embed_data:
        for field in embed_data['fields']:
            field_name = str(field.get('name', ''))
            field_value = str(field.get('value', ''))
            embed.add_field(name=field_name, value=field_value, inline=field.get('inline', False))

    return embed

# --- Views de Configuração Específicas (Boas-Vindas e Saídas) ---

class WelcomeConfigView(ui.View):
    def __init__(self, parent_view: ui.View, bot: commands.Bot, guild_id: int): # db_manager removido daqui
        super().__init__(timeout=180)
        self.parent_view = parent_view # A WelcomeSettingsView
        self.bot = bot
        self.guild_id = guild_id
        self.db = bot.db_connection # Armazena a instância do gerenciador de DB
        self.message = None

    async def on_timeout(self):
        if self.message:
            for item in self.children:
                item.disabled = True
            await self.message.edit(content="Sessão de configuração de Boas-Vindas expirada.", view=self)

    async def _update_welcome_display(self, interaction: discord.Interaction):
        settings = None
        try:
            settings = await self.db.fetch_one( # Usando self.db
                "SELECT welcome_enabled, welcome_channel_id, welcome_message, welcome_embed_json FROM welcome_leave_messages WHERE guild_id = ?",
                (self.guild_id,)
            )
        except Exception as e:
            logging.error(f"Erro ao buscar configurações de boas-vindas do DB para guild {self.guild_id}: {e}", exc_info=True)
            # Continua com valores padrão se houver erro no DB
            settings = (False, None, None, None)

        embed = discord.Embed(
            title="Configurações de Boas-Vindas",
            description="Ajuste as mensagens e o embed para novos membros.\n\n**Variáveis:** `{member}`, `{member.name}`, `{guild.name}`, `{member.count}`",
            color=discord.Color.blue()
        )

        if settings:
            welcome_enabled, wc_id, wm, welcome_embed_json = settings
            
            welcome_status = "🟢 Ativado" if welcome_enabled else "🔴 Desativado"
            welcome_channel = self.bot.get_channel(wc_id) if wc_id else "Nenhum"
            welcome_message_preview = (wm[:50] + "..." if wm and len(wm) > 50 else wm) if wm else "Nenhuma"
            welcome_embed_configured = "Sim" if welcome_embed_json else "Não"
            
            embed.add_field(name="Status Geral", value=welcome_status, inline=False)
            embed.add_field(name="Canal", value=getattr(welcome_channel, 'mention', welcome_channel), inline=False)
            embed.add_field(name="Mensagem de Texto", value=f"`{welcome_message_preview}`", inline=False)
            embed.add_field(name="Embed Configurado", value=welcome_embed_configured, inline=False)

            # Pré-visualização do embed de boas-vindas (se configurado)
            preview_embed = None # Initialize preview_embed
            if welcome_embed_json:
                try:
                    embed_data = json.loads(welcome_embed_json)
                    preview_embed = _create_embed_from_data(embed_data, member=interaction.user, guild=interaction.guild) # Usar interaction.user/guild para preview
                    embed.add_field(name="Pré-visualização do Embed", value="Veja abaixo:", inline=False)
                except json.JSONDecodeError:
                    logging.error(f"Erro ao decodificar JSON do welcome embed para guild {self.guild_id} na preview.")
                    preview_embed = None
            else:
                preview_embed = None
        else:
            embed.add_field(name="Status", value="🔴 Desativado (Padrões)", inline=False)
            embed.set_footer(text="Nenhuma configuração salva. Use os botões para configurar.")
            preview_embed = None # Initialize preview_embed for this path too
        
        embeds_to_send = [embed]
        if preview_embed:
            embeds_to_send.append(preview_embed)

        if self.message:
            await self.message.edit(embeds=embeds_to_send, view=self)
        else:
            if interaction.response.is_done():
                self.message = await interaction.followup.send(embeds=embeds_to_send, view=self, ephemeral=True)
            else:
                await interaction.response.send_message(embeds=embeds_to_send, view=self, ephemeral=True)
                self.message = await interaction.original_response()

    # Helpers para carregar/salvar embed JSON
    async def _get_welcome_embed_data(self): # Tornar assíncrono
        settings = await self.db.fetch_one("SELECT welcome_embed_json FROM welcome_leave_messages WHERE guild_id = ?", (self.guild_id,)) # Usando self.db
        if settings and settings[0]:
            try:
                return json.loads(settings[0])
            except json.JSONDecodeError:
                logging.error(f"Erro ao decodificar JSON do welcome embed para guild {self.guild_id}. Retornando vazio.")
                return {}
        return {}

    async def _save_welcome_embed_data(self, embed_data: dict): # Tornar assíncrono
        embed_json = json.dumps(embed_data)
        try:
            await self.db.execute_query( # Usando self.db
                "INSERT OR REPLACE INTO welcome_leave_messages (guild_id, welcome_embed_json) VALUES (?, ?)",
                (self.guild_id, embed_json)
            )
        except Exception as e:
            logging.error(f"Erro ao salvar welcome embed data no DB para guild {self.guild_id}: {e}", exc_info=True)


    @ui.button(label="Alternar Status", style=discord.ButtonStyle.primary, row=0)
    async def toggle_welcome_status(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        current_status = await self.db.fetch_one("SELECT welcome_enabled FROM welcome_leave_messages WHERE guild_id = ?", (self.guild_id,)) # Usando self.db
        new_status = not current_status[0] if current_status and current_status[0] is not None else True # Handle None or 0
        
        try:
            await self.db.execute_query( # Usando self.db
                "INSERT OR REPLACE INTO welcome_leave_messages (guild_id, welcome_enabled) VALUES (?, ?)",
                (self.guild_id, new_status)
            )
            await self._update_welcome_display(interaction)
            await interaction.followup.send(f"Mensagens de Boas-Vindas {('ativadas' if new_status else 'desativadas')}!", ephemeral=True)
        except Exception as e:
            logging.error(f"Erro ao alternar status de boas-vindas no DB para guild {self.guild_id}: {e}", exc_info=True)
            await interaction.followup.send("Ocorreu um erro ao atualizar o status de boas-vindas.", ephemeral=True)


    @ui.button(label="Definir Canal", style=discord.ButtonStyle.secondary, row=0)
    async def set_welcome_channel(self, interaction: discord.Interaction, button: ui.Button):
        class WelcomeChannelModal(ui.Modal, title="Definir Canal de Boas-Vindas"):
            def __init__(self, parent_view: ui.View, current_channel_id: int): # db_manager removido
                super().__init__()
                self.parent_view = parent_view
                self.db = parent_view.db # Armazena db_manager via parent_view
                default_value = str(current_channel_id) if current_channel_id else ""
                self.add_item(ui.TextInput(label="ID do Canal", placeholder="Ex: 123456789012345678", style=discord.TextStyle.short, custom_id="channel_id", default=default_value))

            async def on_submit(self, interaction: discord.Interaction):
                await interaction.response.defer()
                original_view = self.parent_view
                try:
                    channel_id = int(self.children[0].value)
                    channel = original_view.bot.get_channel(channel_id)
                    if not isinstance(channel, discord.TextChannel):
                        await interaction.followup.send("ID de canal inválido ou não é um canal de texto.", ephemeral=True)
                        return

                    try:
                        await self.db.execute_query( # Usando self.db
                            "INSERT OR REPLACE INTO welcome_leave_messages (guild_id, welcome_channel_id) VALUES (?, ?)",
                            (original_view.guild_id, channel_id)
                        )
                        await original_view._update_welcome_display(interaction)
                        await interaction.followup.send(f"Canal de Boas-Vindas definido para {channel.mention}.", ephemeral=True)
                    except Exception as e:
                        logging.error(f"Erro ao definir canal de boas-vindas no DB para guild {original_view.guild_id}: {e}", exc_info=True)
                        await interaction.followup.send("Ocorreu um erro ao salvar o canal no banco de dados.", ephemeral=True)
                except ValueError:
                    await interaction.followup.send("ID de canal inválido. Por favor, insira um número.", ephemeral=True)
        
        current_settings = await self.db.fetch_one("SELECT welcome_channel_id FROM welcome_leave_messages WHERE guild_id = ?", (self.guild_id,)) # Usando self.db
        current_channel_id = current_settings[0] if current_settings else None
        await interaction.response.send_modal(WelcomeChannelModal(parent_view=self, current_channel_id=current_channel_id)) # db_manager removido

    @ui.button(label="Definir Mensagem de Texto", style=discord.ButtonStyle.secondary, row=0)
    async def set_welcome_message(self, interaction: discord.Interaction, button: ui.Button):
        class WelcomeMessageModal(ui.Modal, title="Definir Mensagem de Boas-Vindas"):
            def __init__(self, parent_view: ui.View, current_message: str): # db_manager removido
                super().__init__()
                self.parent_view = parent_view
                self.db = parent_view.db # Armazena db_manager via parent_view
                self.add_item(ui.TextInput(label="Mensagem", placeholder="Use {member}, {guild.name}, {member.count}", style=discord.TextStyle.paragraph, custom_id="welcome_message", default=current_message, required=False))

            async def on_submit(self, interaction: discord.Interaction):
                await interaction.response.defer()
                original_view = self.parent_view
                message_content = self.children[0].value if self.children[0].value.strip() else None

                try:
                    await self.db.execute_query( # Usando self.db
                        "INSERT OR REPLACE INTO welcome_leave_messages (guild_id, welcome_message) VALUES (?, ?)",
                        (original_view.guild_id, message_content)
                    )
                    await original_view._update_welcome_display(interaction)
                    await interaction.followup.send("Mensagem de Boas-Vindas atualizada!", ephemeral=True)
                except Exception as e:
                    logging.error(f"Erro ao definir mensagem de boas-vindas no DB para guild {original_view.guild_id}: {e}", exc_info=True)
                    await interaction.followup.send("Ocorreu um erro ao salvar a mensagem no banco de dados.", ephemeral=True)
        
        current_settings = await self.db.fetch_one("SELECT welcome_message FROM welcome_leave_messages WHERE guild_id = ?", (self.guild_id,)) # Usando self.db
        current_message = current_settings[0] if current_settings and current_settings[0] else ""
        await interaction.response.send_modal(WelcomeMessageModal(parent_view=self, current_message=current_message)) # db_manager removido

    @ui.button(label="Título do Embed", style=discord.ButtonStyle.green, row=1)
    async def set_welcome_embed_title(self, interaction: discord.Interaction, button: ui.Button):
        class WelcomeEmbedTitleModal(ui.Modal, title="Título do Embed de Boas-Vindas"):
            def __init__(self, parent_view: ui.View, current_title: str): # db_manager removido
                super().__init__()
                self.parent_view = parent_view
                self.db = parent_view.db # Armazena db_manager via parent_view
                self.add_item(ui.TextInput(label="Título", placeholder="Título do embed (use variáveis)", style=discord.TextStyle.short, custom_id="embed_title", default=current_title, required=False))

            async def on_submit(self, interaction: discord.Interaction):
                await interaction.response.defer()
                original_view = self.parent_view
                embed_data = await original_view._get_welcome_embed_data() # Tornar assíncrono
                embed_data['title'] = self.children[0].value if self.children[0].value.strip() else None
                await original_view._save_welcome_embed_data(embed_data) # Tornar assíncrono
                await original_view._update_welcome_display(interaction)
                await interaction.followup.send("Título do Embed de Boas-Vindas atualizado!", ephemeral=True)
        
        embed_data = await self._get_welcome_embed_data() # Tornar assíncrono
        current_title = embed_data.get('title', '') or ''
        await interaction.response.send_modal(WelcomeEmbedTitleModal(parent_view=self, current_title=current_title)) # db_manager removido

    @ui.button(label="Descrição do Embed", style=discord.ButtonStyle.green, row=1)
    async def set_welcome_embed_description(self, interaction: discord.Interaction, button: ui.Button):
        class WelcomeEmbedDescriptionModal(ui.Modal, title="Descrição do Embed de Boas-Vindas"):
            def __init__(self, parent_view: ui.View, current_description: str): # db_manager removido
                super().__init__()
                self.parent_view = parent_view
                self.db = parent_view.db # Armazena db_manager via parent_view
                self.add_item(ui.TextInput(label="Descrição", placeholder="Descrição do embed (use variáveis)", style=discord.TextStyle.paragraph, custom_id="embed_description", default=current_description, required=False))

            async def on_submit(self, interaction: discord.Interaction):
                await interaction.response.defer()
                original_view = self.parent_view
                embed_data = await original_view._get_welcome_embed_data() # Tornar assíncrono
                embed_data['description'] = self.children[0].value if self.children[0].value.strip() else None
                await original_view._save_welcome_embed_data(embed_data) # Tornar assíncrono
                await original_view._update_welcome_display(interaction)
                await interaction.followup.send("Descrição do Embed de Boas-Vindas atualizada!", ephemeral=True)
        
        embed_data = await self._get_welcome_embed_data() # Tornar assíncrono
        current_description = embed_data.get('description', '') or ''
        await interaction.response.send_modal(WelcomeEmbedDescriptionModal(parent_view=self, current_description=current_description)) # db_manager removido

    @ui.button(label="Cor do Embed", style=discord.ButtonStyle.green, row=1)
    async def set_welcome_embed_color(self, interaction: discord.Interaction, button: ui.Button):
        class WelcomeEmbedColorModal(ui.Modal, title="Cor do Embed de Boas-Vindas"):
            def __init__(self, parent_view: ui.View, current_color: str): # db_manager removido
                super().__init__()
                self.parent_view = parent_view
                self.db = parent_view.db # Armazena db_manager via parent_view
                self.add_item(ui.TextInput(label="Cor (Hex ou Decimal)", placeholder="#RRGGBB ou 0xRRGGBB ou número", style=discord.TextStyle.short, custom_id="embed_color", default=current_color, required=False))

            async def on_submit(self, interaction: discord.Interaction):
                await interaction.response.defer()
                original_view = self.parent_view
                embed_data = await original_view._get_welcome_embed_data() # Tornar assíncrono
                color_value = self.children[0].value.strip()
                embed_data['color'] = color_value if color_value else None
                await original_view._save_welcome_embed_data(embed_data) # Tornar assíncrono
                await original_view._update_welcome_display(interaction)
                await interaction.followup.send("Cor do Embed de Boas-Vindas atualizada!", ephemeral=True)
        
        embed_data = await self._get_welcome_embed_data() # Tornar assíncrono
        current_color = embed_data.get('color', '') or ''
        await interaction.response.send_modal(WelcomeEmbedColorModal(parent_view=self, current_color=current_color)) # db_manager removido

    @ui.button(label="Imagem do Embed", style=discord.ButtonStyle.green, row=2)
    async def set_welcome_embed_image(self, interaction: discord.Interaction, button: ui.Button):
        class WelcomeEmbedImageModal(ui.Modal, title="Imagem do Embed de Boas-Vindas"):
            def __init__(self, parent_view: ui.View, current_image_url: str): # db_manager removido
                super().__init__()
                self.parent_view = parent_view
                self.db = parent_view.db # Armazena db_manager via parent_view
                self.add_item(ui.TextInput(label="URL da Imagem", placeholder="URL da imagem (opcional)", style=discord.TextStyle.short, custom_id="embed_image", default=current_image_url, required=False))

            async def on_submit(self, interaction: discord.Interaction):
                await interaction.response.defer()
                original_view = self.parent_view
                embed_data = await original_view._get_welcome_embed_data() # Tornar assíncrono
                image_url = self.children[0].value.strip()
                embed_data['image_url'] = image_url if image_url else None
                await original_view._save_welcome_embed_data(embed_data) # Tornar assíncrono
                await original_view._update_welcome_display(interaction)
                await interaction.followup.send("Imagem do Embed de Boas-Vindas atualizada!", ephemeral=True)
        
        embed_data = await self._get_welcome_embed_data() # Tornar assíncrono
        current_image_url = embed_data.get('image_url', '') or ''
        await interaction.response.send_modal(WelcomeEmbedImageModal(parent_view=self, current_image_url=current_image_url)) # db_manager removido

    @ui.button(label="Rodapé do Embed", style=discord.ButtonStyle.green, row=2)
    async def set_welcome_embed_footer(self, interaction: discord.Interaction, button: ui.Button):
        class WelcomeEmbedFooterModal(ui.Modal, title="Rodapé do Embed de Boas-Vindas"):
            def __init__(self, parent_view: ui.View, current_footer_text: str, current_footer_icon_url: str): # db_manager removido
                super().__init__()
                self.parent_view = parent_view
                self.db = parent_view.db # Armazena db_manager via parent_view
                self.add_item(ui.TextInput(label="Texto do Rodapé", placeholder="Texto do rodapé (opcional)", style=discord.TextStyle.short, custom_id="footer_text", default=current_footer_text, required=False))
                self.add_item(ui.TextInput(label="URL do Ícone do Rodapé (Opcional)", placeholder="URL da imagem do ícone", style=discord.TextStyle.short, custom_id="footer_icon_url", default=current_footer_icon_url, required=False))

            async def on_submit(self, interaction: discord.Interaction):
                await interaction.response.defer()
                original_view = self.parent_view
                embed_data = await original_view._get_welcome_embed_data() # Tornar assíncrono
                footer_text = self.children[0].value.strip()
                footer_icon_url = self.children[1].value.strip()
                embed_data['footer_text'] = footer_text if footer_text else None
                embed_data['footer_icon_url'] = footer_icon_url if footer_icon_url else None
                await original_view._save_welcome_embed_data(embed_data) # Tornar assíncrono
                await original_view._update_welcome_display(interaction)
                await interaction.followup.send("Rodapé do Embed de Boas-Vindas atualizado!", ephemeral=True)
        
        embed_data = await self._get_welcome_embed_data() # Tornar assíncrono
        current_footer_text = embed_data.get('footer_text', '') or ''
        current_footer_icon_url = embed_data.get('footer_icon_url', '') or ''
        await interaction.response.send_modal(WelcomeEmbedFooterModal(parent_view=self, current_footer_text=current_footer_text, current_footer_icon_url=current_footer_icon_url)) # db_manager removido

    @ui.button(label="Autor do Embed", style=discord.ButtonStyle.green, row=2)
    async def set_welcome_embed_author(self, interaction: discord.Interaction, button: ui.Button):
        class WelcomeEmbedAuthorModal(ui.Modal, title="Autor do Embed de Boas-Vindas"):
            def __init__(self, parent_view: ui.View, current_author_name: str, current_author_icon_url: str): # db_manager removido
                super().__init__()
                self.parent_view = parent_view
                self.db = parent_view.db # Armazena db_manager
                self.add_item(ui.TextInput(label="Nome do Autor", placeholder="Nome do autor (opcional)", style=discord.TextStyle.short, custom_id="author_name", default=current_author_name, required=False))
                self.add_item(ui.TextInput(label="URL do Ícone do Autor (Opcional)", placeholder="URL da imagem do ícone", style=discord.TextStyle.short, custom_id="author_icon_url", default=current_author_icon_url, required=False))

            async def on_submit(self, interaction: discord.Interaction):
                await interaction.response.defer()
                original_view = self.parent_view
                embed_data = await original_view._get_welcome_embed_data()
                author_name = self.children[0].value.strip()
                author_icon_url = self.children[1].value.strip()
                embed_data['author_name'] = author_name if author_name else None
                embed_data['author_icon_url'] = author_icon_url if author_icon_url else None
                await original_view._save_welcome_embed_data(embed_data)
                await original_view._update_welcome_display(interaction)
                await interaction.followup.send("Autor do Embed de Boas-Vindas atualizado!", ephemeral=True)

        embed_data = await self._get_welcome_embed_data()
        current_author_name = embed_data.get('author_name', '') or ''
        current_author_icon_url = embed_data.get('author_icon_url', '') or ''
        await interaction.response.send_modal(WelcomeEmbedAuthorModal(parent_view=self, current_author_name=current_author_name, current_author_icon_url=current_author_icon_url)) # db_manager removido

    @ui.button(label="Voltar ao Painel Principal", style=discord.ButtonStyle.red, row=3)
    async def back_to_main_panel(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        for item in self.children:
            item.disabled = True
        await self.message.edit(view=self) # Desabilita esta view

        # Re-habilita os botões da view principal e a atualiza
        for item in self.parent_view.children:
            item.disabled = False
        await self.parent_view.message.edit(view=self.parent_view)
        await interaction.followup.send("Retornando ao painel principal.", ephemeral=True)


class LeaveConfigView(ui.View):
    def __init__(self, parent_view: ui.View, bot: commands.Bot, guild_id: int): # db_manager removido daqui
        super().__init__(timeout=180)
        self.parent_view = parent_view # A WelcomeSettingsView
        self.bot = bot
        self.guild_id = guild_id
        self.db = bot.db_connection # Armazena a instância do gerenciador de DB
        self.message = None

    async def on_timeout(self):
        if self.message:
            for item in self.children:
                item.disabled = True
            await self.message.edit(content="Sessão de configuração de Saídas expirada.", view=self)

    async def _update_leave_display(self, interaction: discord.Interaction):
        settings = None
        try:
            settings = await self.db.fetch_one( # Usando self.db
                "SELECT leave_enabled, leave_channel_id, leave_message, leave_embed_json FROM welcome_leave_messages WHERE guild_id = ?",
                (self.guild_id,)
            )
        except Exception as e:
            logging.error(f"Erro ao buscar configurações de saída do DB para guild {self.guild_id}: {e}", exc_info=True)
            # Continua com valores padrão se houver erro no DB
            settings = (False, None, None, None)

        embed = discord.Embed(
            title="Configurações de Saídas",
            description="Ajuste as mensagens e o embed para membros que saem.\n\n**Variáveis:** `{member}`, `{member.name}`, `{guild.name}`, `{member.count}`",
            color=discord.Color.red()
        )

        if settings:
            leave_enabled, lc_id, lm, leave_embed_json = settings
            
            leave_status = "🟢 Ativado" if leave_enabled else "🔴 Desativado"
            leave_channel = self.bot.get_channel(lc_id) if lc_id else "Nenhum"
            leave_message_preview = (lm[:50] + "..." if lm and len(lm) > 50 else lm) if lm else "Nenhuma"
            leave_embed_configured = "Sim" if leave_embed_json else "Não"
            
            embed.add_field(name="Status Geral", value=leave_status, inline=False)
            embed.add_field(name="Canal", value=getattr(leave_channel, 'mention', leave_channel), inline=False)
            embed.add_field(name="Mensagem de Texto", value=f"`{leave_message_preview}`", inline=False)
            embed.add_field(name="Embed Configurado", value=leave_embed_configured, inline=False)

            # Pré-visualização do embed de saídas (se configurado)
            preview_embed = None # Initialize preview_embed
            if leave_embed_json:
                try:
                    embed_data = json.loads(leave_embed_json)
                    preview_embed = _create_embed_from_data(embed_data, member=interaction.user, guild=interaction.guild) # Usar interaction.user/guild para preview
                    embed.add_field(name="Pré-visualização do Embed", value="Veja abaixo:", inline=False)
                except json.JSONDecodeError:
                    logging.error(f"Erro ao decodificar JSON do leave embed para guild {self.guild_id} na preview.")
                    preview_embed = None
            else:
                preview_embed = None
        else:
            embed.add_field(name="Status", value="🔴 Desativado (Padrões)", inline=False)
            embed.set_footer(text="Nenhuma configuração salva. Use os botões para configurar.")
            preview_embed = None # Initialize preview_embed for this path too
        
        embeds_to_send = [embed]
        if preview_embed:
            embeds_to_send.append(preview_embed)

        if self.message:
            await self.message.edit(embeds=embeds_to_send, view=self)
        else:
            if interaction.response.is_done():
                self.message = await interaction.followup.send(embeds=embeds_to_send, view=self, ephemeral=True)
            else:
                await interaction.response.send_message(embeds=embeds_to_send, view=self, ephemeral=True)
                self.message = await interaction.original_response()

    # Helpers para carregar/salvar embed JSON de saída
    async def _get_leave_embed_data(self): # Tornar assíncrono
        settings = await self.db.fetch_one("SELECT leave_embed_json FROM welcome_leave_messages WHERE guild_id = ?", (self.guild_id,)) # Usando self.db
        if settings and settings[0]:
            try:
                return json.loads(settings[0])
            except json.JSONDecodeError:
                logging.error(f"Erro ao decodificar JSON do leave embed para guild {self.guild_id}. Retornando vazio.")
                return {}
        return {}

    async def _save_leave_embed_data(self, embed_data: dict): # Tornar assíncrono
        embed_json = json.dumps(embed_data)
        try:
            await self.db.execute_query( # Usando self.db
                "INSERT OR REPLACE INTO welcome_leave_messages (guild_id, leave_embed_json) VALUES (?, ?)",
                (self.guild_id, embed_json)
            )
        except Exception as e:
            logging.error(f"Erro ao salvar leave embed data no DB para guild {self.guild_id}: {e}", exc_info=True)

    @ui.button(label="Alternar Status", style=discord.ButtonStyle.primary, row=0)
    async def toggle_leave_status(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        current_status = await self.db.fetch_one("SELECT leave_enabled FROM welcome_leave_messages WHERE guild_id = ?", (self.guild_id,)) # Usando self.db
        new_status = not current_status[0] if current_status and current_status[0] is not None else True # Handle None or 0
        
        try:
            await self.db.execute_query( # Usando self.db
                "INSERT OR REPLACE INTO welcome_leave_messages (guild_id, leave_enabled) VALUES (?, ?)",
                (self.guild_id, new_status)
            )
            await self._update_leave_display(interaction)
            await interaction.followup.send(f"Mensagens de Saída {('ativadas' if new_status else 'desativadas')}!", ephemeral=True)
        except Exception as e:
            logging.error(f"Erro ao alternar status de saída no DB para guild {self.guild_id}: {e}", exc_info=True)
            await interaction.followup.send("Ocorreu um erro ao atualizar o status de saída.", ephemeral=True)

    @ui.button(label="Definir Canal", style=discord.ButtonStyle.secondary, row=0)
    async def set_leave_channel(self, interaction: discord.Interaction, button: ui.Button):
        class LeaveChannelModal(ui.Modal, title="Definir Canal de Saídas"):
            def __init__(self, parent_view: ui.View, current_channel_id: int): # db_manager removido
                super().__init__()
                self.parent_view = parent_view
                self.db = parent_view.db # Armazena db_manager via parent_view
                default_value = str(current_channel_id) if current_channel_id else ""
                self.add_item(ui.TextInput(label="ID do Canal", placeholder="Ex: 123456789012345678", style=discord.TextStyle.short, custom_id="channel_id", default=default_value))

            async def on_submit(self, interaction: discord.Interaction):
                await interaction.response.defer()
                original_view = self.parent_view
                try:
                    channel_id = int(self.children[0].value)
                    channel = original_view.bot.get_channel(channel_id)
                    if not isinstance(channel, discord.TextChannel):
                        await interaction.followup.send("ID de canal inválido ou não é um canal de texto.", ephemeral=True)
                        return

                    try:
                        await self.db.execute_query( # Usando self.db
                            "INSERT OR REPLACE INTO welcome_leave_messages (guild_id, leave_channel_id) VALUES (?, ?)",
                            (original_view.guild_id, channel_id)
                        )
                        await original_view._update_leave_display(interaction)
                        await interaction.followup.send(f"Canal de Saídas definido para {channel.mention}.", ephemeral=True)
                    except Exception as e:
                        logging.error(f"Erro ao definir canal de saídas no DB para guild {original_view.guild_id}: {e}", exc_info=True)
                        await interaction.followup.send("Ocorreu um erro ao salvar o canal no banco de dados.", ephemeral=True)
                except ValueError:
                    await interaction.followup.send("ID de canal inválido. Por favor, insira um número.", ephemeral=True)
        
        current_settings = await self.db.fetch_one("SELECT leave_channel_id FROM welcome_leave_messages WHERE guild_id = ?", (self.guild_id,)) # Usando self.db
        current_channel_id = current_settings[0] if current_settings else None
        await interaction.response.send_modal(LeaveChannelModal(parent_view=self, current_channel_id=current_channel_id)) # db_manager removido

    @ui.button(label="Definir Mensagem de Texto", style=discord.ButtonStyle.secondary, row=0)
    async def set_leave_message(self, interaction: discord.Interaction, button: ui.Button):
        class LeaveMessageModal(ui.Modal, title="Definir Mensagem de Saídas"):
            def __init__(self, parent_view: ui.View, current_message: str): # db_manager removido
                super().__init__()
                self.parent_view = parent_view
                self.db = parent_view.db # Armazena db_manager via parent_view
                self.add_item(ui.TextInput(label="Mensagem", placeholder="Use {member}, {guild.name}, {member.count}", style=discord.TextStyle.paragraph, custom_id="leave_message", default=current_message, required=False))

            async def on_submit(self, interaction: discord.Interaction):
                await interaction.response.defer()
                original_view = self.parent_view
                message_content = self.children[0].value if self.children[0].value.strip() else None

                try:
                    await self.db.execute_query( # Usando self.db
                        "INSERT OR REPLACE INTO welcome_leave_messages (guild_id, leave_message) VALUES (?, ?)",
                        (original_view.guild_id, message_content)
                    )
                    await original_view._update_leave_display(interaction)
                    await interaction.followup.send("Mensagem de Saídas atualizada!", ephemeral=True)
                except Exception as e:
                    logging.error(f"Erro ao definir mensagem de saídas no DB para guild {original_view.guild_id}: {e}", exc_info=True)
                    await interaction.followup.send("Ocorreu um erro ao salvar a mensagem no banco de dados.", ephemeral=True)
        
        current_settings = await self.db.fetch_one("SELECT leave_message FROM welcome_leave_messages WHERE guild_id = ?", (self.guild_id,)) # Usando self.db
        current_message = current_settings[0] if current_settings and current_settings[0] else ""
        await interaction.response.send_modal(LeaveMessageModal(parent_view=self, current_message=current_message)) # db_manager removido

    @ui.button(label="Título do Embed", style=discord.ButtonStyle.green, row=1)
    async def set_leave_embed_title(self, interaction: discord.Interaction, button: ui.Button):
        class LeaveEmbedTitleModal(ui.Modal, title="Título do Embed de Saídas"):
            def __init__(self, parent_view: ui.View, current_title: str): # db_manager removido
                super().__init__()
                self.parent_view = parent_view
                self.db = parent_view.db # Armazena db_manager via parent_view
                self.add_item(ui.TextInput(label="Título", placeholder="Título do embed (use variáveis)", style=discord.TextStyle.short, custom_id="embed_title", default=current_title, required=False))

            async def on_submit(self, interaction: discord.Interaction):
                await interaction.response.defer()
                original_view = self.parent_view
                embed_data = await original_view._get_leave_embed_data() # Tornar assíncrono
                embed_data['title'] = self.children[0].value if self.children[0].value.strip() else None
                await original_view._save_leave_embed_data(embed_data) # Tornar assíncrono
                await original_view._update_leave_display(interaction)
                await interaction.followup.send("Título do Embed de Saídas atualizado!", ephemeral=True)
        
        embed_data = await self._get_leave_embed_data() # Tornar assíncrono
        current_title = embed_data.get('title', '') or ''
        await interaction.response.send_modal(LeaveEmbedTitleModal(parent_view=self, current_title=current_title)) # db_manager removido

    @ui.button(label="Descrição do Embed", style=discord.ButtonStyle.green, row=1)
    async def set_leave_embed_description(self, interaction: discord.Interaction, button: ui.Button):
        class LeaveEmbedDescriptionModal(ui.Modal, title="Descrição do Embed de Saídas"):
            def __init__(self, parent_view: ui.View, current_description: str): # db_manager removido
                super().__init__()
                self.parent_view = parent_view
                self.db = parent_view.db # Armazena db_manager via parent_view
                self.add_item(ui.TextInput(label="Descrição", placeholder="Descrição do embed (use variáveis)", style=discord.TextStyle.paragraph, custom_id="embed_description", default=current_description, required=False))

            async def on_submit(self, interaction: discord.Interaction):
                await interaction.response.defer()
                original_view = self.parent_view
                embed_data = await original_view._get_leave_embed_data() # Tornar assíncrono
                embed_data['description'] = self.children[0].value if self.children[0].value.strip() else None
                await original_view._save_leave_embed_data(embed_data) # Tornar assíncrono
                await original_view._update_leave_display(interaction)
                await interaction.followup.send("Descrição do Embed de Saídas atualizada!", ephemeral=True)
        
        embed_data = await self._get_leave_embed_data() # Tornar assíncrono
        current_description = embed_data.get('description', '') or ''
        await interaction.response.send_modal(LeaveEmbedDescriptionModal(parent_view=self, current_description=current_description)) # db_manager removido

    @ui.button(label="Cor do Embed", style=discord.ButtonStyle.green, row=1)
    async def set_leave_embed_color(self, interaction: discord.Interaction, button: ui.Button):
        class LeaveEmbedColorModal(ui.Modal, title="Cor do Embed de Saídas"):
            def __init__(self, parent_view: ui.View, current_color: str): # db_manager removido
                super().__init__()
                self.parent_view = parent_view
                self.db = parent_view.db # Armazena db_manager via parent_view
                self.add_item(ui.TextInput(label="Cor (Hex ou Decimal)", placeholder="#RRGGBB ou 0xRRGGBB ou número", style=discord.TextStyle.short, custom_id="embed_color", default=current_color, required=False))

            async def on_submit(self, interaction: discord.Interaction):
                await interaction.response.defer()
                original_view = self.parent_view
                embed_data = await original_view._get_leave_embed_data() # Tornar assíncrono
                color_value = self.children[0].value.strip()
                embed_data['color'] = color_value if color_value else None
                await original_view._save_leave_embed_data(embed_data) # Tornar assíncrono
                await original_view._update_leave_display(interaction)
                await interaction.followup.send("Cor do Embed de Saídas atualizada!", ephemeral=True)
        
        embed_data = await self._get_leave_embed_data() # Tornar assíncrono
        current_color = embed_data.get('color', '') or ''
        await interaction.response.send_modal(LeaveEmbedColorModal(parent_view=self, current_color=current_color)) # db_manager removido

    @ui.button(label="Imagem do Embed", style=discord.ButtonStyle.green, row=2)
    async def set_leave_embed_image(self, interaction: discord.Interaction, button: ui.Button):
        class LeaveEmbedImageModal(ui.Modal, title="Imagem do Embed de Saídas"):
            def __init__(self, parent_view: ui.View, current_image_url: str): # db_manager removido
                super().__init__()
                self.parent_view = parent_view
                self.db = parent_view.db # Armazena db_manager via parent_view
                self.add_item(ui.TextInput(label="URL da Imagem", placeholder="URL da imagem (opcional)", style=discord.TextStyle.short, custom_id="embed_image", default=current_image_url, required=False))

            async def on_submit(self, interaction: discord.Interaction):
                await interaction.response.defer()
                original_view = self.parent_view
                embed_data = await original_view._get_leave_embed_data() # Tornar assíncrono
                image_url = self.children[0].value.strip()
                embed_data['image_url'] = image_url if image_url else None
                await original_view._save_leave_embed_data(embed_data) # Tornar assíncrono
                await original_view._update_leave_display(interaction)
                await interaction.followup.send("Imagem do Embed de Saídas atualizada!", ephemeral=True)
        
        embed_data = await self._get_leave_embed_data() # Tornar assíncrono
        current_image_url = embed_data.get('image_url', '') or ''
        await interaction.response.send_modal(LeaveEmbedImageModal(parent_view=self, current_image_url=current_image_url)) # db_manager removido

    @ui.button(label="Rodapé do Embed", style=discord.ButtonStyle.green, row=2)
    async def set_leave_embed_footer(self, interaction: discord.Interaction, button: ui.Button):
        class LeaveEmbedFooterModal(ui.Modal, title="Rodapé do Embed de Saídas"):
            def __init__(self, parent_view: ui.View, current_footer_text: str, current_footer_icon_url: str): # db_manager removido
                super().__init__()
                self.parent_view = parent_view
                self.db = parent_view.db # Armazena db_manager via parent_view
                self.add_item(ui.TextInput(label="Texto do Rodapé", placeholder="Texto do rodapé (opcional)", style=discord.TextStyle.short, custom_id="footer_text", default=current_footer_text, required=False))
                self.add_item(ui.TextInput(label="URL do Ícone do Rodapé (Opcional)", placeholder="URL da imagem do ícone", style=discord.TextStyle.short, custom_id="footer_icon_url", default=current_footer_icon_url, required=False))

            async def on_submit(self, interaction: discord.Interaction):
                await interaction.response.defer()
                original_view = self.parent_view
                embed_data = await original_view._get_leave_embed_data() # Tornar assíncrono
                footer_text = self.children[0].value.strip()
                footer_icon_url = self.children[1].value.strip()
                embed_data['footer_text'] = footer_text if footer_text else None
                embed_data['footer_icon_url'] = footer_icon_url if footer_icon_url else None
                await original_view._save_leave_embed_data(embed_data) # Tornar assíncrono
                await original_view._update_leave_display(interaction)
                await interaction.followup.send("Rodapé do Embed de Saídas atualizado!", ephemeral=True)
        
        embed_data = await self._get_leave_embed_data() # Tornar assíncrono
        current_footer_text = embed_data.get('footer_text', '') or ''
        current_footer_icon_url = embed_data.get('footer_icon_url', '') or ''
        await interaction.response.send_modal(LeaveEmbedFooterModal(parent_view=self, current_footer_text=current_footer_text, current_footer_icon_url=current_footer_icon_url)) # db_manager removido

    @ui.button(label="Autor do Embed", style=discord.ButtonStyle.green, row=2)
    async def set_leave_embed_author(self, interaction: discord.Interaction, button: ui.Button):
        class LeaveEmbedAuthorModal(ui.Modal, title="Autor do Embed de Saídas"):
            def __init__(self, parent_view: ui.View, current_author_name: str, current_author_icon_url: str): # db_manager removido
                super().__init__()
                self.parent_view = parent_view
                self.db = parent_view.db # Armazena db_manager
                self.add_item(ui.TextInput(label="Nome do Autor", placeholder="Nome do autor (opcional)", style=discord.TextStyle.short, custom_id="author_name", default=current_author_name, required=False))
                self.add_item(ui.TextInput(label="URL do Ícone do Autor (Opcional)", placeholder="URL da imagem do ícone", style=discord.TextStyle.short, custom_id="author_icon_url", default=current_author_icon_url, required=False))

            async def on_submit(self, interaction: discord.Interaction):
                await interaction.response.defer()
                original_view = self.parent_view
                embed_data = await original_view._get_leave_embed_data()
                author_name = self.children[0].value.strip()
                author_icon_url = self.children[1].value.strip()
                embed_data['author_name'] = author_name if author_name else None
                embed_data['author_icon_url'] = author_icon_url if author_icon_url else None
                await original_view._save_leave_embed_data(embed_data)
                await original_view._update_leave_display(interaction)
                await interaction.followup.send("Autor do Embed de Saídas atualizado!", ephemeral=True)

        embed_data = await self._get_leave_embed_data()
        current_author_name = embed_data.get('author_name', '') or ''
        current_author_icon_url = embed_data.get('author_icon_url', '') or ''
        await interaction.response.send_modal(LeaveEmbedAuthorModal(parent_view=self, current_author_name=current_author_name, current_author_icon_url=current_author_icon_url)) # db_manager removido

    @ui.button(label="Voltar ao Painel Principal", style=discord.ButtonStyle.red, row=3)
    async def back_to_main_panel(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        for item in self.children:
            item.disabled = True
        await self.message.edit(view=self) # Desabilita esta view

        # Re-habilita os botões da view principal e a atualiza
        for item in self.parent_view.children:
            item.disabled = False
        await self.parent_view.message.edit(view=self.parent_view)
        await interaction.followup.send("Retornando ao painel principal.", ephemeral=True)

class WelcomeLeaveSystem(commands.Cog):
    def __init__(self, bot: commands.Bot): # db_manager removido daqui
        self.bot = bot
        self.db = bot.db_connection # Armazena a instância do gerenciador de DB
        self.bot.loop.create_task(self.ensure_persistent_views())

    async def ensure_persistent_views(self):
        await self.bot.wait_until_ready()
        logging.info("Tentando carregar painéis de Boas-Vindas/Saídas persistentes...")
        panel_datas = []
        try:
            panel_datas = await self.db.fetch_all("SELECT guild_id, panel_channel_id, panel_message_id FROM welcome_leave_panel_settings") # Usando self.db
        except Exception as e:
            logging.error(f"Erro ao buscar painéis persistentes de Boas-Vindas/Saídas do DB: {e}", exc_info=True)
            return # Aborta se houver erro no DB

        logging.info(f"[ensure_persistent_views] Dados lidos do DB: {panel_datas}")
        
        if panel_datas:
            for guild_id, channel_id, message_id in panel_datas:
                if channel_id is None or message_id is None:
                    logging.warning(f"[ensure_persistent_views] Pulando entrada inválida no DB para guild {guild_id} (channel_id ou message_id é None). Removendo do DB.")
                    try:
                        await self.db.execute_query("DELETE FROM welcome_leave_panel_settings WHERE guild_id = ?", (guild_id,)) # Usando self.db
                    except Exception as e:
                        logging.error(f"Erro ao deletar entrada inválida do painel de Boas-Vindas/Saídas no DB: {e}", exc_info=True)
                    continue 
                
                try:
                    guild = self.bot.get_guild(guild_id)
                    if not guild:
                        logging.warning(f"Guild {guild_id} não encontrada para painel persistente de Boas-Vindas/Saídas. Removendo do DB.")
                        try:
                            await self.db.execute_query("DELETE FROM welcome_leave_panel_settings WHERE guild_id = ?", (guild_id,)) # Usando self.db
                        except Exception as e:
                            logging.error(f"Erro ao deletar painel de Boas-Vindas/Saídas do DB após guild não encontrada: {e}", exc_info=True)
                        continue
                    
                    channel = await guild.fetch_channel(channel_id)
                    if not isinstance(channel, discord.TextChannel):
                        logging.warning(f"Canal {channel_id} não é de texto para painel persistente de Boas-Vindas/Saídas na guild {guild_id}. Removendo do DB.")
                        try:
                            await self.db.execute_query("DELETE FROM welcome_leave_panel_settings WHERE guild_id = ?", (guild_id,)) # Usando self.db
                        except Exception as e:
                            logging.error(f"Erro ao deletar painel de Boas-Vindas/Saídas do DB após canal não ser de texto: {e}", exc_info=True)
                        continue

                    message = await channel.fetch_message(message_id)
                    view = WelcomeLeaveSettingsView(self.bot, guild_id) # db_manager removido daqui
                    view.message = message 
                    self.bot.add_view(view, message_id=message.id)
                    logging.info(f"Painel de Boas-Vindas/Saídas persistente carregado para guild {guild_id} no canal {channel_id}, mensagem {message_id}.")
                except discord.NotFound:
                    logging.warning(f"Mensagem do painel de Boas-Vindas/Saídas ({message_id}) ou canal ({channel_id}) não encontrada. Removendo do DB para evitar carregamentos futuros.")
                    try:
                        await self.db.execute_query("DELETE FROM welcome_leave_panel_settings WHERE message_id = ?", (message_id,)) # Usando self.db
                    except Exception as e:
                        logging.error(f"Erro ao deletar painel de Boas-Vindas/Saídas do DB após mensagem/canal não encontrado: {e}", exc_info=True)
                except discord.Forbidden:
                    logging.error(f"Bot sem permissão para acessar o canal {channel_id} ou mensagem {message_id} na guild {guild_id}. Não foi possível carregar o painel persistente.")
                except Exception as e:
                    logging.error(f"Erro inesperado ao carregar painel persistente para guild {guild_id}, mensagem {message_id}: {e}", exc_info=True)
        else:
            logging.info("Nenhum painel de Boas-Vindas/Saídas persistente para carregar.")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return

        settings = None
        try:
            settings = await self.db.fetch_one(
                "SELECT welcome_enabled, welcome_channel_id, welcome_message, welcome_embed_json FROM welcome_leave_messages WHERE guild_id = ?",
                (member.guild.id,)
            )
        except Exception as e:
            logging.error(f"Erro ao buscar configurações de boas-vindas para guild {member.guild.id} no on_member_join: {e}", exc_info=True)
            return

        if not settings or not settings[0]: # welcome_enabled
            return

        welcome_enabled, channel_id, message_content, embed_json = settings

        if not welcome_enabled or not channel_id:
            return

        channel = self.bot.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            logging.warning(f"Canal de boas-vindas {channel_id} não encontrado ou não é um canal de texto para guild {member.guild.id}.")
            return

        try:
            embed = None
            if embed_json:
                try:
                    embed_data = json.loads(embed_json)
                    embed = _create_embed_from_data(embed_data, member=member, guild=member.guild)
                except json.JSONDecodeError:
                    logging.error(f"Erro ao decodificar JSON do welcome embed para guild {member.guild.id}.")
            
            formatted_message = message_content.format(
                member=member.mention,
                member_name=member.display_name,
                guild_name=member.guild.name,
                member_count=member.guild.member_count
            ) if message_content else None

            if formatted_message or embed:
                await channel.send(content=formatted_message, embed=embed)
                logging.info(f"Mensagem de boas-vindas enviada para {member.name} na guild {member.guild.name}.")
            else:
                logging.info(f"Nenhuma mensagem de texto ou embed configurado para boas-vindas na guild {member.guild.id}.")
        except discord.Forbidden:
            logging.error(f"Bot sem permissão para enviar mensagem no canal de boas-vindas {channel.name} ({channel.id}) na guild {member.guild.id}.")
        except Exception as e:
            logging.error(f"Erro ao enviar mensagem de boas-vindas para {member.name} na guild {member.guild.id}: {e}", exc_info=True)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.bot:
            return

        settings = None
        try:
            settings = await self.db.fetch_one(
                "SELECT leave_enabled, leave_channel_id, leave_message, leave_embed_json FROM welcome_leave_messages WHERE guild_id = ?",
                (member.guild.id,)
            )
        except Exception as e:
            logging.error(f"Erro ao buscar configurações de saída para guild {member.guild.id} no on_member_remove: {e}", exc_info=True)
            return

        if not settings or not settings[0]: # leave_enabled
            return

        leave_enabled, channel_id, message_content, embed_json = settings

        if not leave_enabled or not channel_id:
            return

        channel = self.bot.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            logging.warning(f"Canal de saídas {channel_id} não encontrado ou não é um canal de texto para guild {member.guild.id}.")
            return

        try:
            embed = None
            if embed_json:
                try:
                    embed_data = json.loads(embed_json)
                    embed = _create_embed_from_data(embed_data, member=member, guild=member.guild)
                except json.JSONDecodeError:
                    logging.error(f"Erro ao decodificar JSON do leave embed para guild {member.guild.id}.")
            
            formatted_message = message_content.format(
                member=member.display_name, # Para saídas, geralmente o nome é suficiente, pois o mention não funciona mais
                guild_name=member.guild.name,
                member_count=member.guild.member_count
            ) if message_content else None

            if formatted_message or embed:
                await channel.send(content=formatted_message, embed=embed)
                logging.info(f"Mensagem de saída enviada para {member.name} na guild {member.guild.name}.")
            else:
                logging.info(f"Nenhuma mensagem de texto ou embed configurado para saídas na guild {member.guild.id}.")
        except discord.Forbidden:
            logging.error(f"Bot sem permissão para enviar mensagem no canal de saídas {channel.name} ({channel.id}) na guild {member.guild.id}.")
        except Exception as e:
            logging.error(f"Erro ao enviar mensagem de saída para {member.name} na guild {member.guild.id}: {e}", exc_info=True)

    @app_commands.command(name="welcome_leave_panel", description="Configura o painel de boas-vindas e saídas.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_welcome_leave_panel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild.id

        old_panel_data = None
        try:
            old_panel_data = await self.db.fetch_one(
                "SELECT panel_channel_id, panel_message_id FROM welcome_leave_panel_settings WHERE guild_id = ?",
                (guild_id,)
            )
        except Exception as e:
            logging.error(f"Erro ao buscar dados antigos do painel de boas-vindas/saídas no DB para guild {guild_id}: {e}", exc_info=True)
            await interaction.followup.send("Ocorreu um erro ao buscar configurações antigas do painel.", ephemeral=True)
            return

        if old_panel_data and (old_panel_data[0] is not None and old_panel_data[1] is not None): 
            old_channel_id, old_message_id = old_panel_data
            try:
                old_channel = await interaction.guild.fetch_channel(old_channel_id)
                if isinstance(old_channel, discord.TextChannel):
                    old_message = await old_channel.fetch_message(old_message_id)
                    await old_message.delete()
                    logging.info(f"[setup_welcome_leave_panel] Mensagem do painel antigo ({old_message_id}) deletada do canal {old_channel_id}.")
                else:
                    logging.warning(f"[setup_welcome_leave_panel] Canal antigo {old_channel_id} não é de texto. Não foi possível deletar a mensagem.")
            except discord.NotFound:
                logging.warning(f"[setup_welcome_leave_panel] Mensagem do painel antigo ({old_message_id}) não encontrada para deletar no canal {old_channel_id}.")
            except discord.Forbidden:
                logging.error(f"[setup_welcome_leave_panel] Bot sem permissão para deletar a mensagem do painel antigo ({old_message_id}) no canal {old_channel_id}. Verifique as permissões 'Gerenciar Mensagens'.")
            except Exception as e:
                logging.error(f"[setup_welcome_leave_panel] Erro ao deletar painel antigo: {e}", exc_info=True)
            
            try:
                await self.db.execute_query("DELETE FROM welcome_leave_panel_settings WHERE guild_id = ?", (guild_id,))
            except Exception as e:
                logging.error(f"Erro ao deletar entrada antiga do painel de boas-vindas/saídas do DB para guild {guild_id}: {e}", exc_info=True)
        elif old_panel_data: 
            logging.warning(f"[setup_welcome_leave_panel] Entrada antiga de painel com IDs None para guild {guild_id}. Apenas deletando do DB.")
            try:
                await self.db.execute_query("DELETE FROM welcome_leave_panel_settings WHERE guild_id = ?", (guild_id,))
            except Exception as e:
                logging.error(f"Erro ao deletar entrada inválida do painel de boas-vindas/saídas do DB: {e}", exc_info=True)

        embed = discord.Embed(
            title="Painel de Boas-Vindas e Saídas",
            description="Use os botões para configurar as mensagens de boas-vindas e saídas.",
            color=discord.Color.purple()
        )
        embed.set_footer(text="As mensagens serão enviadas no canal configurado.")

        view = WelcomeLeaveSettingsView(self.bot, guild_id)
        
        try:
            panel_message = await interaction.channel.send(embed=embed, view=view)
            view.message = panel_message 

            logging.info(f"[setup_welcome_leave_panel] Tentando salvar no DB: guild_id={guild_id}, channel_id={interaction.channel.id}, message_id={panel_message.id}")

            success_db_insert = await self.db.execute_query(
                "INSERT OR REPLACE INTO welcome_leave_panel_settings (guild_id, panel_channel_id, panel_message_id) VALUES (?, ?, ?)",
                (guild_id, interaction.channel.id, panel_message.id)
            )
            if success_db_insert:
                logging.info(f"[setup_welcome_leave_panel] Dados do painel de boas-vindas/saídas salvos com sucesso no DB para guild {guild_id}.")
            else:
                logging.error(f"[setup_welcome_leave_panel] Falha ao salvar dados do painel de boas-vindas/saídas no DB para guild {guild_id}.")

            self.bot.add_view(view, message_id=panel_message.id) 
            await interaction.followup.send(f"Painel de Boas-Vindas e Saídas configurado neste canal: {interaction.channel.mention}", ephemeral=True)
            logging.info(f"Painel de Boas-Vindas e Saídas configurado/movido por {interaction.user.id} para canal {interaction.channel.id} na guild {guild_id}. Mensagem ID: {panel_message.id}.")
        except discord.Forbidden:
            await interaction.followup.send("Não tenho permissão para enviar mensagens neste canal. Por favor, verifique as minhas permissões.", ephemeral=True)
            logging.error(f"Bot sem permissão para enviar painel de boas-vindas/saídas no canal {interaction.channel.id} na guild {guild_id}.")
        except Exception as e:
            await interaction.followup.send(f"Ocorreu um erro ao configurar o painel: {e}", ephemeral=True)
            logging.error(f"Erro inesperado ao configurar painel de boas-vindas/saídas na guild {guild_id}: {e}", exc_info=True)

    @app_commands.command(name="delete_welcome_leave_panel", description="Deleta o painel de boas-vindas e saídas existente.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def delete_welcome_leave_panel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild.id
        
        panel_data = None
        try:
            panel_data = await self.db.fetch_one(
                "SELECT panel_channel_id, panel_message_id FROM welcome_leave_panel_settings WHERE guild_id = ?",
                (guild_id,)
            )
        except Exception as e:
            logging.error(f"Erro ao buscar dados do painel de boas-vindas/saídas para deletar no DB para guild {guild_id}: {e}", exc_info=True)
            await interaction.followup.send("Ocorreu um erro ao buscar o painel para deletar.", ephemeral=True)
            return

        if not panel_data:
            await interaction.followup.send("Nenhum painel de boas-vindas e saídas encontrado para deletar.", ephemeral=True)
            logging.info(f"Tentativa de deletar painel de boas-vindas/saídas, mas nenhum painel encontrado para guild {guild_id}.")
            return

        channel_id, message_id = panel_data
        
        if channel_id is None or message_id is None:
            logging.warning(f"Entrada inválida no DB para guild {guild_id} (channel_id ou message_id é None). Apenas deletando do DB.")
            try:
                await self.db.execute_query("DELETE FROM welcome_leave_panel_settings WHERE guild_id = ?", (guild_id,))
            except Exception as e:
                logging.error(f"Erro ao deletar entrada inválida do painel de boas-vindas/saídas do DB: {e}", exc_info=True)
            await interaction.followup.send("Painel de boas-vindas e saídas deletado com sucesso (entrada inválida no DB).", ephemeral=True)
            return

        try:
            channel = await interaction.guild.fetch_channel(channel_id)
            if isinstance(channel, discord.TextChannel):
                message = await channel.fetch_message(message_id)
                await message.delete()
                logging.info(f"Mensagem do painel de boas-vindas/saídas ({message_id}) deletada do canal {channel_id}.")
                
                # Após deletar a mensagem, remova a entrada do DB
                success_db_delete = await self.db.execute_query("DELETE FROM welcome_leave_panel_settings WHERE guild_id = ?", (guild_id,))
                if success_db_delete:
                    logging.info(f"Entrada do painel de boas-vindas/saídas deletada do DB para guild {guild_id}.")
                    await interaction.followup.send("Painel de boas-vindas e saídas deletado com sucesso.", ephemeral=True)
                else:
                    logging.error(f"Falha ao deletar entrada do painel de boas-vindas/saídas do DB para guild {guild_id}.")
                    await interaction.followup.send("Painel deletado do Discord, mas ocorreu um erro ao remover a entrada do banco de dados.", ephemeral=True)
            else:
                logging.warning(f"Canal {channel_id} não é de texto. Não foi possível deletar a mensagem do painel.")
                await interaction.followup.send("O canal do painel não é um canal de texto válido. Removendo a entrada do banco de dados.", ephemeral=True)
                try:
                    await self.db.execute_query("DELETE FROM welcome_leave_panel_settings WHERE guild_id = ?", (guild_id,))
                except Exception as e:
                    logging.error(f"Erro ao deletar entrada do painel de boas-vindas/saídas do DB após canal inválido: {e}", exc_info=True)
        except discord.NotFound:
            logging.warning(f"Mensagem do painel de boas-vindas/saídas ({message_id}) ou canal ({channel_id}) não encontrada. Removendo do DB.")
            try:
                await self.db.execute_query("DELETE FROM welcome_leave_panel_settings WHERE guild_id = ?", (guild_id,))
            except Exception as e:
                logging.error(f"Erro ao deletar entrada do painel de boas-vindas/saídas do DB após mensagem/canal não encontrado: {e}", exc_info=True)
            await interaction.followup.send("Painel de boas-vindas e saídas não encontrado no Discord, mas a entrada foi removida do banco de dados.", ephemeral=True)
        except discord.Forbidden:
            logging.error(f"Bot sem permissão para deletar a mensagem do painel ({message_id}) no canal {channel_id}. Verifique as permissões 'Gerenciar Mensagens'.")
            await interaction.followup.send("Não tenho permissão para deletar a mensagem do painel. Por favor, verifique as minhas permissões.", ephemeral=True)
        except Exception as e:
            logging.error(f"Erro inesperado ao deletar painel de boas-vindas/saídas: {e}", exc_info=True)
            await interaction.followup.send(f"Ocorreu um erro ao deletar o painel: {e}", ephemeral=True)

class WelcomeLeaveSettingsView(ui.View):
    def __init__(self, bot: commands.Bot, guild_id: int): # db_manager removido
        super().__init__(timeout=180)
        self.bot = bot
        self.guild_id = guild_id
        self.db = bot.db_connection # Armazena a instância do gerenciador de DB
        self.message = None

    async def on_timeout(self):
        if self.message:
            for item in self.children:
                item.disabled = True
            await self.message.edit(content="Sessão do painel de Boas-Vindas/Saídas expirada.", view=self)

    async def _update_main_panel_display(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Painel de Boas-Vindas e Saídas",
            description="Use os botões para configurar as mensagens de boas-vindas e saídas.",
            color=discord.Color.purple()
        )
        embed.set_footer(text="As mensagens serão enviadas no canal configurado.")

        if self.message:
            await self.message.edit(embed=embed, view=self)
        else:
            if interaction.response.is_done():
                self.message = await interaction.followup.send(embed=embed, view=self, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, view=self, ephemeral=True)
                self.message = await interaction.original_response()

    @ui.button(label="Configurar Boas-Vindas", style=discord.ButtonStyle.blurple, row=0)
    async def configure_welcome(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        for item in self.children:
            item.disabled = True
        await self.message.edit(view=self) # Desabilita esta view

        welcome_config_view = WelcomeConfigView(parent_view=self, bot=self.bot, guild_id=self.guild_id) # db_manager removido
        await welcome_config_view._update_welcome_display(interaction)
        welcome_config_view.message = await interaction.original_response() # Captura a mensagem enviada pelo _update_welcome_display

    @ui.button(label="Configurar Saídas", style=discord.ButtonStyle.blurple, row=0)
    async def configure_leave(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        for item in self.children:
            item.disabled = True
        await self.message.edit(view=self) # Desabilita esta view

        leave_config_view = LeaveConfigView(parent_view=self, bot=self.bot, guild_id=self.guild_id) # db_manager removido
        await leave_config_view._update_leave_display(interaction)
        leave_config_view.message = await interaction.original_response() # Captura a mensagem enviada pelo _update_leave_display


async def setup(bot: commands.Bot): # db_manager removido daqui
    """
    Função de setup para adicionar o cog ao bot.
    """
    await bot.add_cog(WelcomeLeaveSystem(bot)) # db_manager removido daqui
    logging.info("WelcomeLeaveSystem cog adicionado ao bot.")
