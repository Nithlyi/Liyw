import discord
from discord.ext import commands
from discord import app_commands, ui
import datetime
import asyncio
import logging

# Configuração de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Timeout para propostas de casamento (em segundos)
PROPOSAL_TIMEOUT_SECONDS = 120 # 2 minutos

class ProposeView(ui.View):
    def __init__(self, bot: commands.Bot, proposer: discord.Member, proposee: discord.Member): # db_manager removido daqui
        super().__init__(timeout=PROPOSAL_TIMEOUT_SECONDS)
        self.bot = bot
        self.proposer = proposer
        self.proposee = proposee
        self.db = bot.db_connection # Armazena a instância do gerenciador de DB
        self.proposal_message = None # Para armazenar a mensagem da proposta
        self.accepted = False

    async def on_timeout(self):
        if self.proposal_message and not self.accepted:
            for item in self.children:
                item.disabled = True
            await self.proposal_message.edit(content=f"A proposta de casamento de {self.proposer.mention} para {self.proposee.mention} expirou.", view=self)
            # Remove a proposta pendente do cog
            cog = self.bot.get_cog("MarriageSystem")
            if cog:
                cog.remove_pending_proposal(self.proposer.id, self.proposee.id, self.proposer.guild.id)
        logging.info(f"Proposta de casamento entre {self.proposer.id} e {self.proposee.id} na guild {self.proposer.guild.id} expirou.")

    @ui.button(label="Aceitar", style=discord.ButtonStyle.success, custom_id="accept_proposal")
    async def accept_proposal(self, interaction: discord.Interaction, button: ui.Button):
        # Verifica se a interação é do proposto
        if interaction.user.id != self.proposee.id:
            await interaction.response.send_message("Esta proposta não é para você!", ephemeral=True)
            return

        # Verifica se algum dos usuários já se casou enquanto a proposta estava pendente
        marriage_info_proposer = None
        try:
            marriage_info_proposer = await self.db.fetch_one( # Usando self.db
                "SELECT partner1_id, partner2_id FROM marriages WHERE guild_id = ? AND (partner1_id = ? OR partner2_id = ?)",
                (interaction.guild.id, self.proposer.id, self.proposer.id)
            )
        except Exception as e:
            logging.error(f"Erro ao verificar casamento do proponente no DB: {e}", exc_info=True)
            await interaction.response.send_message("Ocorreu um erro ao verificar o status de casamento. Por favor, tente novamente.", ephemeral=True)
            return

        marriage_info_proposee = None
        try:
            marriage_info_proposee = await self.db.fetch_one( # Usando self.db
                "SELECT partner1_id, partner2_id FROM marriages WHERE guild_id = ? AND (partner1_id = ? OR partner2_id = ?)",
                (interaction.guild.id, self.proposee.id, self.proposee.id)
            )
        except Exception as e:
            logging.error(f"Erro ao verificar casamento do proposto no DB: {e}", exc_info=True)
            await interaction.response.send_message("Ocorreu um erro ao verificar o status de casamento. Por favor, tente novamente.", ephemeral=True)
            return

        if marriage_info_proposer:
            await interaction.response.send_message(f"{self.proposer.mention} já está casado(a)!", ephemeral=True)
            self.accepted = True # Marca como aceita para não disparar timeout
            self.stop()
            if self.proposal_message:
                for item in self.children:
                    item.disabled = True
                await self.proposal_message.edit(content=f"A proposta de casamento de {self.proposer.mention} para {self.proposee.mention} foi cancelada (proponente já casado).", view=self)
            return
        
        if marriage_info_proposee:
            await interaction.response.send_message(f"Você já está casado(a)!", ephemeral=True)
            self.accepted = True # Marca como aceita para não disparar timeout
            self.stop()
            if self.proposal_message:
                for item in self.children:
                    item.disabled = True
                await self.proposal_message.edit(content=f"A proposta de casamento de {self.proposer.mention} para {self.proposee.mention} foi cancelada (proposto já casado).", view=self)
            return

        # Registra o casamento no banco de dados
        # Garante que partner1_id seja sempre o menor para manter a unicidade
        p1_id = min(self.proposer.id, self.proposee.id)
        p2_id = max(self.proposer.id, self.proposee.id)

        success = False
        try:
            success = await self.db.execute_query( # Usando self.db
                "INSERT INTO marriages (guild_id, partner1_id, partner2_id) VALUES (?, ?, ?)",
                (interaction.guild.id, p1_id, p2_id)
            )
        except Exception as e:
            logging.error(f"Erro ao registrar casamento no DB para guild {interaction.guild.id}: {e}", exc_info=True)

        if success:
            self.accepted = True
            for item in self.children:
                item.disabled = True
            await interaction.response.edit_message(content=f"🎉 {self.proposee.mention} aceitou a proposta de casamento de {self.proposer.mention}! Eles estão oficialmente casados! �", view=self)
            logging.info(f"Casamento entre {self.proposer.id} e {self.proposee.id} na guild {interaction.guild.id} registrado.")
            # Remove a proposta pendente do cog
            cog = self.bot.get_cog("MarriageSystem")
            if cog:
                cog.remove_pending_proposal(self.proposer.id, self.proposee.id, self.proposer.guild.id)
            self.stop() # Para a view
        else:
            await interaction.response.send_message("Ocorreu um erro ao registrar o casamento. Por favor, tente novamente.", ephemeral=True)
            logging.error(f"Erro ao registrar casamento entre {self.proposer.id} e {self.proposee.id} na guild {interaction.guild.id}.")

    @ui.button(label="Recusar", style=discord.ButtonStyle.danger, custom_id="decline_proposal")
    async def decline_proposal(self, interaction: discord.Interaction, button: ui.Button):
        # Verifica se a interação é do proposto
        if interaction.user.id != self.proposee.id:
            await interaction.response.send_message("Esta proposta não é para você!", ephemeral=True)
            return

        self.accepted = False # Não foi aceita
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content=f"💔 {self.proposee.mention} recusou a proposta de casamento de {self.proposer.mention}.", view=self)
        logging.info(f"Proposta de casamento entre {self.proposer.id} e {self.proposee.id} na guild {self.proposer.guild.id} recusada.")
        # Remove a proposta pendente do cog
        cog = self.bot.get_cog("MarriageSystem")
        if cog:
            cog.remove_pending_proposal(self.proposer.id, self.proposee.id, self.proposer.guild.id)
        self.stop() # Para a view

class MarriageSystem(commands.Cog):
    def __init__(self, bot: commands.Bot): # db_manager removido daqui
        self.bot = bot
        self.db = bot.db_connection # Armazena a instância do gerenciador de DB
        # Dicionário para armazenar propostas pendentes
        # Key: (guild_id, proposer_id) -> Value: {'proposee_id': int, 'message_id': int, 'expiration_time': datetime.datetime}
        self.pending_proposals = {}

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info("Views persistentes de casamento garantidas.")
        # Opcional: Recarregar propostas pendentes do DB se o bot caiu e reiniciou
        # Isso exigiria que as propostas fossem salvas no DB, o que não está implementado aqui.
        # Por enquanto, self.pending_proposals será limpo a cada reinício do bot.

    def add_pending_proposal(self, guild_id: int, proposer_id: int, proposee_id: int, message_id: int):
        expiration_time = datetime.datetime.now() + datetime.timedelta(seconds=PROPOSAL_TIMEOUT_SECONDS)
        self.pending_proposals[(guild_id, proposer_id)] = {
            'proposee_id': proposee_id,
            'message_id': message_id,
            'expiration_time': expiration_time
        }
        logging.info(f"Proposta pendente adicionada: Proposer {proposer_id}, Proposee {proposee_id}, Guild {guild_id}")

    def remove_pending_proposal(self, proposer_id: int, proposee_id: int, guild_id: int):
        # Remove a proposta usando a chave do proponente
        if (guild_id, proposer_id) in self.pending_proposals:
            del self.pending_proposals[(guild_id, proposer_id)]
            logging.info(f"Proposta pendente removida: Proposer {proposer_id}, Proposee {proposee_id}, Guild {guild_id}")
        else:
            logging.warning(f"Tentativa de remover proposta não existente: Proposer {proposer_id}, Proposee {proposee_id}, Guild {guild_id}")


    def is_user_involved_in_pending_proposal(self, user_id: int, guild_id: int) -> bool:
        # Cria uma lista de chaves para iterar para evitar "dictionary changed size during iteration"
        keys_to_check = list(self.pending_proposals.keys())
        for (g_id, prop_id) in keys_to_check:
            if g_id == guild_id:
                proposal_data = self.pending_proposals.get((g_id, prop_id))
                if proposal_data: # Certifica-se de que a proposta ainda existe (não foi removida por outra chamada)
                    if prop_id == user_id or proposal_data['proposee_id'] == user_id:
                        # Verifica se a proposta não expirou ainda
                        if datetime.datetime.now() < proposal_data['expiration_time']:
                            return True
                        else:
                            # Se expirou, remove-a
                            del self.pending_proposals[(g_id, prop_id)]
                            logging.info(f"Proposta expirada removida durante verificação: Proposer {prop_id}, Proposee {proposal_data['proposee_id']}, Guild {g_id}")
        return False

    @app_commands.command(name="marry", description="Exibe seu status de casamento.")
    async def marry(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        user_id = interaction.user.id
        guild_id = interaction.guild.id

        marriage_info = None
        try:
            marriage_info = await self.db.fetch_one( # Usando self.db
                "SELECT partner1_id, partner2_id, married_at FROM marriages WHERE guild_id = ? AND (partner1_id = ? OR partner2_id = ?)",
                (guild_id, user_id, user_id)
            )
        except Exception as e:
            logging.error(f"Erro ao buscar status de casamento no DB para usuário {user_id}: {e}", exc_info=True)
            await interaction.followup.send("Ocorreu um erro ao buscar seu status de casamento.", ephemeral=True)
            return

        if marriage_info:
            p1_id, p2_id, married_at_str = marriage_info
            partner_id = p2_id if p1_id == user_id else p1_id
            partner = interaction.guild.get_member(partner_id)

            married_at = datetime.datetime.strptime(married_at_str, '%Y-%m-%d %H:%M:%S')
            timestamp_unix = int(married_at.timestamp())

            if partner:
                await interaction.followup.send(f"Você está casado(a) com {partner.mention} desde <t:{timestamp_unix}:F>!", ephemeral=True)
            else:
                await interaction.followup.send(f"Você está casado(a) com um usuário que não está mais no servidor (ID: {partner_id}) desde <t:{timestamp_unix}:F>.", ephemeral=True)
        else:
            await interaction.followup.send("Você não está casado(a).", ephemeral=True)

    @app_commands.command(name="propose", description="Pede alguém em casamento.")
    @app_commands.describe(user="O usuário que você deseja pedir em casamento.")
    async def propose(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.defer(ephemeral=True)

        proposer = interaction.user
        proposee = user
        guild_id = interaction.guild.id

        if proposer.id == proposee.id:
            await interaction.followup.send("Você não pode pedir a si mesmo(a) em casamento!", ephemeral=True)
            return

        if proposee.bot:
            await interaction.followup.send("Você não pode pedir um bot em casamento!", ephemeral=True)
            return

        # Verifica se o proponente já está casado
        proposer_married = None
        try:
            proposer_married = await self.db.fetch_one( # Usando self.db
                "SELECT 1 FROM marriages WHERE guild_id = ? AND (partner1_id = ? OR partner2_id = ?)",
                (guild_id, proposer.id, proposer.id)
            )
        except Exception as e:
            logging.error(f"Erro ao verificar casamento do proponente no DB: {e}", exc_info=True)
            await interaction.followup.send("Ocorreu um erro ao verificar seu status de casamento.", ephemeral=True)
            return

        if proposer_married:
            await interaction.followup.send("Você já está casado(a)!", ephemeral=True)
            return

        # Verifica se o proposto já está casado
        proposee_married = None
        try:
            proposee_married = await self.db.fetch_one( # Usando self.db
                "SELECT 1 FROM marriages WHERE guild_id = ? AND (partner1_id = ? OR partner2_id = ?)",
                (guild_id, proposee.id, proposee.id)
            )
        except Exception as e:
            logging.error(f"Erro ao verificar casamento do proposto no DB: {e}", exc_info=True)
            await interaction.followup.send("Ocorreu um erro ao verificar o status de casamento do proposto.", ephemeral=True)
            return

        if proposee_married:
            await interaction.followup.send(f"{proposee.mention} já está casado(a)!", ephemeral=True)
            return

        # Verifica se há propostas pendentes envolvendo qualquer um dos usuários
        if self.is_user_involved_in_pending_proposal(proposer.id, guild_id):
            await interaction.followup.send("Você já tem uma proposta de casamento pendente!", ephemeral=True)
            return
        if self.is_user_involved_in_pending_proposal(proposee.id, guild_id):
            await interaction.followup.send(f"{proposee.mention} já tem uma proposta de casamento pendente!", ephemeral=True)
            return

        # Envia a proposta
        view = ProposeView(self.bot, proposer, proposee) # db_manager removido daqui
        proposal_message = await interaction.channel.send(
            f"💍 {proposee.mention}, {proposer.mention} te pediu em casamento! Você aceita? "
            f"(Esta proposta expira em {PROPOSAL_TIMEOUT_SECONDS // 60} minutos)",
            view=view
        )
        view.proposal_message = proposal_message # Armazena a mensagem para edição posterior

        # Adiciona a proposta ao controle de propostas pendentes
        self.add_pending_proposal(guild_id, proposer.id, proposee.id, proposal_message.id)

        await interaction.followup.send(f"Sua proposta de casamento para {proposee.mention} foi enviada!", ephemeral=True)
        logging.info(f"Proposta de casamento enviada de {proposer.id} para {proposee.id} na guild {guild_id}.")

    @app_commands.command(name="divorce", description="Divorcia-se do seu parceiro(a).")
    async def divorce(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        user_id = interaction.user.id
        guild_id = interaction.guild.id

        # Busca o casamento do usuário
        marriage_info = None
        try:
            marriage_info = await self.db.fetch_one( # Usando self.db
                "SELECT partner1_id, partner2_id FROM marriages WHERE guild_id = ? AND (partner1_id = ? OR partner2_id = ?)",
                (guild_id, user_id, user_id)
            )
        except Exception as e:
            logging.error(f"Erro ao buscar casamento para divórcio no DB para usuário {user_id}: {e}", exc_info=True)
            await interaction.followup.send("Ocorreu um erro ao buscar seu status de casamento para divórcio.", ephemeral=True)
            return

        if not marriage_info:
            await interaction.followup.send("Você não está casado(a)!", ephemeral=True)
            return

        p1_id, p2_id = marriage_info
        partner_id = p2_id if p1_id == user_id else p1_id
        partner = interaction.guild.get_member(partner_id)

        # Deleta o registro de casamento
        success = False
        try:
            success = await self.db.execute_query( # Usando self.db
                "DELETE FROM marriages WHERE guild_id = ? AND (partner1_id = ? OR partner2_id = ?)",
                (guild_id, user_id, user_id)
            )
        except Exception as e:
            logging.error(f"Erro ao deletar casamento no DB para usuário {user_id}: {e}", exc_info=True)

        if success:
            if partner:
                await interaction.followup.send(f"Você se divorciou de {partner.mention}. Que a vida siga em frente!", ephemeral=False)
                # Envia uma mensagem para o ex-parceiro se ele estiver no servidor
                try:
                    await partner.send(f"💔 Olá! Apenas para avisar que {interaction.user.mention} iniciou um divórcio, e vocês não estão mais casados no servidor '{interaction.guild.name}'.")
                except discord.Forbidden:
                    logging.warning(f"Não foi possível enviar mensagem de divórcio para {partner.id}.")
            else:
                await interaction.followup.send("Você se divorciou. Seu ex-parceiro(a) não está mais no servidor.", ephemeral=False)
            logging.info(f"Usuário {user_id} se divorciou de {partner_id} na guild {guild_id}.")
        else:
            await interaction.followup.send("Ocorreu um erro ao processar o divórcio. Por favor, tente novamente.", ephemeral=True)
            logging.error(f"Erro ao deletar casamento para o usuário {user_id} na guild {guild_id}.")

    @app_commands.command(name="partners", description="Lista todos os casais do servidor.")
    async def partners(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        guild_id = interaction.guild.id
        marriages = []
        try:
            marriages = await self.db.fetch_all( # Usando self.db
                "SELECT partner1_id, partner2_id, married_at FROM marriages WHERE guild_id = ?",
                (guild_id,)
            )
        except Exception as e:
            logging.error(f"Erro ao buscar casais no DB para guild {guild_id}: {e}", exc_info=True)
            await interaction.followup.send("Ocorreu um erro ao buscar a lista de casais.", ephemeral=True)
            return

        if not marriages:
            await interaction.followup.send("Não há casais registrados neste servidor.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"Casais em {interaction.guild.name}",
            description="Aqui estão os casais registrados no servidor:",
            color=discord.Color.gold()
        )

        for p1_id, p2_id, married_at_str in marriages:
            partner1 = interaction.guild.get_member(p1_id)
            partner2 = interaction.guild.get_member(p2_id)

            p1_name = partner1.mention if partner1 else f"Usuário Desconhecido (ID: {p1_id})"
            p2_name = partner2.mention if partner2 else f"Usuário Desconhecido (ID: {p2_id})"
            
            married_at = datetime.datetime.strptime(married_at_str, '%Y-%m-%d %H:%M:%S')
            timestamp_unix = int(married_at.timestamp())

            embed.add_field(
                name=f"💖 {p1_name} e {p2_name}",
                value=f"Casados desde <t:{timestamp_unix}:D>",
                inline=False
            )
        
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot): # db_manager removido daqui
    """
    Função de setup para adicionar o cog ao bot.
    """
    await bot.add_cog(MarriageSystem(bot)) # Passe bot para a classe MarriageSystem
