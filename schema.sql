-- Snapdex schema
-- Target: Turso (libSQL / SQLite-compatible)
-- Decisioni di riferimento: schema_decisions.md
--
-- Nota sul partizionamento:
-- `prices` è per ora una tabella unica. Il partizionamento per anno
-- è rinviato a quando il volume lo richiederà (vedi schema_decisions.md).

PRAGMA foreign_keys = ON;


-- ---------------------------------------------------------------------------
-- categories
-- ---------------------------------------------------------------------------
-- Una riga per categoria TCGCSV tracciata (Pokemon EN, Pokemon JP, ...).
-- `language` non è fornito dall'API, viene aggiunto in fase di sync
-- tramite mappa statica categoryId -> language.

CREATE TABLE IF NOT EXISTS categories (
    category_id       INTEGER NOT NULL,
    source            TEXT    NOT NULL DEFAULT 'tcgcsv',
    language          TEXT    NOT NULL,
    name              TEXT    NOT NULL,
    display_name      TEXT,
    popularity        INTEGER,
    modified_on       TEXT,             -- audit only
    last_synced_at    TEXT    NOT NULL,

    PRIMARY KEY (source, category_id)
);

CREATE INDEX IF NOT EXISTS idx_categories_language
    ON categories (language);


-- ---------------------------------------------------------------------------
-- groups
-- ---------------------------------------------------------------------------
-- Un set (espansione, promo set, ecc.) dentro una categoria.

CREATE TABLE IF NOT EXISTS groups (
    group_id          INTEGER NOT NULL,
    source            TEXT    NOT NULL DEFAULT 'tcgcsv',
    category_id       INTEGER NOT NULL,
    name              TEXT    NOT NULL,
    abbreviation      TEXT,
    is_supplemental   INTEGER,          -- 0/1, audit only
    published_on      TEXT,             -- audit only
    modified_on       TEXT,             -- audit only

    PRIMARY KEY (source, group_id),
    FOREIGN KEY (source, category_id)
        REFERENCES categories (source, category_id)
);

CREATE INDEX IF NOT EXISTS idx_groups_category
    ON groups (source, category_id);


-- ---------------------------------------------------------------------------
-- products
-- ---------------------------------------------------------------------------
-- Una riga per prodotto: carta singola, sealed, code card, ecc.
-- `language` è denormalizzato da category_id, per query rapide.

CREATE TABLE IF NOT EXISTS products (
    product_id        INTEGER NOT NULL,
    source            TEXT    NOT NULL DEFAULT 'tcgcsv',
    language          TEXT    NOT NULL,
    category_id       INTEGER NOT NULL,
    group_id          INTEGER NOT NULL,
    name              TEXT    NOT NULL,
    image_url         TEXT,
    url               TEXT,
    modified_on       TEXT,             -- audit only

    PRIMARY KEY (source, product_id),
    FOREIGN KEY (source, category_id)
        REFERENCES categories (source, category_id),
    FOREIGN KEY (source, group_id)
        REFERENCES groups (source, group_id)
);

CREATE INDEX IF NOT EXISTS idx_products_language_group
    ON products (language, source, group_id);

CREATE INDEX IF NOT EXISTS idx_products_group
    ON products (source, group_id);


-- ---------------------------------------------------------------------------
-- product_extended_attrs
-- ---------------------------------------------------------------------------
-- Attributi categorici e brevi di un prodotto, in formato chiave-valore.
-- Solo le chiavi in ATTRIBUTE_MAP (vedi schema_decisions.md) finiscono qui.

CREATE TABLE IF NOT EXISTS product_extended_attrs (
    source            TEXT    NOT NULL DEFAULT 'tcgcsv',
    product_id        INTEGER NOT NULL,
    attr_key          TEXT    NOT NULL,  -- 'number', 'rarity', 'card_type'
    attr_value        TEXT,              -- nullable

    PRIMARY KEY (source, product_id, attr_key),
    FOREIGN KEY (source, product_id)
        REFERENCES products (source, product_id)
);

CREATE INDEX IF NOT EXISTS idx_attrs_key_value
    ON product_extended_attrs (attr_key, attr_value);


-- ---------------------------------------------------------------------------
-- prices
-- ---------------------------------------------------------------------------
-- Storico completo dei prezzi. Una riga per (prodotto, variante, data).
-- La chiave primaria include `snapshot_date`: ad ogni sync giornaliero
-- si aggiunge una nuova riga, senza sovrascrivere le precedenti.
--
-- Il valore "prezzo attuale" si ottiene filtrando per l'ultima
-- snapshot_date, che è memorizzata in sync_state.last_price_snapshot.
--
-- La tabella cresce molto nel tempo (~100k righe/giorno, ~35M/anno).
-- Il partizionamento per anno è rinviato a quando il volume lo richiederà.

CREATE TABLE IF NOT EXISTS prices (
    source            TEXT    NOT NULL DEFAULT 'tcgcsv',
    product_id        INTEGER NOT NULL,
    sub_type          TEXT    NOT NULL,  -- 'Normal', 'Holofoil', 'Reverse Holofoil', ...
    snapshot_date     TEXT    NOT NULL,  -- 'YYYY-MM-DD'
    low_price         REAL,
    mid_price         REAL,
    high_price        REAL,              -- audit only
    market_price      REAL,              -- nullable, campo principale
    direct_low_price  REAL,              -- nullable

    PRIMARY KEY (source, product_id, sub_type, snapshot_date),
    FOREIGN KEY (source, product_id)
        REFERENCES products (source, product_id)
);

CREATE INDEX IF NOT EXISTS idx_prices_date
    ON prices (snapshot_date);

CREATE INDEX IF NOT EXISTS idx_prices_product_date
    ON prices (source, product_id, snapshot_date);


-- ---------------------------------------------------------------------------
-- sync_state
-- ---------------------------------------------------------------------------
-- Stato del sync, in una sola riga (id = 1).
-- Contiene il timestamp remoto dell'ultimo last-updated.txt processato
-- e l'ultima snapshot_date completata per i prezzi.

CREATE TABLE IF NOT EXISTS sync_state (
    id                     INTEGER PRIMARY KEY CHECK (id = 1),
    last_remote_timestamp  TEXT,           -- contenuto di last-updated.txt
    last_successful_sync   TEXT,           -- quando ha finito l'ultimo sync OK
    last_run_at            TEXT,           -- ultima esecuzione (anche fallita)
    sync_in_progress       INTEGER NOT NULL DEFAULT 0,
    last_price_snapshot    TEXT            -- 'YYYY-MM-DD', ultima snapshot prezzi completa
);

-- Riga singola, inizializzata al primo avvio.
INSERT OR IGNORE INTO sync_state (id, sync_in_progress) VALUES (1, 0);