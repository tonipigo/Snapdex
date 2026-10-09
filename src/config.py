"""
Configuration constants for Snapdex.
"""

import os
from dotenv import load_dotenv

# Carica le variabili dal file .env (nella root del progetto)
load_dotenv()

# --- Paths ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_FILE = os.path.join(PROJECT_ROOT, "schema.sql")

# --- Database ---
# Turso cloud (via pyturso local sync)
TURSO_DATABASE_URL = os.environ["TURSO_DATABASE_URL"]
TURSO_AUTH_TOKEN = os.environ["TURSO_AUTH_TOKEN"]

# Percorso del DB locale temporaneo usato da pyturso per il sync.
# IMPORTANTE: spostalo FUORI da OneDrive per evitare corruzione.
# Esempio: r"C:\Users\pigol\Snapdex\snapdex.db"
LOCAL_DB_PATH = os.path.join(PROJECT_ROOT, "snapdex.db")

# --- Source ---
SOURCE = "tcgcsv"

# --- Tracked categories ---
# Maps categoryId to language code.
TRACKED_CATEGORIES = {
    3: "en",    # Pokemon (English)
    85: "jp",   # Pokemon Japan
}

# --- Attribute normalization maps ---
# See schema_decisions.md for the rationale.

# Attributes that go into product_extended_attrs
ATTRIBUTE_MAP = {
    "Number":    "number",
    "Rarity":    "rarity",
    "Card Type": "card_type",
    "CardType":  "card_type",
}

# Attributes intentionally ignored (no warnings)
IGNORED_ATTRIBUTES = {
    "UPC",
    "HP",
    "Stage",
    "Weakness",
    "Resistance",
    "RetreatCost",
    "Retreat Cost",
    "CardText",
    "Description",
    "Flavor Text",
}

# Attributes ignored by pattern (prefix match, no warnings)
IGNORED_ATTRIBUTE_PREFIXES = {
    "Attack ",
}

# --- HTTP client ---
BASE_URL = "https://tcgcsv.com"
USER_AGENT = "Snapdex/0.1.0"
REQUEST_DELAY_SECONDS = 0.1