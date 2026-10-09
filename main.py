"""
Snapdex entry point.

For now, this only verifies that the database connection works and
that the schema can be applied. The actual sync logic will be added later.
"""

import logging

from src import db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def main():
    db.apply_schema()          # prima, applica lo schema
    client = db.connect()      # poi, connetti con libsql_client
    print("Database ready.")

    result = client.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    print("\nTables in database:")
    for row in result.rows:
        print(f"  - {row[0]}")

if __name__ == "__main__":
    main()

