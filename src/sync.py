"""
Sync logic for Snapdex.

Handles categories, groups, products, and prices.
"""

import logging
from datetime import datetime, timezone

from src import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

def sync_categories(conn, http):
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
        conn.execute(
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
            (
                cat["category_id"],
                cat["source"],
                cat["language"],
                cat["name"],
                cat["display_name"],
                cat["popularity"],
                cat["modified_on"],
                cat["last_synced_at"],
            ),
        )
    conn.commit()


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------

def sync_groups(conn, http):
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
            conn.execute(
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
                (
                    group["groupId"],
                    config.SOURCE,
                    category_id,
                    group["name"],
                    group.get("abbreviation"),
                    1 if group.get("isSupplemental") else 0,
                    group.get("publishedOn"),
                    group.get("modifiedOn"),
                ),
            )
            total += 1
        conn.commit()

    logger.info("Groups sync complete: %d groups upserted", total)


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

def sync_products(conn, http, group_id: int):
    """
    Download products for a single group and upsert them.

    For each product, writes one row in `products`, and one row per
    attribute in `product_extended_attrs` (only for keys in ATTRIBUTE_MAP).

    Attributes in IGNORED_ATTRIBUTES are silently skipped.
    Unknown attributes are logged as warnings and skipped.
    """
    category_id = _find_category_for_group(conn, group_id)
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
        _upsert_product(conn, product, category_id, language)
        _upsert_product_attributes(conn, product)

    conn.commit()
    logger.info("Products sync complete for group %d", group_id)


def sync_products_for_groups(conn, http, group_ids: list):
    """
    Download products for a list of groups, one group at a time.

    If a group fails, logs the error and continues with the next.
    At the end, logs a summary of successes and failures.
    """
    succeeded = 0
    failed = 0

    for group_id in group_ids:
        try:
            sync_products(conn, http, group_id)
            succeeded += 1
        except Exception:
            logger.exception("Failed to sync products for group %d", group_id)
            conn.rollback()
            failed += 1

    logger.info(
        "Batch sync complete: %d succeeded, %d failed",
        succeeded, failed,
    )


def sync_all_products(conn, http):
    """
    Sync products for all tracked categories.

    For each category in TRACKED_CATEGORIES, reads its groups from the DB
    and syncs products for all of them, one group at a time.
    """
    for category_id in config.TRACKED_CATEGORIES:
        logger.info("Starting products sync for category %d", category_id)

        cursor = conn.execute(
            "SELECT group_id FROM groups "
            "WHERE source = ? AND category_id = ? "
            "ORDER BY group_id",
            (config.SOURCE, category_id),
        )
        group_ids = [row["group_id"] for row in cursor.fetchall()]
        logger.info(
            "Category %d has %d groups to sync",
            category_id, len(group_ids),
        )

        sync_products_for_groups(conn, http, group_ids)


# ---------------------------------------------------------------------------
# Prices
# ---------------------------------------------------------------------------

def sync_prices(conn, http, group_id: int, snapshot_date: str = None):
    """
    Download prices for a single group and append them to `prices`.

    Each price record is inserted with the given snapshot_date. Previous
    snapshots for the same product are preserved.

    snapshot_date defaults to today (UTC) in 'YYYY-MM-DD' format.
    """
    if snapshot_date is None:
        snapshot_date = _today_iso()

    category_id = _find_category_for_group(conn, group_id)
    if category_id is None:
        logger.error("Group %d not found in DB, cannot sync prices", group_id)
        return

    path = f"/tcgplayer/{category_id}/{group_id}/prices"
    logger.info("Fetching prices for group %d (category %d)", group_id, category_id)

    data = http.fetch_json(path)
    results = data.get("results", [])
    logger.info("Received %d price records for group %d", len(results), group_id)

    for price in results:
        _insert_price_snapshot(conn, price, snapshot_date)

    conn.commit()
    logger.info("Prices sync complete for group %d", group_id)


def _sync_prices_for_groups(conn, http, group_ids: list, snapshot_date: str):
    """
    Download prices for a list of groups, one group at a time.

    Returns (succeeded, failed).
    """
    succeeded = 0
    failed = 0

    for group_id in group_ids:
        try:
            sync_prices(conn, http, group_id, snapshot_date)
            succeeded += 1
        except Exception:
            logger.exception("Failed to sync prices for group %d", group_id)
            conn.rollback()
            failed += 1

    logger.info(
        "Batch prices sync complete: %d succeeded, %d failed",
        succeeded, failed,
    )
    return succeeded, failed


def sync_all_prices(conn, http):
    """
    Sync prices for all tracked categories.

    Only updates sync_state.last_price_snapshot if every group was
    successfully synced. This ensures the "current price" always points
    to a complete snapshot.
    """
    snapshot_date = _today_iso()
    logger.info("Snapshot date: %s", snapshot_date)

    all_succeeded = True
    for category_id in config.TRACKED_CATEGORIES:
        logger.info("Starting prices sync for category %d", category_id)

        cursor = conn.execute(
            "SELECT group_id FROM groups "
            "WHERE source = ? AND category_id = ? "
            "ORDER BY group_id",
            (config.SOURCE, category_id),
        )
        group_ids = [row["group_id"] for row in cursor.fetchall()]
        logger.info(
            "Category %d has %d groups to sync",
            category_id, len(group_ids),
        )

        succeeded, failed = _sync_prices_for_groups(
            conn, http, group_ids, snapshot_date
        )
        if failed > 0:
            all_succeeded = False

    if all_succeeded:
        _set_last_price_snapshot(conn, snapshot_date)
    else:
        logger.warning(
            "Not updating last_price_snapshot: some groups failed to sync"
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_category_for_group(conn, group_id: int):
    """Return the category_id of a group, or None if not found."""
    cursor = conn.execute(
        "SELECT category_id FROM groups WHERE source = ? AND group_id = ?",
        (config.SOURCE, group_id),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return row["category_id"]


def _upsert_product(conn, product: dict, category_id: int, language: str):
    """Upsert one row into products."""
    conn.execute(
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
        (
            product["productId"],
            config.SOURCE,
            language,
            category_id,
            product["groupId"],
            product["name"],
            product.get("imageUrl"),
            product.get("url"),
            product.get("modifiedOn"),
        ),
    )


def _upsert_product_attributes(conn, product: dict):
    """
    Upsert extendedData attributes for one product.

    Order of checks:
      1. Exact match in IGNORED_ATTRIBUTES            -> skip silently
      2. Prefix match in IGNORED_ATTRIBUTE_PREFIXES   -> skip silently
      3. Match in ATTRIBUTE_MAP                       -> normalize and write
      4. Otherwise                                    -> log warning and skip
    """
    product_id = product["productId"]
    extended = product.get("extendedData", [])

    for attr in extended:
        raw_key = attr.get("name")
        if raw_key is None:
            continue

        # 1. Ignored by exact name
        if raw_key in config.IGNORED_ATTRIBUTES:
            continue

        # 2. Ignored by prefix (e.g. "Attack 1", "Attack 2", ...)
        if any(raw_key.startswith(p) for p in config.IGNORED_ATTRIBUTE_PREFIXES):
            continue

        # 3. Mapped: normalize and write
        if raw_key in config.ATTRIBUTE_MAP:
            canonical_key = config.ATTRIBUTE_MAP[raw_key]
            value = attr.get("value")

            # Special case: JP "None" rarity -> NULL
            if canonical_key == "rarity" and value == "None":
                value = None

            conn.execute(
                """
                INSERT INTO product_extended_attrs
                    (source, product_id, attr_key, attr_value)
                VALUES
                    (?, ?, ?, ?)
                ON CONFLICT (source, product_id, attr_key) DO UPDATE SET
                    attr_value = excluded.attr_value
                """,
                (config.SOURCE, product_id, canonical_key, value),
            )
            continue

        # 4. Unknown: log warning and skip
        logger.warning(
            "Unknown attribute key for product %d: %r",
            product_id, raw_key,
        )


def _insert_price_snapshot(conn, price: dict, snapshot_date: str):
    """Insert one row into `prices` for the given snapshot date."""
    conn.execute(
        """
        INSERT INTO prices
            (source, product_id, sub_type, snapshot_date, low_price,
             mid_price, high_price, market_price, direct_low_price)
        VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (source, product_id, sub_type, snapshot_date) DO UPDATE SET
            low_price         = excluded.low_price,
            mid_price         = excluded.mid_price,
            high_price        = excluded.high_price,
            market_price      = excluded.market_price,
            direct_low_price  = excluded.direct_low_price
        """,
        (
            config.SOURCE,
            price["productId"],
            price["subTypeName"],
            snapshot_date,
            price.get("lowPrice"),
            price.get("midPrice"),
            price.get("highPrice"),
            price.get("marketPrice"),
            price.get("directLowPrice"),
        ),
    )


def _set_last_price_snapshot(conn, snapshot_date: str):
    """Update sync_state.last_price_snapshot to the given date."""
    conn.execute(
        "UPDATE sync_state SET last_price_snapshot = ? WHERE id = 1",
        (snapshot_date,),
    )
    conn.commit()
    logger.info("sync_state.last_price_snapshot updated to %s", snapshot_date)


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")