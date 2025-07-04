import discord
from discord.ext import commands
from discord import app_commands
import random # Importar o módulo random para escolher GIFs
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class DiversionCommands(commands.Cog):
    def __init__(self, bot: commands.Bot): # db_manager removido daqui
        self.bot = bot
        self.db = bot.db_connection # Armazena a instância do gerenciador de DB, mesmo que não seja usado diretamente aqui
        logging.info("Cog 'DiversionCommands' inicializado.")

    @app_commands.command(name="hello", description="Diz olá!")
    async def hello(self, interaction: discord.Interaction):
        """
        Um comando de slash simples que faz o bot dizer olá para o usuário.
        """
        logging.info(f"Comando /hello executado por {interaction.user.display_name} ({interaction.user.id}) na guild {interaction.guild.name} ({interaction.guild.id}).")
        await interaction.response.send_message(f"Olá, {interaction.user.display_name}!", ephemeral=False)

    @app_commands.command(name="hug", description="Envie um abraço para outro membro!")
    @app_commands.describe(
        member="O membro que você deseja abraçar."
    )
    async def hug(self, interaction: discord.Interaction, member: discord.Member):
        """
        Envia um abraço para outro membro com um GIF aleatório.
        """
        await interaction.response.defer() # Deferir a interação publicamente

        # Lista de GIFs de abraço (você pode adicionar mais aqui!)
        hug_gifs = [
            "https://media.giphy.com/media/wnsgfr0AxS8X6/giphy.gif",
            "https://media.giphy.com/media/GfXFVyS0P1qms/giphy.com/media/GfXFVyS0P1qms/giphy.gif",
            "https://media.giphy.com/media/u9BxQbM5M0kQ/giphy.gif",
            "https://media.giphy.com/media/LrvnJpX2g40/giphy.gif",
            "https://media.giphy.com/media/qscdhWs5o3UFW/giphy.gif",
            "https://media.giphy.com/media/Vp3ftC4tE7mS0/giphy.gif",
            "https://media.giphy.com/media/ZBQhoPmIDK5Qo/giphy.gif",
            "https://media.giphy.com/media/sUIZWMnfd4qb6/giphy.gif",
            "https://media.giphy.com/media/EvYHULoN6Bd3O/giphy.gif",
            "https://media.giphy.com/media/l2QDM9JNxuKqBqzYs/giphy.gif",
            "https://media.discordapp.net/attachments/1385626050826076364/1385626612942245968/24bf9ea5632d759d4793dabbc51e89c6.gif?ex=68649898&is=68634718&hm=cb1100c8ccc590be8bc8f725f80c0ea5c8da557143c4048ec91b1778ea64b23e&=&width=400&height=186"
        ]
        
        chosen_gif = random.choice(hug_gifs)

        if member.id == interaction.user.id:
            response_message = f"{interaction.user.mention} se abraça! Que fofo! 🤗"
        else:
            response_message = f"{interaction.user.mention} abraçou {member.mention}! Que carinho! 🥰"

        embed = discord.Embed(
            description=response_message,
            color=discord.Color.pink()
        )
        embed.set_image(url=chosen_gif)
        embed.set_footer(text="Um abraço para você!")

        await interaction.followup.send(embed=embed)
        logging.info(f"Comando /hug usado por {interaction.user.id} para {member.id} na guild {interaction.guild.id}.")

    # Exemplo de comando de rolagem de dado (descomentado e pronto para uso):
    @app_commands.command(name="roll", description="Rola um dado (ex: 1d6, 2d10).")
    @app_commands.describe(dice="O formato do dado a rolar (ex: 1d6, 2d10)")
    async def roll(self, interaction: discord.Interaction, dice: str):
        """
        Rola um ou mais dados e exibe o resultado.
        """
        await interaction.response.defer()
        try:
            num_dice, num_sides = map(int, dice.lower().split('d'))
            if num_dice <= 0 or num_sides <= 0:
                await interaction.followup.send("Por favor, insira valores positivos para o número de dados e lados.", ephemeral=True)
                return
            if num_dice > 100 or num_sides > 1000: # Limites para evitar abuso
                await interaction.followup.send("Por favor, não role mais de 100 dados ou dados com mais de 1000 lados.", ephemeral=True)
                return

            rolls = [random.randint(1, num_sides) for _ in range(num_dice)]
            total = sum(rolls)
            await interaction.followup.send(f"Você rolou {dice}: {', '.join(map(str, rolls))} (Total: {total})", ephemeral=False)
        except ValueError:
            await interaction.followup.send("Formato inválido. Use, por exemplo: `1d6` ou `2d10`.", ephemeral=True)
        except Exception as e:
            logging.error(f"Erro ao rolar dado: {e}", exc_info=True)
            await interaction.followup.send("Ocorreu um erro ao rolar o dado.", ephemeral=True)


async def setup(bot: commands.Bot): # db_manager removido daqui
    """
    Função de setup para adicionar o cog ao bot.
    """
    await bot.add_cog(DiversionCommands(bot)) # Passe bot para a classe DiversionCommands
