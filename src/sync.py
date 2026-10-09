"""
Sync logic for Snapdex.

Currently only handles categories. Groups, products, and prices will be
added incrementally, following the same pattern.
"""

import logging
from datetime import datetime, timezone

from src import config

logger = logging.getLogger(__name__)


def sync_categories(client, http):
    """
    Download categories and upsert the ones we track into the database.

    Filters by config.TRACKED_CATEGORIES. Adds the `language` column
    from that map (the API doesn't provide it).
    """
    data = http.fetch_json("/tcgplayer/categories")
    results = data.get("results", [])

    logger.info("Received %d categories from API", len(results))

    now = _now_iso()
    tracked = []
    for category in results:
        category_id = category["categoryId"]
        if category_id not in config.TRACKED_CATEGORIES:
            continue

        language = config.TRACKED_CATEGORIES[category_id]
        tracked.append({
            "category_id": category_id,
            "source": config.SOURCE,
            "language": language,
            "name": category["name"],
            "display_name": category.get("displayName"),
            "popularity": category.get("popularity"),
            "modified_on": category.get("modifiedOn"),
            "last_synced_at": now,
        })

    if not tracked:
        logger.warning("No tracked categories found in API response")
        return

    logger.info("Upserting %d tracked categories", len(tracked))

    for cat in tracked:
        client.execute(
            """
            INSERT INTO categories
                (category_id, source, language, name, display_name,
                 popularity, modified_on, last_synced_at)
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (source, category_id) DO UPDATE SET
                language       = excluded.language,
                name           = excluded.name,
                display_name   = excluded.display_name,
                popularity     = excluded.popularity,
                modified_on    = excluded.modified_on,
                last_synced_at = excluded.last_synced_at
            """,
            [
                cat["category_id"],
                cat["source"],
                cat["language"],
                cat["name"],
                cat["display_name"],
                cat["popularity"],
                cat["modified_on"],
                cat["last_synced_at"],
            ],
        ) 


def sync_groups(client, http):
    """
    Download groups for each tracked category and upsert them.
    """
    total = 0
    for category_id, language in config.TRACKED_CATEGORIES.items():
        logger.info(
            "Fetching groups for category %d (%s)", category_id, language
        )
        data = http.fetch_json(f"/tcgplayer/{category_id}/groups")
        results = data.get("results", [])
        logger.info(
            "Received %d groups for category %d", len(results), category_id
        )

        for group in results:
            client.execute(
                """
                INSERT INTO groups
                    (group_id, source, category_id, name, abbreviation,
                     is_supplemental, published_on, modified_on)
                VALUES
                    (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (source, group_id) DO UPDATE SET
                    category_id     = excluded.category_id,
                    name            = excluded.name,
                    abbreviation    = excluded.abbreviation,
                    is_supplemental = excluded.is_supplemental,
                    published_on    = excluded.published_on,
                    modified_on     = excluded.modified_on
                """,
                [
                    group["groupId"],
                    config.SOURCE,
                    category_id,
                    group["name"],
                    group.get("abbreviation"),
                    1 if group.get("isSupplemental") else 0,
                    group.get("publishedOn"),
                    group.get("modifiedOn"),
                ],
            )
            total += 1

    logger.info("Groups sync complete: %d groups upserted", total)

def sync_products(client, http, group_id: int):
    """
    Download products for a single group and upsert them.

    For each product, writes one row in `products`, and one row per
    attribute in `product_extended_attrs` (only for keys in ATTRIBUTE_MAP).

    Attributes in IGNORED_ATTRIBUTES are silently skipped.
    Unknown attributes are logged as warnings and skipped.
    """
    category_id = _find_category_for_group(client, group_id)
    if category_id is None:
        logger.error("Group %d not found in DB, cannot sync products", group_id)
        return

    language = config.TRACKED_CATEGORIES[category_id]
    path = f"/tcgplayer/{category_id}/{group_id}/products"
    logger.info("Fetching products for group %d (category %d)", group_id, category_id)

    data = http.fetch_json(path)
    results = data.get("results", [])
    logger.info("Received %d products for group %d", len(results), group_id)

    for product in results:
        _upsert_product(client, product, category_id, language)
        _upsert_product_attributes(client, product)

    logger.info("Products sync complete for group %d", group_id)


def _find_category_for_group(client, group_id: int):
    """Return the category_id of a group, or None if not found."""
    result = client.execute(
        "SELECT category_id FROM groups WHERE source = ? AND group_id = ?",
        [config.SOURCE, group_id],
    )
    if not result.rows:
        return None
    return result.rows[0][0]


def _upsert_product(client, product: dict, category_id: int, language: str):
    """Upsert one row into products."""
    client.execute(
        """
        INSERT INTO products
            (product_id, source, language, category_id, group_id, name,
             image_url, url, modified_on)
        VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (source, product_id) DO UPDATE SET
            language    = excluded.language,
            category_id = excluded.category_id,
            group_id    = excluded.group_id,
            name        = excluded.name,
            image_url   = excluded.image_url,
            url         = excluded.url,
            modified_on = excluded.modified_on
        """,
        [
            product["productId"],
            config.SOURCE,
            language,
            category_id,
            product["groupId"],
            product["name"],
            product.get("imageUrl"),
            product.get("url"),
            product.get("modifiedOn"),
        ],
    )


def _upsert_product_attributes(client, product: dict):
    """
    Upsert extendedData attributes for one product.

    Only keys in ATTRIBUTE_MAP are written. Keys in IGNORED_ATTRIBUTES are
    silently skipped. Unknown keys are logged as warnings.
    """
    product_id = product["productId"]
    extended = product.get("extendedData", [])

    for attr in extended:
        raw_key = attr.get("name")
        if raw_key is None:
            continue

        # Ignored: skip silently
        if raw_key in config.IGNORED_ATTRIBUTES:
            continue

        # Mapped: normalize and write
        if raw_key in config.ATTRIBUTE_MAP:
            canonical_key = config.ATTRIBUTE_MAP[raw_key]
            value = attr.get("value")

            # Special case: JP "None" rarity -> NULL
            if canonical_key == "rarity" and value == "None":
                value = None

            client.execute(
                """
                INSERT INTO product_extended_attrs
                    (source, product_id, attr_key, attr_value)
                VALUES
                    (?, ?, ?, ?)
                ON CONFLICT (source, product_id, attr_key) DO UPDATE SET
                    attr_value = excluded.attr_value
                """,
                [config.SOURCE, product_id, canonical_key, value],
            )
            continue

        # Unknown: log and skip
        logger.warning(
            "Unknown attribute key for product %d: %r",
            product_id, raw_key,
        )

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
