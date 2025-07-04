import discord
from discord.ext import commands
from discord import app_commands, ui
import json
import os
import datetime
import logging
import asyncio # Para usar bot.wait_for

# Configuração de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Funções Auxiliares para Embeds (Reutilizadas do Welcome/Leave) ---
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

# View para gerenciar campos de embed
class FieldManagementView(ui.View):
    def __init__(self, parent_view: ui.View, bot: commands.Bot): # db_manager removido daqui
        super().__init__(timeout=180) # Timeout de 3 minutos para a sessão de campos
        self.parent_view = parent_view # Isso é uma EmbedCreatorMainView
        self.bot = bot
        self.db = bot.db_connection # Armazena a instância do gerenciador de DB
        self.message = None # Para armazenar a mensagem do painel de gerenciamento de campos

    async def on_timeout(self):
        if self.message:
            for item in self.children:
                item.disabled = True
            await self.message.edit(content="Sessão de gerenciamento de campos expirada.", view=self)
            # Re-habilitar botões na view principal se necessário
            # await self.parent_view.message.edit(view=self.parent_view)

    async def _update_field_display(self, interaction: discord.Interaction):
        """Atualiza a mensagem que exibe os campos atuais."""
        embed = discord.Embed(title="Gerenciamento de Campos", description="Use os botões para adicionar ou remover campos.")
        
        fields_data = self.parent_view.current_embed_data.get('fields', [])
        if not fields_data:
            embed.add_field(name="Status", value="Nenhum campo adicionado ainda.", inline=False)
        else:
            for i, field in enumerate(fields_data):
                inline_status = "Inline" if field.get('inline', False) else "Bloco"
                embed.add_field(name=f"Campo {i+1}: {field.get('name', 'Sem Nome')}", 
                                 value=f"Valor: {field.get('value', 'Sem Valor')}\nTipo: {inline_status}", 
                                 inline=False)
        
        if self.message:
            await self.message.edit(embed=embed, view=self)
        else:
            if interaction.response.is_done():
                self.message = await interaction.followup.send(embed=embed, view=self, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, view=self, ephemeral=True)
                self.message = await interaction.original_response()

    @ui.button(label="Adicionar Campo", style=discord.ButtonStyle.success)
    async def add_field_button(self, interaction: discord.Interaction, button: ui.Button):
        class AddFieldModal(ui.Modal, title="Adicionar Novo Campo"):
            def __init__(self, parent_view: ui.View):
                super().__init__()
                self.parent_view = parent_view # Isso é uma FieldManagementView
                self.add_item(ui.TextInput(label="Nome do Campo", placeholder="Ex: Título do Campo", style=discord.TextStyle.short, custom_id="field_name"))
                self.add_item(ui.TextInput(label="Valor do Campo", placeholder="Ex: Conteúdo do campo", style=discord.TextStyle.paragraph, custom_id="field_value"))
                self.add_item(ui.TextInput(label="Inline? (sim/não)", placeholder="Digite 'sim' ou 'não'", style=discord.TextStyle.short, custom_id="field_inline", required=False))

            async def on_submit(self, interaction: discord.Interaction):
                await interaction.response.defer() # Deferir a interação do modal
                original_view = self.parent_view # Isso é a FieldManagementView
                
                name = self.children[0].value
                value = self.children[1].value
                inline_str = self.children[2].value.lower().strip()
                inline = inline_str == 'sim'

                if not name or not value:
                    await interaction.followup.send("Nome e Valor do campo são obrigatórios.", ephemeral=True)
                    return

                if 'fields' not in original_view.parent_view.current_embed_data:
                    original_view.parent_view.current_embed_data['fields'] = []
                
                original_view.parent_view.current_embed_data['fields'].append({
                    'name': name,
                    'value': value,
                    'inline': inline
                })
                
                await original_view._update_field_display(interaction) # Atualiza o painel de campos
                await original_view.parent_view.update_panel(interaction) # Atualiza o painel principal do embed
                await interaction.followup.send("Campo adicionado com sucesso!", ephemeral=True)
        
        add_field_modal = AddFieldModal(parent_view=self)
        await interaction.response.send_modal(add_field_modal)

    @ui.button(label="Remover Campo", style=discord.ButtonStyle.danger)
    async def remove_field_button(self, interaction: discord.Interaction, button: ui.Button):
        fields_data = self.parent_view.current_embed_data.get('fields', [])
        if not fields_data:
            await interaction.response.send_message("Não há campos para remover.", ephemeral=True)
            return

        options = []
        for i, field in enumerate(fields_data):
            # Limita o nome do campo para a opção do select para 100 caracteres
            field_name_display = field.get('name', 'Campo Sem Nome')
            if len(field_name_display) > 90: # Deixa espaço para "(...)"
                field_name_display = field_name_display[:87] + "..."
            options.append(discord.SelectOption(label=f"{i+1}. {field_name_display}", value=str(i)))

        class RemoveFieldSelect(ui.Select):
            def __init__(self, select_options):
                super().__init__(placeholder="Selecione o campo para remover...", min_values=1, max_values=1, options=select_options, custom_id="remove_field_select")
            
            async def callback(self, interaction: discord.Interaction):
                await interaction.response.defer()
                original_view = self.view.parent_view # A view do select é a FieldManagementView
                
                index_to_remove = int(self.values[0])
                if 0 <= index_to_remove < len(original_view.parent_view.current_embed_data['fields']):
                    removed_field = original_view.parent_view.current_embed_data['fields'].pop(index_to_remove)
                    await original_view._update_field_display(interaction)
                    await original_view.parent_view.update_panel(interaction)
                    await interaction.followup.send(f"Campo '{removed_field.get('name', 'Sem Nome')}' removido com sucesso!", ephemeral=True)
                else:
                    await interaction.followup.send("Índice de campo inválido.", ephemeral=True)

        class RemoveFieldView(ui.View):
            def __init__(self, select_options):
                super().__init__(timeout=60)
                self.add_item(RemoveFieldSelect(select_options))

        await interaction.response.send_message("Qual campo você gostaria de remover?", view=RemoveFieldView(options), ephemeral=True)

    @ui.button(label="Voltar", style=discord.ButtonStyle.secondary, row=4)
    async def back_button(self, interaction: discord.Interaction, button: ui.Button):
        # CORREÇÃO: Deferir a interação primeiro para evitar "interação falhou"
        await interaction.response.defer() 
        
        # Desabilita esta view (FieldManagementView)
        for item in self.children:
            item.disabled = True
        await self.message.edit(view=self)

        # Reabilita os botões da view principal (EmbedCreatorMainView)
        # Isso é importante para garantir que a view principal esteja interativa novamente
        for item in self.parent_view.children:
            item.disabled = False
        # Edita a mensagem principal com a view principal reabilitada
        # Isso também garante que a view principal seja re-renderizada com os botões habilitados
        await self.parent_view.message.edit(view=self.parent_view)
        
        # Envia uma mensagem de acompanhamento para o usuário
        await interaction.followup.send("Retornando ao criador de embeds principal.", ephemeral=True)


# View para o painel principal do EmbedCreator
class EmbedCreatorMainView(ui.View):
    def __init__(self, bot: commands.Bot, current_embed_data: dict = None, loaded_embed_name: str = None): # db_manager removido daqui
        super().__init__(timeout=300) # Timeout de 5 minutos
        self.bot = bot
        self.db = bot.db_connection # Armazena a instância do gerenciador de DB
        
        # Inicializa com valores padrão garantidos como strings vazias ou None para cor
        self.current_embed_data = {
            'title': '',
            'description': '',
            'color': None, 
            'fields': [],
            'author_name': None,
            'author_icon_url': None,
            'image_url': None,
            'footer_text': None,
            'footer_icon_url': None,
        }
        
        # Se houver dados existentes, atualiza, garantindo que title/description sejam strings
        if current_embed_data:
            self.current_embed_data['title'] = str(current_embed_data.get('title', ''))
            self.current_embed_data['description'] = str(current_embed_data.get('description', ''))
            self.current_embed_data['color'] = current_embed_data.get('color', None)
            self.current_embed_data['fields'] = current_embed_data.get('fields', [])
            self.current_embed_data['author_name'] = current_embed_data.get('author_name', None)
            self.current_embed_data['author_icon_url'] = current_embed_data.get('author_icon_url', None)
            self.current_embed_data['image_url'] = current_embed_data.get('image_url', None)
            self.current_embed_data['footer_text'] = current_embed_data.get('footer_text', None)
            self.current_embed_data['footer_icon_url'] = current_embed_data.get('footer_icon_url', None)
        
        self.message = None # Para armazenar a mensagem do painel
        self.loaded_embed_name = loaded_embed_name # Novo: Armazena o nome do embed carregado

    async def on_timeout(self):
        if self.message:
            for item in self.children:
                item.disabled = True
            await self.message.edit(content="Sessão do criador de embeds expirada.", view=self)

    async def update_panel(self, interaction: discord.Interaction):
        """Atualiza a mensagem do painel com o embed atual."""
        embed = discord.Embed(title="Criador de Embeds", description="Use os botões abaixo para configurar seu embed.")
        embed.add_field(name="Título", value=self.current_embed_data.get('title', 'Nenhum') or "Nenhum", inline=False)
        embed.add_field(name="Descrição", value=self.current_embed_data.get('description', 'Nenhuma') or "Nenhuma", inline=False)
        embed.add_field(name="Cor", value=self.current_embed_data.get('color', 'Nenhuma') or "Nenhuma", inline=False)
        embed.add_field(name="Autor", value=self.current_embed_data.get('author_name', 'Nenhum') or "Nenhum", inline=False)
        embed.add_field(name="Imagem", value="Configurada" if self.current_embed_data.get('image_url') else "Nenhuma", inline=True)
        embed.add_field(name="Rodapé", value="Configurado" if self.current_embed_data.get('footer_text') else "Nenhum", inline=True)
        embed.add_field(name="Campos", value=f"{len(self.current_embed_data.get('fields', []))} campos", inline=False)
        # Adicione mais campos conforme você permitir mais configurações (autor, thumbnail, imagem, footer, etc.)

        # Adiciona uma pré-visualização do embed
        preview_embed = self._create_preview_embed()
        
        # Lógica para enviar ou editar a mensagem do painel
        if self.message:
            await self.message.edit(embeds=[embed, preview_embed], view=self)
        else:
            if interaction.response.is_done():
                self.message = await interaction.followup.send(embeds=[embed, preview_embed], view=self, ephemeral=True)
            else:
                await interaction.response.send_message(embeds=[embed, preview_embed], view=self, ephemeral=True)
                self.message = await interaction.original_response()
            
    def _create_preview_embed(self):
        """Cria um discord.Embed a partir dos dados atuais para pré-visualização."""
        data = self.current_embed_data
        embed = discord.Embed()
        
        # Garante que title e description sejam strings válidas.
        embed.title = str(data.get('title', ''))
        embed.description = str(data.get('description', ''))

        # Se a descrição ainda estiver vazia, adicione um texto padrão para satisfazer o Discord API
        if not embed.description.strip(): 
            embed.description = "Pré-visualização do Embed (Clique nos botões para editar)"

        if 'color' in data and data['color'] is not None: 
            try:
                if isinstance(data['color'], str):
                    color_str = data['color'].strip()
                    if color_str.startswith('#'):
                        embed.color = discord.Color(int(color_str[1:], 16))
                    elif color_str.startswith('0x'):
                        embed.color = discord.Color(int(color_str, 16))
                    else:
                        embed.color = discord.Color(int(color_str))
                elif isinstance(data['color'], int):
                    embed.color = discord.Color(data['color'])
                else:
                    raise ValueError("Tipo de cor inválido.")
            except (ValueError, TypeError):
                logging.warning(f"Cor inválida fornecida: {data.get('color')}. Usando cor padrão.")
                embed.color = discord.Color.default()
        else:
            embed.color = discord.Color.default() 

        # Configurar Autor
        author_name = data.get('author_name')
        author_icon_url = data.get('author_icon_url')
        if author_name:
            embed.set_author(name=author_name, icon_url=author_icon_url)

        # Configurar Imagem
        image_url = data.get('image_url')
        if image_url:
            embed.set_image(url=image_url)

        # Configurar Rodapé
        footer_text = data.get('footer_text')
        footer_icon_url = data.get('footer_icon_url')
        if footer_text:
            embed.set_footer(text=footer_text, icon_url=footer_icon_url)


        if 'fields' in data:
            for field in data['fields']:
                field_name = str(field.get('name', ''))
                field_value = str(field.get('value', ''))
                embed.add_field(name=field_name, value=field_value, inline=field.get('inline', False))
        return embed

    @ui.button(label="Definir Título", style=discord.ButtonStyle.primary)
    async def set_title_button(self, interaction: discord.Interaction, button: ui.Button):
        class TitleModal(ui.Modal, title="Definir Título do Embed"):
            def __init__(self, parent_view: ui.View):
                super().__init__()
                self.parent_view = parent_view
                current_title = self.parent_view.current_embed_data.get('title', '')
                self.add_item(ui.TextInput(label="Título", placeholder="Digite o novo título...", style=discord.TextStyle.short, custom_id="new_title", default=current_title))

            async def on_submit(self, interaction: discord.Interaction):
                await interaction.response.defer() # Deferir a interação do modal
                original_view = self.parent_view
                original_view.current_embed_data['title'] = self.children[0].value
                await original_view.update_panel(interaction)
        
        title_modal = TitleModal(parent_view=self)
        await interaction.response.send_modal(title_modal)

    @ui.button(label="Definir Descrição", style=discord.ButtonStyle.primary)
    async def set_description_button(self, interaction: discord.Interaction, button: ui.Button):
        class DescriptionModal(ui.Modal, title="Definir Descrição do Embed"):
            def __init__(self, parent_view: ui.View):
                super().__init__()
                self.parent_view = parent_view
                current_description = self.parent_view.current_embed_data.get('description', '')
                self.add_item(ui.TextInput(label="Descrição", placeholder="Digite a nova descrição...", style=discord.TextStyle.paragraph, custom_id="new_description", default=current_description))

            async def on_submit(self, interaction: discord.Interaction):
                await interaction.response.defer() # Deferir a interação do modal
                original_view = self.parent_view
                original_view.current_embed_data['description'] = self.children[0].value
                await original_view.update_panel(interaction)
        
        description_modal = DescriptionModal(parent_view=self)
        await interaction.response.send_modal(description_modal)

    @ui.button(label="Definir Cor", style=discord.ButtonStyle.primary)
    async def set_color_button(self, interaction: discord.Interaction, button: ui.Button):
        class ColorModal(ui.Modal, title="Definir Cor do Embed"):
            def __init__(self, parent_view: ui.View):
                super().__init__()
                self.parent_view = parent_view
                current_color = self.parent_view.current_embed_data.get('color', '')
                self.add_item(ui.TextInput(label="Cor (Hex ou Decimal)", placeholder="#RRGGBB ou 0xRRGGBB ou número", style=discord.TextStyle.short, required=False, custom_id="new_color", default=current_color))

            async def on_submit(self, interaction: discord.Interaction):
                await interaction.response.defer() # Deferir a interação do modal
                color_value = self.children[0].value.strip()
                original_view = self.parent_view
                if not color_value:
                    original_view.current_embed_data['color'] = None # Define como None se o usuário limpar
                else:
                    original_view.current_embed_data['color'] = color_value
                await original_view.update_panel(interaction)
        
        color_modal = ColorModal(parent_view=self)
        await interaction.response.send_modal(color_modal)

    @ui.button(label="Definir Autor", style=discord.ButtonStyle.secondary, row=2)
    async def set_author_button(self, interaction: discord.Interaction, button: ui.Button):
        class AuthorModal(ui.Modal, title="Definir Autor do Embed"):
            def __init__(self, parent_view: ui.View):
                super().__init__()
                self.parent_view = parent_view
                current_author_name = self.parent_view.current_embed_data.get('author_name', '')
                current_author_icon = self.parent_view.current_embed_data.get('author_icon_url', '')

                self.add_item(ui.TextInput(label="Nome do Autor", placeholder="Nome do autor", style=discord.TextStyle.short, custom_id="author_name", default=current_author_name, required=False))
                self.add_item(ui.TextInput(label="URL do Ícone do Autor (Opcional)", placeholder="URL da imagem do ícone", style=discord.TextStyle.short, custom_id="author_icon_url", default=current_author_icon, required=False))

            async def on_submit(self, interaction: discord.Interaction):
                await interaction.response.defer() # Deferir a interação do modal
                original_view = self.parent_view
                original_view.current_embed_data['author_name'] = self.children[0].value if self.children[0].value.strip() else None
                original_view.current_embed_data['author_icon_url'] = self.children[1].value if self.children[1].value.strip() else None
                await original_view.update_panel(interaction)
        
        author_modal = AuthorModal(parent_view=self)
        await interaction.response.send_modal(author_modal)

    @ui.button(label="Definir Imagem", style=discord.ButtonStyle.secondary, row=2)
    async def set_image_button(self, interaction: discord.Interaction, button: ui.Button):
        class ImageModal(ui.Modal, title="Definir Imagem do Embed"):
            def __init__(self, parent_view: ui.View):
                super().__init__()
                self.parent_view = parent_view
                current_image_url = self.parent_view.current_embed_data.get('image_url', '')
                self.add_item(ui.TextInput(label="URL da Imagem", placeholder="URL da imagem (Ex: https://example.com/image.png)", style=discord.TextStyle.short, custom_id="image_url", default=current_image_url, required=False))

            async def on_submit(self, interaction: discord.Interaction):
                await interaction.response.defer() # Deferir a interação do modal
                original_view = self.parent_view
                original_view.current_embed_data['image_url'] = self.children[0].value if self.children[0].value.strip() else None
                await original_view.update_panel(interaction)
        
        image_modal = ImageModal(parent_view=self)
        await interaction.response.send_modal(image_modal)

    @ui.button(label="Definir Rodapé", style=discord.ButtonStyle.secondary, row=2)
    async def set_footer_button(self, interaction: discord.Interaction, button: ui.Button):
        class FooterModal(ui.Modal, title="Definir Rodapé do Embed"):
            def __init__(self, parent_view: ui.View):
                super().__init__()
                self.parent_view = parent_view
                current_footer_text = self.parent_view.current_embed_data.get('footer_text', '')
                current_footer_icon = self.parent_view.current_embed_data.get('footer_icon_url', '')

                self.add_item(ui.TextInput(label="Texto do Rodapé", placeholder="Texto do rodapé", style=discord.TextStyle.short, custom_id="footer_text", default=current_footer_text, required=False))
                self.add_item(ui.TextInput(label="URL do Ícone do Rodapé (Opcional)", placeholder="URL da imagem do ícone", style=discord.TextStyle.short, custom_id="footer_icon_url", default=current_footer_icon, required=False))

            async def on_submit(self, interaction: discord.Interaction):
                await interaction.response.defer() # Deferir a interação do modal
                original_view = self.parent_view
                original_view.current_embed_data['footer_text'] = self.children[0].value if self.children[0].value.strip() else None
                original_view.current_embed_data['footer_icon_url'] = self.children[1].value if self.children[1].value.strip() else None
                await original_view.update_panel(interaction)
        
        footer_modal = FooterModal(parent_view=self)
        await interaction.response.send_modal(footer_modal)


    @ui.button(label="Gerenciar Campos", style=discord.ButtonStyle.primary, row=3)
    async def manage_fields_button(self, interaction: discord.Interaction, button: ui.Button):
        # Desabilita a view principal temporariamente
        for item in self.children:
            item.disabled = True
        await self.message.edit(view=self)

        # Abre a nova view de gerenciamento de campos
        field_view = FieldManagementView(parent_view=self, bot=self.bot) # Passa self.bot
        await interaction.response.defer(ephemeral=True) 
        await field_view._update_field_display(interaction) # Envia a mensagem inicial do painel de campos

    @ui.button(label="Salvar Embed", style=discord.ButtonStyle.success, row=4)
    async def save_embed_button(self, interaction: discord.Interaction, button: ui.Button):
        class SaveModal(ui.Modal, title="Salvar Embed"):
            def __init__(self, parent_view: ui.View): # db_manager removido daqui
                super().__init__()
                self.parent_view = parent_view # Isso é uma EmbedCreatorMainView
                self.db = parent_view.db # Armazena a instância do gerenciador de DB
                # Pré-preenche o nome do embed se um foi carregado
                default_name = self.parent_view.loaded_embed_name if self.parent_view.loaded_embed_name else ""
                self.add_item(ui.TextInput(label="Nome para Salvar", placeholder="Nome único para este embed", style=discord.TextStyle.short, custom_id="embed_name", default=default_name))

            async def on_submit(self, interaction: discord.Interaction):
                await interaction.response.defer() # Deferir a interação do modal
                name = self.children[0].value
                guild_id = interaction.guild_id
                original_view = self.parent_view
                embed_json = json.dumps(original_view.current_embed_data)

                # Usar INSERT OR REPLACE INTO para permitir edição de embeds existentes
                success = False
                try:
                    success = await self.db.execute_query( # Usando self.db
                        "INSERT OR REPLACE INTO saved_embeds (guild_id, embed_name, embed_json) VALUES (?, ?, ?)",
                        (guild_id, name, embed_json)
                    )
                except Exception as e:
                    logging.error(f"Erro ao salvar embed no DB para guild {guild_id}: {e}", exc_info=True)

                if success:
                    await interaction.followup.send(f"Embed '{name}' salvo (ou atualizado) com sucesso!", ephemeral=True)
                else:
                    await interaction.followup.send("Erro ao salvar o embed no banco de dados.", ephemeral=True)
        
        save_modal = SaveModal(parent_view=self) # db_manager removido daqui
        await interaction.response.send_modal(save_modal)

    @ui.button(label="Enviar Embed", style=discord.ButtonStyle.success, row=4)
    async def send_embed_button(self, interaction: discord.Interaction, button: ui.Button):
        embed_to_send = self._create_preview_embed()
        
        class ChannelSelect(ui.Select):
            def __init__(self, guild_channels):
                options = [
                    discord.SelectOption(label=channel.name, value=str(channel.id))
                    for channel in guild_channels
                ]
                if not options:
                    options.append(discord.SelectOption(label="Nenhum canal de texto encontrado", value="none", default=True))

                super().__init__(placeholder="Selecione um canal...", min_values=1, max_values=1, options=options, custom_id="send_embed_channel_select")

            async def callback(self, interaction: discord.Interaction):
                await interaction.response.defer(ephemeral=True) # Deferir a interação do select
                if self.values[0] == "none":
                    await interaction.followup.send("Não há canais de texto válidos para enviar o embed.", ephemeral=True)
                    return

                channel_id = int(self.values[0])
                target_channel = interaction.guild.get_channel(channel_id)
                if not target_channel:
                    await interaction.followup.send("Canal não encontrado ou não tenho permissão para vê-lo.", ephemeral=True)
                    return
                
                try:
                    await target_channel.send(embed=embed_to_send)
                    await interaction.followup.send(f"Embed enviado para {target_channel.mention}!", ephemeral=True)
                except discord.Forbidden:
                    await interaction.followup.send(f"Não tenho permissão para enviar mensagens em {target_channel.mention}.", ephemeral=True)
                except Exception as e:
                    await interaction.followup.send(f"Erro ao enviar o embed: {e}", ephemeral=True)
                
        class SendEmbedView(ui.View):
            def __init__(self, guild_channels):
                super().__init__(timeout=60)
                self.add_item(ChannelSelect(guild_channels))
        
        await interaction.response.send_message("Para onde você gostaria de enviar este embed?", view=SendEmbedView(interaction.guild.text_channels), ephemeral=True)


class EmbedCreatorCog(commands.Cog):
    def __init__(self, bot: commands.Bot): # db_manager removido daqui
        self.bot = bot
        self.db = bot.db_connection # Armazena a instância do gerenciador de DB
        logging.info("Cog 'EmbedCreatorCog' inicializado.")

    @app_commands.command(name="embed_creator", description="Inicia o criador de embeds interativo.")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def embed_creator(self, interaction: discord.Interaction):
        view = EmbedCreatorMainView(self.bot) # Passa self.bot
        await interaction.response.defer(ephemeral=True)
        await view.update_panel(interaction)

    @app_commands.command(name="embed_load", description="Carrega um embed salvo para edição.")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.describe(name="O nome do embed que você quer carregar.")
    async def embed_load(self, interaction: discord.Interaction, name: str):
        guild_id = interaction.guild_id
        result = None
        try:
            result = await self.db.fetch_one( # Usando self.db
                "SELECT embed_json FROM saved_embeds WHERE guild_id = ? AND embed_name = ?",
                (guild_id, name)
            )
        except Exception as e:
            logging.error(f"Erro ao carregar embed do DB para guild {guild_id}, nome {name}: {e}", exc_info=True)
            await interaction.response.send_message("Ocorreu um erro ao carregar o embed.", ephemeral=True)
            return

        if result:
            embed_data = json.loads(result[0])
            # Passa o nome do embed carregado para a view
            view = EmbedCreatorMainView(self.bot, current_embed_data=embed_data, loaded_embed_name=name) # Passa self.bot
            await interaction.response.defer(ephemeral=True)
            await view.update_panel(interaction)
        else:
            await interaction.response.send_message(f"Embed '{name}' não encontrado.", ephemeral=True)

    @app_commands.command(name="embed_list", description="Lista todos os embeds salvos no servidor.")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def embed_list(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id
        results = []
        try:
            results = await self.db.fetch_all( # Usando self.db
                "SELECT embed_name FROM saved_embeds WHERE guild_id = ?",
                (guild_id,)
            )
        except Exception as e:
            logging.error(f"Erro ao listar embeds do DB para guild {guild_id}: {e}", exc_info=True)
            await interaction.response.send_message("Ocorreu um erro ao listar os embeds.", ephemeral=True)
            return

        if results:
            embed_names = [r[0] for r in results]
            embed = discord.Embed(
                title="Embeds Salvos",
                description="Aqui estão todos os embeds salvos neste servidor:\n" + "\n".join(embed_names),
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("Nenhum embed salvo neste servidor.", ephemeral=True)

    @app_commands.command(name="embed_delete", description="Deleta um embed salvo.")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.describe(name="O nome do embed que você quer deletar.")
    async def embed_delete(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id

        # Verifica se o embed existe antes de tentar deletar
        exists = await self.db.fetch_one(
            "SELECT 1 FROM saved_embeds WHERE guild_id = ? AND embed_name = ?",
            (guild_id, name)
        )

        if not exists:
            await interaction.followup.send(f"Embed '{name}' não encontrado para deletar.", ephemeral=True)
            return

        try:
            success = await self.db.execute_query(
                "DELETE FROM saved_embeds WHERE guild_id = ? AND embed_name = ?",
                (guild_id, name)
            )
            if success:
                await interaction.followup.send(f"Embed '{name}' deletado com sucesso!", ephemeral=True)
                logging.info(f"Embed '{name}' deletado por {interaction.user.name} ({interaction.user.id}) na guild {guild_id}.")
            else:
                await interaction.followup.send("Erro ao deletar o embed do banco de dados.", ephemeral=True)
        except Exception as e:
            logging.error(f"Erro ao deletar embed '{name}' do DB para guild {guild_id}: {e}", exc_info=True)
            await interaction.followup.send(f"Ocorreu um erro ao deletar o embed: {e}", ephemeral=True)


async def setup(bot: commands.Bot):
    """
    Função de setup para adicionar o cog ao bot.
    """
    await bot.add_cog(EmbedCreatorCog(bot))
    logging.info("EmbedCreatorCog cog adicionado ao bot.")
