import aiosqlite
import os
import logging
import datetime

# Configure logging for the database module
logger = logging.getLogger(__name__)

# Define the database path
DATABASE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'bot_database.db')

class DatabaseManager:
    """
    Manages the asynchronous SQLite database connection and operations.
    Provides methods for executing queries, fetching single rows, and fetching all rows.
    """
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = None

    async def connect(self):
        """Establishes the database connection."""
        if self.conn is None:
            self.conn = await aiosqlite.connect(self.db_path)
            self.conn.row_factory = aiosqlite.Row # Allows accessing columns by name
            logger.info("Conexão com o banco de dados estabelecida.")

    async def close(self):
        """Closes the database connection."""
        if self.conn:
            await self.conn.close()
            self.conn = None
            logger.info("Conexão com o banco de dados fechada.")

    async def execute_query(self, query: str, params: tuple = ()) -> bool:
        """
        Executes a database query (INSERT, UPDATE, DELETE).
        Returns True on success, False on error.
        """
        await self.connect() # Ensure connection is open
        try:
            await self.conn.execute(query, params)
            await self.conn.commit()
            return True
        except aiosqlite.Error as e:
            logger.error(f"Erro ao executar query: {query} com params {params}. Erro: {e}", exc_info=True)
            return False

    async def fetch_one(self, query: str, params: tuple = ()):
        """
        Fetches a single row from the database.
        Returns the row as a dictionary-like object (aiosqlite.Row) or None if no row is found.
        """
        await self.connect() # Ensure connection is open
        try:
            async with self.conn.execute(query, params) as cursor:
                return await cursor.fetchone()
        except aiosqlite.Error as e:
            logger.error(f"Erro ao buscar uma linha: {query} com params {params}. Erro: {e}", exc_info=True)
            return None

    async def fetch_all(self, query: str, params: tuple = ()):
        """
        Fetches all rows from the database.
        Returns a list of dictionary-like objects (aiosqlite.Row) or an empty list.
        """
        await self.connect() # Ensure connection is open
        try:
            async with self.conn.execute(query, params) as cursor:
                return await cursor.fetchall()
        except aiosqlite.Error as e:
            logger.error(f"Erro ao buscar todas as linhas: {query} com params {params}. Erro: {e}", exc_info=True)
            return []

async def init_db() -> DatabaseManager:
    """
    Initializes the SQLite database connection, creates necessary tables,
    and returns an instance of DatabaseManager.
    """
    logger.info("Inicializando o banco de dados...")
    db_dir = os.path.dirname(DATABASE_PATH)

    # Create the directory if it doesn't exist
    if db_dir and not os.path.exists(db_dir):
        try:
            os.makedirs(db_dir)
            logger.info(f"Diretório do banco de dados criado: {db_dir}")
        except OSError as e:
            logger.critical(f"Falha ao criar o diretório do banco de dados '{db_dir}': {e}")
            raise # Re-raise the exception as it's a critical failure

    db_manager = DatabaseManager(DATABASE_PATH)
    try:
        await db_manager.connect() # Connect using the manager
        logger.info(f"Conectado ao banco de dados em: {DATABASE_PATH}")

        # Create tables
        await db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE,
                username TEXT,
                balance INTEGER DEFAULT 0
            )
        """)
        await db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS settings (
                guild_id INTEGER PRIMARY KEY,
                prefix TEXT DEFAULT '!'
            )
        """)
        await db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                level TEXT,
                message TEXT
            )
        """)
        await db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS locked_channels (
                channel_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                reason TEXT,
                locked_by_id INTEGER,
                locked_until_timestamp TEXT
            )
        """)
        await db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS lockdown_panel_settings (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER,
                message_id INTEGER
            )
        """)
        await db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS anti_raid_settings (
                guild_id INTEGER PRIMARY KEY,
                enabled BOOLEAN DEFAULT FALSE,
                min_account_age_hours INTEGER DEFAULT 24,
                join_burst_threshold INTEGER DEFAULT 10,
                join_burst_time_seconds INTEGER DEFAULT 60,
                channel_id INTEGER,
                message_id INTEGER
            )
        """)
        await db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS welcome_leave_settings (
                guild_id INTEGER PRIMARY KEY,
                welcome_channel_id INTEGER,
                welcome_message TEXT,
                welcome_embed_json TEXT,
                welcome_role_id INTEGER,
                leave_channel_id INTEGER,
                leave_message TEXT,
                leave_embed_json TEXT
            )
        """)
        await db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS welcome_leave_panel_settings (
                guild_id INTEGER PRIMARY KEY,
                panel_channel_id INTEGER,
                panel_message_id INTEGER
            )
        """)
        await db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS ticket_settings (
                guild_id INTEGER PRIMARY KEY,
                category_id INTEGER,
                panel_channel_id INTEGER,
                panel_message_id INTEGER,
                panel_embed_json TEXT,
                ticket_initial_embed_json TEXT,
                support_role_id INTEGER,
                transcript_channel_id INTEGER
            )
        """)
        await db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS active_tickets (
                ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER UNIQUE NOT NULL,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT DEFAULT 'open',
                closed_by_id INTEGER,
                closed_at TEXT
            )
        """)
        await db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS saved_embeds (
                guild_id INTEGER NOT NULL,
                embed_name TEXT NOT NULL,
                embed_json TEXT NOT NULL,
                PRIMARY KEY (guild_id, embed_name)
            )
        """)
        await db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS marriages (
                guild_id INTEGER NOT NULL,
                partner1_id INTEGER NOT NULL,
                partner2_id INTEGER NOT NULL,
                married_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, partner1_id, partner2_id)
            )
        """)
        await db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS log_settings (
                guild_id INTEGER PRIMARY KEY,
                message_log_channel_id INTEGER,
                member_log_channel_id INTEGER,
                role_log_channel_id INTEGER,
                channel_log_channel_id INTEGER,
                moderation_log_channel_id INTEGER
            )
        """)
        await db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS moderation_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                target_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                reason TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # NOVA TABELA: anti_features_settings
        await db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS anti_features_settings (
                guild_id INTEGER PRIMARY KEY,
                panel_channel_id INTEGER,
                panel_message_id INTEGER,
                anti_spam_config_json TEXT,
                anti_link_config_json TEXT,
                anti_invite_config_json TEXT,
                anti_flood_config_json TEXT
            )
        """)

        logger.info("Tabelas verificadas/criadas com sucesso.")
        logger.info("Banco de dados inicializado com sucesso.")
        return db_manager
    except aiosqlite.Error as e:
        logger.critical(f"Falha crítica ao inicializar o banco de dados: {e}")
        await db_manager.close()
        raise
    except Exception as e:
        logger.critical(f"Um erro inesperado ocorreu durante a inicialização do banco de dados: {e}")
        await db_manager.close()
        raise
