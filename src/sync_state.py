"""
Management of sync_state: the single row that tracks the sync progress.
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def get_state(client) -> dict:
    """Read the single sync_state row."""
    result = client.execute(
        "SELECT last_remote_timestamp, last_successful_sync, "
        "last_run_at, sync_in_progress FROM sync_state WHERE id = 1"
    )
    row = result.rows[0]
    return {
        "last_remote_timestamp": row[0],
        "last_successful_sync": row[1],
        "last_run_at": row[2],
        "sync_in_progress": row[3],
    }


def should_sync(client, remote_timestamp: str) -> bool:
    """
    Decide whether to run the sync.

    Returns True only if the remote timestamp is strictly newer than the
    local one, or if we have never synced before.
    """
    state = get_state(client)
    local_ts = state["last_remote_timestamp"]

    if local_ts is None:
        logger.info("No previous sync found. Sync required.")
        return True

    if remote_timestamp > local_ts:
        logger.info(
            "Remote timestamp is newer: %s > %s. Sync required.",
            remote_timestamp, local_ts,
        )
        return True

    logger.info(
        "Remote timestamp is not newer: %s <= %s. Sync not required.",
        remote_timestamp, local_ts,
    )
    return False


def mark_run(client):
    """Record that a sync attempt has started."""
    now = _now_iso()
    client.execute(
        "UPDATE sync_state SET last_run_at = ?, sync_in_progress = 1 WHERE id = 1",
        [now],
    )
    logger.info("sync_state.last_run_at updated to %s", now)


def mark_success(client, remote_timestamp: str):
    """Record a successful sync."""
    now = _now_iso()
    client.execute(
        "UPDATE sync_state "
        "SET last_remote_timestamp = ?, last_successful_sync = ?, "
        "sync_in_progress = 0 "
        "WHERE id = 1",
        [remote_timestamp, now],
    )
    logger.info(
        "sync_state updated: remote=%s, successful=%s",
        remote_timestamp, now,
    )


def mark_failed(client):
    """Clear the in-progress flag after a failure."""
    client.execute(
        "UPDATE sync_state SET sync_in_progress = 0 WHERE id = 1"
    )
    logger.warning("sync_state.sync_in_progress reset to 0 after failure")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")