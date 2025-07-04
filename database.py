import asyncpg
import os
import logging
import datetime
import re  # Importado para a substituição de placeholders

# Configure logging for the database module
logger = logging.getLogger(__name__)

# PostgreSQL connection URL should be read from environment variables
# Example: postgres://user:password@host:port/database
DATABASE_URL = os.getenv('DATABASE_URL')

# Helper function to adapt SQLite '?' placeholders to PostgreSQL '$N'
def adapt_query_placeholders(query: str) -> str:
    """Adapts SQLite '?' placeholders to PostgreSQL '$N'."""
    # This regex finds '?' not inside quotes
    # It's a basic implementation and might fail with complex SQL
    parts = re.split(r"""('(?:[^']|'')*'|"(?:[^"\\]|\\.)*"|`)""", query)
    adapted_query = ""
    param_index = 1
    for i, part in enumerate(parts):
        if i % 2 == 0:  # Not inside quotes
            new_part = part.replace('?', f'${param_index}')
            # Need to correctly increment param_index for each '?' replaced in this part
            param_index += part.count('?')  # Count original ? in this part
            adapted_query += new_part
        else:  # Inside quotes or backticks, leave as is
            adapted_query += part
    return adapted_query


class DatabaseManager:
    """
    Manages the asynchronous PostgreSQL database connection and operations.
    Provides methods for executing queries, fetching single rows, and fetching all rows.
    """
    def __init__(self, dsn: str):
        self.dsn = dsn  # Data Source Name (connection string)
        self.conn = None

    async def connect(self):
        """Establishes the database connection."""
        if self.conn is None:
            try:
                self.conn = await asyncpg.connect(self.dsn)
                logger.info("Conexão com o banco de dados PostgreSQL estabelecida.")
            except Exception as e:
                logger.critical(f"Falha ao conectar ao banco de dados PostgreSQL: {e}", exc_info=True)
                raise  # Re-raise the exception

    async def close(self):
        """Closes the database connection."""
        if self.conn:
            await self.conn.close()
            self.conn = None
            logger.info("Conexão com o banco de dados PostgreSQL fechada.")

    async def execute_query(self, query: str, params: tuple = ()) -> bool:
        """
        Executes a database query (INSERT, UPDATE, DELETE).
        Returns True on success, False on error.
        """
        await self.connect()  # Ensure connection is open
        try:
            # Use the adapter for placeholders
            adapted_query = adapt_query_placeholders(query)
            await self.conn.execute(adapted_query, *params)  # asyncpg takes params unpacked
            return True
        except asyncpg.exceptions.PostgresError as e:
            logger.error(f"Erro ao executar query: {query} com params {params}. Erro: {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"Erro inesperado ao executar query: {query} com params {params}. Erro: {e}", exc_info=True)
            return False


    async def fetch_one(self, query: str, params: tuple = ()):
        """
        Fetches a single row from the database.
        Returns the row as a Record object (dictionary-like) or None if no row is found.
        """
        await self.connect()  # Ensure connection is open
        try:
            # Use the adapter for placeholders
            adapted_query = adapt_query_placeholders(query)
            return await self.conn.fetchrow(adapted_query, *params)  # asyncpg takes params unpacked
        except asyncpg.exceptions.PostgresError as e:
            logger.error(f"Erro ao buscar uma linha: {query} com params {params}. Erro: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Erro inesperado ao buscar uma linha: {query} com params {params}. Erro: {e}", exc_info=True)
            return None


    async def fetch_all(self, query: str, params: tuple = ()):
        """
        Fetches all rows from the database.
        Returns a list of Record objects (dictionary-like) or an empty list.
        """
        await self.connect()  # Ensure connection is open
        try:
            # Use the adapter for placeholders
            adapted_query = adapt_query_placeholders(query)
            return await self.conn.fetch(adapted_query, *params)  # asyncpg takes params unpacked
        except asyncpg.exceptions.PostgresError as e:
            logger.error(f"Erro ao buscar todas as linhas: {query} com params {params}. Erro: {e}", exc_info=True)
            return []
        except Exception as e:
            logger.error(f"Erro inesperado ao buscar todas as linhas: {query} com params {params}. Erro: {e}", exc_info=True)
            return []

async def init_db() -> DatabaseManager:
    """
    Initializes the PostgreSQL database connection, creates necessary tables (if they don't exist),
    and returns an instance of DatabaseManager.
    Reads connection URL from DATABASE_URL environment variable.
    """
    logger.info("Inicializando o banco de dados PostgreSQL...")

    if not DATABASE_URL:
        logger.critical("Variável de ambiente DATABASE_URL não encontrada. Falha ao conectar ao banco de dados.")
        raise ValueError("DATABASE_URL environment variable not set.")

    # Remove SQLite specific path creation logic
    # db_dir = os.path.dirname(DATABASE_PATH)
    # if db_dir and not os.path.exists(db_dir):
    #     try:
    #         os.makedirs(db_dir)
    #         logger.info(f"Diretório do banco de dados criado: {db_dir}")
    #     except OSError as e:
    #         logger.critical(f"Falha ao criar o diretório do banco de dados '{db_dir}': {e}")
    #         raise

    db_manager = DatabaseManager(DATABASE_URL)
    try:
        await db_manager.connect()  # Connect using the manager
        logger.info(f"Conectado ao banco de dados PostgreSQL usando URL.")

        # Create tables if they don't exist (PostgreSQL syntax)
        # Use SERIAL for auto-incrementing PRIMARY KEY
        # TEXT is generally fine for storing various strings/JSON
        # TIMESTAMP can be used for date/time
        # BIGINT is better for Discord IDs (guild, user, channel, message, role)
        await db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                user_id BIGINT UNIQUE,
                username TEXT,
                balance INTEGER DEFAULT 0
            )
        """)
        await db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS settings (
                guild_id BIGINT PRIMARY KEY,
                prefix TEXT DEFAULT '!'
            )
        """)
        await db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS logs (
                log_id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                level TEXT,
                message TEXT
            )
        """)
        await db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS locked_channels (
                channel_id BIGINT PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                reason TEXT,
                locked_by_id BIGINT,
                locked_until_timestamp TIMESTAMP
            )
        """)
        await db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS lockdown_panel_settings (
                guild_id BIGINT PRIMARY KEY,
                channel_id BIGINT,
                message_id BIGINT
            )
        """)
        await db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS anti_raid_settings (
                guild_id BIGINT PRIMARY KEY,
                enabled BOOLEAN DEFAULT FALSE,
                min_account_age_hours INTEGER DEFAULT 24,
                join_burst_threshold INTEGER DEFAULT 10,
                join_burst_time_seconds INTEGER DEFAULT 60,
                channel_id BIGINT,
                message_id BIGINT
            )
        """)
        await db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS welcome_leave_settings (
                guild_id BIGINT PRIMARY KEY,
                welcome_channel_id BIGINT,
                welcome_message TEXT,
                welcome_embed_json TEXT,
                welcome_role_id BIGINT,
                leave_channel_id BIGINT,
                leave_message TEXT,
                leave_embed_json TEXT
            )
        """)
        await db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS welcome_leave_panel_settings (
                guild_id BIGINT PRIMARY KEY,
                panel_channel_id BIGINT,
                panel_message_id BIGINT
            )
        """)
        await db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS ticket_settings (
                guild_id BIGINT PRIMARY KEY,
                category_id BIGINT,
                panel_channel_id BIGINT,
                panel_message_id BIGINT,
                panel_embed_json TEXT,
                ticket_initial_embed_json TEXT,
                support_role_id BIGINT,
                transcript_channel_id BIGINT
            )
        """)
        await db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS active_tickets (
                ticket_id SERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                channel_id BIGINT UNIQUE NOT NULL,
                user_id BIGINT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'open',
                closed_by_id BIGINT,
                closed_at TIMESTAMP
            )
        """)
        await db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS saved_embeds (
                guild_id BIGINT NOT NULL,
                embed_name TEXT NOT NULL,
                embed_json TEXT NOT NULL,
                PRIMARY KEY (guild_id, embed_name)
            )
        """)
        await db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS marriages (
                guild_id BIGINT NOT NULL,
                partner1_id BIGINT NOT NULL,
                partner2_id BIGINT NOT NULL,
                married_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, partner1_id, partner2_id)
            )
        """)
        await db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS log_settings (
                guild_id BIGINT PRIMARY KEY,
                message_log_channel_id BIGINT,
                member_log_channel_id BIGINT,
                role_log_channel_id BIGINT,
                channel_log_channel_id BIGINT,
                moderation_log_channel_id BIGINT
            )
        """)
        await db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS moderation_logs (
                log_id SERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                action TEXT NOT NULL,
                target_id BIGINT NOT NULL,
                moderator_id BIGINT NOT NULL,
                reason TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # NOVA TABELA: anti_features_settings
        await db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS anti_features_settings (
                guild_id BIGINT PRIMARY KEY,
                panel_channel_id BIGINT,
                panel_message_id BIGINT,
                anti_spam_config_json TEXT,
                anti_link_config_json TEXT,
                anti_invite_config_json TEXT,
                anti_flood_config_json TEXT
            )
        """)

        logger.info("Tabelas verificadas/criadas com sucesso no PostgreSQL.")
        logger.info("Banco de dados inicializado com sucesso.")
        return db_manager
    except asyncpg.exceptions.PostgresError as e:
        logger.critical(f"Falha crítica ao inicializar o banco de dados PostgreSQL: {e}")
        if db_manager.conn:
            await db_manager.close()
        raise
    except Exception as e:
        logger.critical(f"Um erro inesperado ocorreu durante a inicialização do banco de dados PostgreSQL: {e}", exc_info=True)
        if db_manager.conn:
            await db_manager.close()
        raise
