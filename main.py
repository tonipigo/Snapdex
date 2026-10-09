"""
Snapdex entry point.

Currently only syncs categories. Groups, products, and prices will be
added incrementally.
"""

import logging

from src import config, db, sync, sync_state
from src.http_client import TCGCSVClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


def main():
    # 1. Prepare DB and HTTP client
    db.apply_schema()
    client = db.connect()
    #client.execute("UPDATE sync_state SET last_remote_timestamp = NULL WHERE id = 1")
    http = TCGCSVClient()

    # 2. Check remote timestamp
    remote_ts = http.fetch_text("/last-updated.txt").strip()
    logger.info("Remote last-updated timestamp: %s", remote_ts)

    # 3. Decide whether to sync
    if not sync_state.should_sync(client, remote_ts):
        logger.info("Nothing to do. Exiting.")
        return

    # 4. Run sync
    sync_state.mark_run(client)
    try:
        result = client.execute(
            "SELECT group_id FROM groups "
            "WHERE source = 'tcgcsv' AND category_id = 3 "
            "ORDER BY group_id"
        )
        group_ids = [row[0] for row in result.rows]
        logger.info("Starting full EN products sync: %d groups", len(group_ids))

        sync.sync_products_for_groups(client, http, group_ids)
        sync_state.mark_success(client, remote_ts)
        logger.info("Sync completed successfully.")

        # --- TEMPORARY VERIFICATION BLOCK ---
        # Remove this block after checking the numbers.
        result = client.execute(
            "SELECT COUNT(*) FROM products "
            "WHERE source = 'tcgcsv' AND language = 'en'"
        )
        print(f"Total EN products: {result.rows[0][0]}")

        result = client.execute(
            "SELECT COUNT(*) FROM product_extended_attrs pea "
            "JOIN products p ON p.product_id = pea.product_id "
            "AND p.source = pea.source "
            "WHERE p.source = 'tcgcsv' AND p.language = 'en'"
        )
        print(f"Total EN attributes: {result.rows[0][0]}")

        result = client.execute(
            "SELECT COUNT(DISTINCT group_id) FROM products "
            "WHERE source = 'tcgcsv' AND language = 'en'"
        )
        print(f"Groups covered: {result.rows[0][0]}")

        result = client.execute(
            "SELECT COUNT(*) FROM products p "
            "WHERE p.source = 'tcgcsv' AND p.language = 'en' "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM product_extended_attrs pea "
            "  WHERE pea.source = p.source AND pea.product_id = p.product_id"
            ")"
        )
        print(f"Products with no attributes (likely sealed): {result.rows[0][0]}")
        # --- END TEMPORARY VERIFICATION BLOCK ---

    except Exception:
        logger.exception("Sync failed")
        sync_state.mark_failed(client)
        raise


if __name__ == "__main__":
    main()