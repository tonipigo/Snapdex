"""
Configuration constants for Snapdex.
"""

import os

# --- Paths ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_FILE = os.path.join(PROJECT_ROOT, "schema.sql")

# --- Database ---
# Local DB for development. Replace with Turso cloud URL + token later.
DB_PATH = os.path.join(PROJECT_ROOT, "snapdex.db")
DB_URL = f"file:{DB_PATH}"

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

# Attributes that are intentionally ignored (don't log warnings for them)
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
    "Attack 1",
    "Attack 2",
}

# --- HTTP client ---
BASE_URL = "https://tcgcsv.com"
USER_AGENT = "Snapdex/0.1.0"
REQUEST_DELAY_SECONDS = 0.1