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

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
