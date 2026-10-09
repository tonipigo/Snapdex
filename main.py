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
    client.execute("UPDATE sync_state SET last_remote_timestamp = NULL WHERE id = 1")
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
        # sync.sync_categories(client, http)
        # sync.sync_groups(client, http)
        sync.sync_products(client, http, group_id=3170)
        sync_state.mark_success(client, remote_ts)
        logger.info("Sync completed successfully.")
    except Exception:
        logger.exception("Sync failed")
        sync_state.mark_failed(client)
        raise

    result = client.execute(
        "SELECT COUNT(*) FROM products WHERE group_id = 3170 AND source = 'tcgcsv'"
    )
    print(f"Products in group 3170: {result.rows[0][0]}")

    result = client.execute(
        "SELECT attr_key, COUNT(*) FROM product_extended_attrs pea "
        "JOIN products p ON p.product_id = pea.product_id "
        "WHERE p.group_id = 3170 AND p.source = 'tcgcsv' "
        "GROUP BY attr_key ORDER BY attr_key"
    )
    print("Attributes for group 3170:")
    for row in result.rows:
        print(f"  - {row[0]}: {row[1]}")

    result = client.execute(
        "SELECT COUNT(*) FROM product_extended_attrs pea "
        "JOIN products p ON p.product_id = pea.product_id "
        "WHERE p.group_id = 3170 AND pea.attr_key = 'rarity' "
        "AND pea.attr_value IS NULL"
    )
    print(f"Products with NULL rarity: {result.rows[0][0]}")

if __name__ == "__main__":
    main()