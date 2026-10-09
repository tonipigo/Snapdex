"""
Snapdex entry point.

Syncs categories, groups, products, and prices for all tracked categories.
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
    conn = db.connect()

    # Pull remote changes from Turso Cloud to local database
    # This ensures we have the latest state before deciding whether to sync
    conn.pull()
    logger.info("Pulled remote state from Turso Cloud")

    http = TCGCSVClient()

    # 2. Check remote timestamp
    remote_ts = http.fetch_text("/last-updated.txt").strip()
    logger.info("Remote last-updated timestamp: %s", remote_ts)

    # 3. Decide whether to sync
    if not sync_state.should_sync(conn, remote_ts):
        logger.info("Nothing to do. Exiting.")
        return

    # 4. Run sync
    sync_state.mark_run(conn)
    try:
        sync.sync_categories(conn, http)
        sync.sync_groups(conn, http)
        sync.sync_all_products(conn, http)
        sync.sync_all_prices(conn, http)
        sync_state.mark_success(conn, remote_ts)

        # Push local changes to Turso Cloud
        # Only push if the sync completed successfully
        conn.push()
        logger.info("Pushed changes to Turso Cloud")

        logger.info("Sync completed successfully.")
    except Exception:
        logger.exception("Sync failed")
        sync_state.mark_failed(conn)
        raise


if __name__ == "__main__":
    main()