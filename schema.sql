-- Snapdex schema
-- Target: Turso (libSQL / SQLite-compatible)
-- Decisioni di riferimento: schema_decisions.md
--
-- Nota sul partizionamento:
-- `price_history` è per ora una tabella unica. Il partizionamento per anno
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
    last_synced_at    TEXT    NOT NULL, -- quando abbiamo visto questa categoria per la prima volta

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
-- Snapshot corrente dei prezzi. Chiave composita (product_id, sub_type).
-- Un prodotto ha 1 prezzo in JP, 1-3 in EN.
-- Sovrascritta ad ogni sync (contiene solo l'ultimo snapshot).
--
-- NOTA: questa tabella è oggi ridondante con l'ultima riga di `price_history`.
-- Serve per query veloci su "prezzo attuale" senza scorrere lo storico.
-- La teniamo separata finché il costo di scrittura su Turso resta accettabile.
-- Se in futuro il costo diventa un problema, valuteremo di eliminarla e
-- ricavare l'ultimo prezzo da `price_history` con una query più pesante.

CREATE TABLE IF NOT EXISTS prices (
    source            TEXT    NOT NULL DEFAULT 'tcgcsv',
    product_id        INTEGER NOT NULL,
    sub_type          TEXT    NOT NULL,  -- 'Normal', 'Holofoil', 'Reverse Holofoil', ...
    low_price         REAL,
    mid_price         REAL,
    high_price        REAL,              -- audit only
    market_price      REAL,              -- nullable, campo principale
    direct_low_price  REAL,              -- nullable

    PRIMARY KEY (source, product_id, sub_type),
    FOREIGN KEY (source, product_id)
        REFERENCES products (source, product_id)
);

CREATE INDEX IF NOT EXISTS idx_prices_product
    ON prices (source, product_id);


-- ---------------------------------------------------------------------------
-- price_history
-- ---------------------------------------------------------------------------
-- Storico append-only. Una riga per (prodotto, variante, data).
-- Cresce molto nel tempo. Partizionamento rinviato a quando il volume
-- lo richiederà (vedi schema_decisions.md).
--
-- NOTA: il campo `snapshot_date` è la data in cui il prezzo è stato
-- osservato dal sync (UTC). Una riga per giorno per prodotto.

CREATE TABLE IF NOT EXISTS price_history (
    source            TEXT    NOT NULL DEFAULT 'tcgcsv',
    product_id        INTEGER NOT NULL,
    sub_type          TEXT    NOT NULL,
    snapshot_date     TEXT    NOT NULL,  -- 'YYYY-MM-DD'
    low_price         REAL,
    mid_price         REAL,
    high_price        REAL,
    market_price      REAL,
    direct_low_price  REAL,

    PRIMARY KEY (source, product_id, sub_type, snapshot_date),
    FOREIGN KEY (source, product_id)
        REFERENCES products (source, product_id)
);

CREATE INDEX IF NOT EXISTS idx_history_date
    ON price_history (snapshot_date);

CREATE INDEX IF NOT EXISTS idx_history_product_date
    ON price_history (source, product_id, snapshot_date);


-- ---------------------------------------------------------------------------
-- sync_state
-- ---------------------------------------------------------------------------
-- Stato del sync, in una sola riga (id = 1).
-- Contiene il timestamp remoto dell'ultimo last-updated.txt processato.

CREATE TABLE IF NOT EXISTS sync_state (
    id                     INTEGER PRIMARY KEY CHECK (id = 1),
    last_remote_timestamp  TEXT,           -- contenuto di last-updated.txt
    last_successful_sync   TEXT,           -- quando ha finito l'ultimo sync OK
    last_run_at            TEXT,           -- ultima esecuzione (anche fallita)
    sync_in_progress       INTEGER NOT NULL DEFAULT 0
);

-- Riga singola, inizializzata al primo avvio.
INSERT OR IGNORE INTO sync_state (id, sync_in_progress) VALUES (1, 0);