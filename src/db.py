import logging
import sqlite3
import libsql_client

from src import config

logger = logging.getLogger(__name__)


def connect():
    """Create a libsql_client connection to the database."""
    client = libsql_client.create_client_sync(url=config.DB_URL)
    logger.info("Connected to database: %s", config.DB_URL)
    return client


def apply_schema():
    """
    Apply schema.sql to the local database file using sqlite3.

    libsql_client doesn't provide a batch execution method, so we use
    sqlite3 directly for the schema. Since the DB is a local file,
    sqlite3 can write to it natively.
    """
    with open(config.SCHEMA_FILE, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    conn = sqlite3.connect(config.DB_PATH)
    try:
        conn.executescript(schema_sql)
        conn.commit()
        logger.info("Schema applied successfully from %s", config.SCHEMA_FILE)
    finally:
        conn.close()