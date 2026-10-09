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
        # Prendi 5 gruppi EN a caso dal DB per il test
        result = client.execute(
            "SELECT group_id FROM groups "
            "WHERE source = 'tcgcsv' AND category_id = 3 "
            "ORDER BY group_id DESC LIMIT 5"
        )
        group_ids = [row[0] for row in result.rows]
        logger.info("Testing batch sync on groups: %s", group_ids)

        sync.sync_products_for_groups(client, http, group_ids)
        sync_state.mark_success(client, remote_ts)
        logger.info("Sync completed successfully.")
    except Exception:
        logger.exception("Sync failed")
        sync_state.mark_failed(client)
        raise

if __name__ == "__main__":
    main()