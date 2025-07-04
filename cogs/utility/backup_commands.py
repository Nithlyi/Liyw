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

# --- Funções Auxiliares para Lógica de Backup/Restauração ---
async def _perform_backup_logic(interaction: discord.Interaction, guild: discord.Guild):
    """Lógica central para criar um backup da estrutura do servidor."""
    backup_data = {
        "guild_id": guild.id,
        "guild_name": guild.name,
        "roles": [],
        "categories": [],
        "text_channels": [],
        "voice_channels": [],
        "timestamp": datetime.datetime.now().isoformat()
    }

    # Backup de Cargos
    for role in guild.roles:
        # Ignora o cargo @everyone para evitar duplicação ou problemas na restauração,
        # pois ele é recriado automaticamente pelo Discord.
        if role == guild.default_role:
            continue
        backup_data["roles"].append({
            "name": role.name,
            "permissions": role.permissions.value, # Salva o valor inteiro das permissões
            "color": role.color.value, # Salva o valor inteiro da cor
            "hoist": role.hoist,
            "mentionable": role.mentionable,
            "position": role.position,
            "id": role.id # Inclui o ID original para mapeamento durante a restauração
        })
    # Ordena os cargos por posição para tentar recriar na ordem correta
    backup_data["roles"].sort(key=lambda x: x["position"], reverse=True)

    # Backup de Canais e Categorias
    for category in guild.categories:
        category_data = {
            "name": category.name,
            "id": category.id, # Inclui o ID original para mapeamento
            "position": category.position,
            "overwrites": []
        }
        for target, overwrite_perms in category.overwrites.items():
            target_id = target.id
            target_type = "role" if isinstance(target, discord.Role) else "member"
            try:
                # Verifica se 'allowed' e 'denied' existem e não são None antes de acessar '.value'
                allowed_value = overwrite_perms.allowed.value if hasattr(overwrite_perms, 'allowed') and overwrite_perms.allowed else 0
                denied_value = overwrite_perms.denied.value if hasattr(overwrite_perms, 'denied') and overwrite_perms.denied else 0
                
                category_data["overwrites"].append({
                    "id": target_id,
                    "type": target_type,
                    "allow": allowed_value,
                    "deny": denied_value
                })
            except AttributeError as e:
                logging.error(f"Erro ao obter permissões de sobrescrita para categoria '{category.name}' (Target ID: {target_id}, Tipo: {target_type}). Erro: {e}. Tipo de overwrite_perms: {type(overwrite_perms)}")
                # Se ocorrer um erro, esta sobrescrita será ignorada para evitar travar o backup.
                # Você pode adicionar lógica para lidar com isso, como definir permissões padrão.
        backup_data["categories"].append(category_data)

        for channel in category.channels:
            channel_data = {
                "name": channel.name,
                "position": channel.position,
                "topic": channel.topic if isinstance(channel, discord.TextChannel) else None,
                "bitrate": channel.bitrate if isinstance(channel, discord.VoiceChannel) else None,
                "user_limit": channel.user_limit if isinstance(channel, discord.VoiceChannel) else None,
                "nsfw": channel.nsfw if isinstance(channel, discord.TextChannel) else None,
                "slowmode_delay": channel.slowmode_delay if isinstance(channel, discord.TextChannel) else None,
                "overwrites": [],
                "id": channel.id, # Inclui o ID original
                "category_id": category.id, # Link para o ID original da categoria
                "type": "text_channel" if isinstance(channel, discord.TextChannel) else "voice_channel" # Adiciona o tipo de canal
            }
            for target, overwrite_perms in channel.overwrites.items():
                target_id = target.id
                target_type = "role" if isinstance(target, discord.Role) else "member"
                try:
                    # Verifica se 'allowed' e 'denied' existem e não são None antes de acessar '.value'
                    allowed_value = overwrite_perms.allowed.value if hasattr(overwrite_perms, 'allowed') and overwrite_perms.allowed else 0
                    denied_value = overwrite_perms.denied.value if hasattr(overwrite_perms, 'denied') and overwrite_perms.denied else 0

                    channel_data["overwrites"].append({
                        "id": target_id,
                        "type": target_type,
                        "allow": allowed_value,
                        "deny": denied_value
                    })
                except AttributeError as e:
                    logging.error(f"Erro ao obter permissões de sobrescrita para canal '{channel.name}' (Target ID: {target_id}, Tipo: {target_type}). Erro: {e}. Tipo de overwrite_perms: {type(overwrite_perms)}")
                    # Se ocorrer um erro, esta sobrescrita será ignorada.
            
            if isinstance(channel, discord.TextChannel):
                backup_data["text_channels"].append(channel_data)
            elif isinstance(channel, discord.VoiceChannel):
                backup_data["voice_channels"].append(channel_data)
    
    # Canais sem categoria (que não estão dentro de uma categoria)
    for channel in guild.channels:
        if channel.category is None and not isinstance(channel, discord.CategoryChannel):
            channel_data = {
                "name": channel.name,
                "position": channel.position,
                "topic": channel.topic if isinstance(channel, discord.TextChannel) else None,
                "bitrate": channel.bitrate if isinstance(channel, discord.VoiceChannel) else None,
                "user_limit": channel.user_limit if isinstance(channel, discord.VoiceChannel) else None,
                "nsfw": channel.nsfw if isinstance(channel, discord.TextChannel) else None,
                "slowmode_delay": channel.slowmode_delay if isinstance(channel, discord.TextChannel) else None,
                "overwrites": [],
                "id": channel.id, # Inclui o ID original
                "category_id": None, # Sem categoria
                "type": "text_channel" if isinstance(channel, discord.TextChannel) else "voice_channel" # Adiciona o tipo de canal
            }
            for target, overwrite_perms in channel.overwrites.items():
                target_id = target.id
                target_type = "role" if isinstance(target, discord.Role) else "member"
                try:
                    # Verifica se 'allowed' e 'denied' existem e não são None antes de acessar '.value'
                    allowed_value = overwrite_perms.allowed.value if hasattr(overwrite_perms, 'allowed') and overwrite_perms.allowed else 0
                    denied_value = overwrite_perms.denied.value if hasattr(overwrite_perms, 'denied') and overwrite_perms.denied else 0

                    channel_data["overwrites"].append({
                        "id": target_id,
                        "type": target_type,
                        "allow": allowed_value,
                        "deny": denied_value
                    })
                except AttributeError as e:
                    logging.error(f"Erro ao obter permissões de sobrescrita para canal sem categoria '{channel.name}' (Target ID: {target_id}, Tipo: {target_type}). Erro: {e}. Tipo de overwrite_perms: {type(overwrite_perms)}")
                    # Se ocorrer um erro, esta sobrescrita será ignorada.

            if isinstance(channel, discord.TextChannel):
                backup_data["text_channels"].append(channel_data)
            elif isinstance(channel, discord.VoiceChannel):
                backup_data["voice_channels"].append(channel_data)

    # Cria a pasta de backups se não existir
    backup_dir = "server_backups"
    os.makedirs(backup_dir, exist_ok=True)

    # Salva o backup em um arquivo JSON
    filename = f"{backup_dir}/{guild.id}_backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(backup_data, f, ensure_ascii=False, indent=4)
    
    logging.info(f"Backup da estrutura do servidor {guild.name} ({guild.id}) criado em {filename}")
    return filename

async def _perform_restore_logic(interaction: discord.Interaction, backup_data: dict):
    """Lógica central para restaurar a estrutura do servidor a partir de dados de backup."""
    guild = interaction.guild

    # Verifica se o backup pertence ao servidor atual
    if backup_data.get("guild_id") != guild.id:
        await interaction.followup.send("Este arquivo de backup não pertence a este servidor. Cancelando.", ephemeral=True)
        return

    await interaction.followup.send("Iniciando restauração da estrutura do servidor. Isso pode levar um tempo...", ephemeral=True)

    role_id_map = {} # Mapeia IDs de cargos antigos para novos IDs
    category_id_map = {} # Mapeia IDs de categorias antigas para novos IDs
    
    # Restauração de Cargos
    existing_roles_map = {role.name: role for role in guild.roles}

    for role_data in backup_data.get("roles", []):
        role_name = role_data["name"]
        
        # Se o cargo já existe, tenta atualizá-lo. Caso contrário, cria um novo.
        if role_name in existing_roles_map:
            new_role = existing_roles_map[role_name]
            try:
                await new_role.edit(
                    permissions=discord.Permissions(role_data["permissions"]),
                    color=discord.Color(role_data["color"]),
                    hoist=role_data["hoist"],
                    mentionable=role_data["mentionable"],
                    reason="Restauração de backup"
                )
                logging.info(f"Cargo existente '{role_name}' atualizado.")
            except Exception as e:
                logging.warning(f"Não foi possível atualizar o cargo existente '{role_name}': {e}")
            role_id_map[role_data.get("id")] = new_role.id
        else:
            try:
                new_role = await guild.create_role(
                    name=role_name,
                    permissions=discord.Permissions(role_data["permissions"]),
                    color=discord.Color(role_data["color"]),
                    hoist=role_data["hoist"],
                    mentionable=role_data["mentionable"],
                    reason="Restauração de backup"
                )
                logging.info(f"Cargo '{role_name}' criado.")
                role_id_map[role_data.get("id")] = new_role.id
            except Exception as e:
                logging.error(f"Não foi possível criar o cargo '{role_name}': {e}")
    
    # Ajustar posições dos cargos após a criação/atualização
    for role_data in backup_data.get("roles", []):
        if role_data["name"] == "@everyone":
            continue
        role_id = role_id_map.get(role_data.get("id"))
        if role_id:
            role = guild.get_role(role_id)
            if role and role.position != role_data["position"]:
                try:
                    await role.edit(position=role_data["position"], reason="Ajuste de posição pós-restauração")
                    logging.info(f"Posição do cargo '{role.name}' ajustada para {role_data['position']}.")
                except Exception as e:
                    logging.warning(f"Não foi possível ajustar a posição do cargo '{role.name}' para {role_data['position']}: {e}")

    # Restauração de Categorias
    for category_data in backup_data.get("categories", []):
        overwrites = {}
        for ow in category_data["overwrites"]:
            target = None
            if ow["type"] == "role":
                mapped_id = role_id_map.get(ow["id"])
                if mapped_id:
                    target = guild.get_role(mapped_id)
                else:
                    # Fallback: tenta encontrar o cargo pelo nome se o ID mapeado não foi encontrado
                    # Nota: O backup não salva o nome do cargo para overwrites, apenas o ID.
                    # Se o ID não for mapeado, e o cargo não existir, não podemos encontrá-lo pelo nome aqui.
                    # Isso é uma limitação se o cargo foi deletado e recriado com outro ID mas o mesmo nome.
                    pass 
            elif ow["type"] == "member":
                target = guild.get_member(ow["id"])
            
            if target:
                perm_allow = discord.Permissions(ow["allow"])
                perm_deny = discord.Permissions(ow["deny"])
                overwrites[target] = discord.PermissionOverwrite.from_pair(perm_allow, perm_deny)
            else:
                logging.warning(f"Alvo de overwrite não encontrado (ID: {ow['id']}, Tipo: {ow['type']}) para categoria '{category_data['name']}'. Ignorando overwrite.")

        try:
            new_category = await guild.create_category(
                name=category_data["name"],
                position=category_data["position"],
                overwrites=overwrites,
                reason="Restauração de backup"
            )
            logging.info(f"Categoria '{category_data['name']}' criada.")
            category_id_map[category_data.get("id")] = new_category.id
        except Exception as e:
            logging.error(f"Não foi possível criar a categoria '{category_data['name']}': {e}")
    
    # Restauração de Canais (Texto e Voz)
    # Combina canais de texto e voz para iterar sobre eles
    for channel_data in backup_data.get("text_channels", []) + backup_data.get("voice_channels", []):
        overwrites = {}
        for ow in channel_data["overwrites"]:
            target = None
            if ow["type"] == "role":
                mapped_id = role_id_map.get(ow["id"])
                if mapped_id:
                    target = guild.get_role(mapped_id)
                else:
                    # Fallback: tenta encontrar o cargo pelo nome se o ID mapeado não foi encontrado
                    pass
            elif ow["type"] == "member":
                target = guild.get_member(ow["id"])
            
            if target:
                perm_allow = discord.Permissions(ow["allow"])
                perm_deny = discord.Permissions(ow["deny"])
                overwrites[target] = discord.PermissionOverwrite.from_pair(perm_allow, perm_deny)
            else:
                logging.warning(f"Alvo de overwrite não encontrado (ID: {ow['id']}, Tipo: {ow['type']}) para canal '{channel_data['name']}'. Ignorando overwrite.")

        category = None
        if channel_data.get("category_id"):
            mapped_category_id = category_id_map.get(channel_data["category_id"])
            if mapped_category_id:
                category = guild.get_channel(mapped_category_id)
                if not isinstance(category, discord.CategoryChannel):
                    category = None # Garante que é uma categoria válida
            else:
                logging.warning(f"Categoria mapeada não encontrada para canal '{channel_data['name']}'. Criando sem categoria.")

        try:
            # Verifica o tipo de canal para criar corretamente
            if channel_data["type"] == "text_channel": 
                await guild.create_text_channel(
                    name=channel_data["name"],
                    position=channel_data["position"],
                    topic=channel_data.get("topic"),
                    nsfw=channel_data.get("nsfw", False),
                    slowmode_delay=channel_data.get("slowmode_delay"),
                    category=category,
                    overwrites=overwrites,
                    reason="Restauração de backup"
                )
                logging.info(f"Canal de texto '{channel_data['name']}' criado.")
            elif channel_data["type"] == "voice_channel": 
                await guild.create_voice_channel(
                    name=channel_data["name"],
                    position=channel_data["position"],
                    bitrate=channel_data.get("bitrate"),
                    user_limit=channel_data.get("user_limit"),
                    category=category,
                    overwrites=overwrites,
                    reason="Restauração de backup"
                )
                logging.info(f"Canal de voz '{channel_data['name']}' criado.")
            else:
                logging.warning(f"Tipo de canal desconhecido ou não suportado para restauração: {channel_data['type']}")
        except Exception as e:
            logging.error(f"Não foi possível criar o canal '{channel_data['name']}' ({channel_data['type']}): {e}")

    await interaction.followup.send("Restauração da estrutura do servidor concluída! Por favor, verifique manualmente.", ephemeral=True)
    logging.info(f"Estrutura do servidor '{guild.name}' (ID: {guild.id}) restaurada por {interaction.user.name}.")


# --- View para o Painel Principal de Backup/Restauração ---
class BackupMainView(ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=300) # Timeout de 5 minutos
        self.bot = bot
        self.db = bot.db_connection # Armazena a instância do gerenciador de DB
        self.message = None # Para armazenar a mensagem do painel

    async def on_timeout(self):
        if self.message:
            for item in self.children:
                item.disabled = True
            await self.message.edit(content="Sessão do painel de backup expirada.", view=self)

    async def _update_display(self, interaction: discord.Interaction):
        """Atualiza a exibição do painel principal."""
        embed = discord.Embed(
            title="Painel de Backup e Restauração",
            description="Use os botões abaixo para gerenciar a estrutura do seu servidor.",
            color=discord.Color.blue()
        )
        embed.add_field(name="Criar Backup", value="Salva a estrutura atual de cargos e canais em um arquivo JSON.", inline=False)
        embed.add_field(name="Carregar Backup", value="Restaura a estrutura a partir de um arquivo JSON de backup que você anexar.", inline=False)

        if self.message:
            try:
                await self.message.edit(embed=embed, view=self)
            except discord.errors.NotFound:
                logging.warning(f"Panel message {self.message.id} not found for editing in guild {interaction.guild.id}. Attempting to resend.")
                if interaction.response.is_done():
                    self.message = await interaction.followup.send(embed=embed, view=self, ephemeral=True)
                else:
                    await interaction.response.send_message(embed=embed, view=self, ephemeral=True)
                    self.message = await interaction.original_response()
            except Exception as e:
                logging.error(f"Error editing panel message {self.message.id}: {e}", exc_info=True)
        else:
            if interaction.response.is_done():
                self.message = await interaction.followup.send(embed=embed, view=self, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, view=self, ephemeral=True)
                self.message = await interaction.original_response()

    @ui.button(label="Criar Backup", style=discord.ButtonStyle.primary)
    async def create_backup_button(self, interaction: discord.Interaction, button: ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
        except discord.errors.NotFound:
            logging.warning(f"Interaction for create_backup_button was already responded to or invalid for user {interaction.user.id}. Skipping further response.")
            return

        try:
            filename = await _perform_backup_logic(interaction, interaction.guild)
            # Envia o arquivo de backup diretamente para o usuário na resposta de acompanhamento
            await interaction.followup.send(f"Backup criado com sucesso! Você pode baixar o arquivo aqui:", file=discord.File(filename), ephemeral=True)
            # Opcional: Remover o arquivo local após o envio
            os.remove(filename) 
            logging.info(f"Arquivo de backup local {filename} removido após envio.")
        except Exception as e:
            logging.error(f"Erro ao criar backup pelo botão: {e}", exc_info=True)
            await interaction.followup.send(f"Ocorreu um erro ao criar o backup: {e}", ephemeral=True)
        await self._update_display(interaction) # Atualiza a exibição do painel após a ação

    @ui.button(label="Carregar Backup", style=discord.ButtonStyle.danger)
    async def load_backup_button(self, interaction: discord.Interaction, button: ui.Button):
        # Verifica se o usuário é o proprietário do bot antes de permitir a restauração
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("Você não tem permissão para carregar backups.", ephemeral=True)
            return

        # Esta é a primeira resposta para esta interação de botão
        await interaction.response.send_message("Por favor, anexe o arquivo JSON de backup que você deseja carregar. Eu irei processá-lo.", ephemeral=True)
        
        # Define uma função de checagem para o wait_for
        def check(m: discord.Message):
            return m.author == interaction.user and \
                   m.channel == interaction.channel and \
                   m.attachments and \
                   m.attachments[0].filename.endswith(".json")

        try:
            # Espera por uma mensagem do usuário com um anexo JSON
            message = await self.bot.wait_for('message', check=check, timeout=120.0) # Espera por 120 segundos
            backup_file = message.attachments[0]
            
            await interaction.followup.send(f"Recebi o arquivo `{backup_file.filename}`. Iniciando restauração...", ephemeral=True)

            backup_content = await backup_file.read()
            backup_data = json.loads(backup_content.decode('utf-8'))

            await _perform_restore_logic(interaction, backup_data)

            # Deleta a mensagem do usuário com o arquivo de backup após o processamento
            try:
                await message.delete()
            except discord.Forbidden:
                logging.warning(f"Não tenho permissão para deletar a mensagem do usuário com o backup em {message.channel.name}.")
            except discord.NotFound:
                pass # Mensagem já deletada
            
        except asyncio.TimeoutError:
            await interaction.followup.send("Tempo esgotado. Nenhum arquivo de backup foi recebido.", ephemeral=True)
        except json.JSONDecodeError:
            await interaction.followup.send("O arquivo anexado não é um JSON válido. Por favor, tente novamente com um arquivo JSON correto.", ephemeral=True)
        except Exception as e:
            logging.error(f"Erro ao carregar backup pelo botão: {e}", exc_info=True)
            await interaction.followup.send(f"Ocorreu um erro ao carregar o backup: {e}", ephemeral=True)
        
        await self._update_display(interaction) # Atualiza a exibição do painel após a ação


# --- Cog Principal de Comandos de Backup ---
class BackupCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db_connection # Armazena a instância do gerenciador de DB
        logging.info("Cog 'BackupCommands' inicializado.")

    @app_commands.command(name="backup_panel", description="Abre o painel de backup e restauração do servidor.")
    @app_commands.checks.has_permissions(administrator=True)
    async def backup_panel(self, interaction: discord.Interaction):
        view = BackupMainView(self.bot)
        try:
            await interaction.response.defer(ephemeral=True)
        except discord.errors.NotFound:
            logging.warning(f"Interaction for /backup_panel command was already responded to or invalid for user {interaction.user.id}. Skipping further response.")
            return
        await view._update_display(interaction)

    @app_commands.command(name="backup", description="Cria um backup da estrutura de canais e cargos do servidor.")
    @app_commands.checks.has_permissions(administrator=True)
    async def backup_command(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
        except discord.errors.NotFound:
            # Isso significa que a interação já foi respondida ou é inválida.
            # Não podemos fazer mais nada com esta interação específica.
            logging.warning(f"Interaction for /backup command was already responded to or invalid for user {interaction.user.id}. Skipping further response.")
            return # Sai do manipulador de comando

        try:
            filename = await _perform_backup_logic(interaction, interaction.guild)
            # Envia o arquivo de backup diretamente para o usuário na resposta de acompanhamento
            await interaction.followup.send(f"Backup criado com sucesso! Você pode baixar o arquivo aqui:", file=discord.File(filename), ephemeral=True)
            # Opcional: Remover o arquivo local após o envio
            os.remove(filename) 
            logging.info(f"Arquivo de backup local {filename} removido após envio.")
        except Exception as e:
            logging.error(f"Erro ao criar backup pelo comando /backup: {e}", exc_info=True)
            # Garante que um follow-up seja sempre enviado, mesmo em caso de erro
            await interaction.followup.send(f"Ocorreu um erro ao criar o backup: {e}", ephemeral=True)

    @app_commands.command(name="restore", description="Restaura a estrutura do servidor a partir de um arquivo JSON (APENAS COM EXTREMA CAUTELA!).")
    @app_commands.check(commands.is_owner().predicate) # Mantém este comando restrito ao proprietário para segurança
    @app_commands.describe(file="Anexe o arquivo JSON de backup aqui.")
    async def restore_command(self, interaction: discord.Interaction, file: discord.Attachment):
        if not file.filename.endswith(".json"):
            await interaction.response.send_message("Por favor, anexe um arquivo JSON válido.", ephemeral=True)
            return
        
        try:
            await interaction.response.defer(ephemeral=True)
        except discord.errors.NotFound:
            logging.warning(f"Interaction for /restore command was already responded to or invalid for user {interaction.user.id}. Skipping further response.")
            return

        try:
            backup_content = await file.read()
            backup_data = json.loads(backup_content.decode('utf-8'))
            await _perform_restore_logic(interaction, backup_data)
        except json.JSONDecodeError:
            await interaction.followup.send("O arquivo JSON de backup é inválido.", ephemeral=True)
        except Exception as e:
            logging.error(f"Erro geral ao carregar backup pelo comando /restore: {e}", exc_info=True)
            await interaction.followup.send(f"Ocorreu um erro ao carregar o backup: {e}", ephemeral=True)


async def setup(bot: commands.Bot):
    """
    Função de setup para adicionar o cog ao bot.
    """
    await bot.add_cog(BackupCommands(bot))
