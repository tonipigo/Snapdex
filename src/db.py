import logging
import sqlite3
import os
import turso
import turso.sync

from src import config

logger = logging.getLogger(__name__)


def connect():
    """Connect to local Turso database with cloud sync."""
    db = turso.sync.connect(
        config.LOCAL_DB_PATH,
        remote_url=config.TURSO_DATABASE_URL,
        auth_token=config.TURSO_AUTH_TOKEN,
    )
    logger.info("Connected to Turso (local + sync)")
    return db


def apply_schema():
    """
    Apply schema.sql using sqlite3 (standard library).
    
    pyturso's executescript() has parsing issues with our schema
    (comments, PRAGMA, INSERT OR IGNORE). Since schema application is
    a one-time operation, we use sqlite3 which is battle-tested.
    """
    with open(config.SCHEMA_FILE, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    conn = sqlite3.connect(config.LOCAL_DB_PATH)
    try:
        conn.executescript(schema_sql)
        conn.commit()
        logger.info("Schema applied successfully from %s", config.SCHEMA_FILE)
    finally:
        conn.close()