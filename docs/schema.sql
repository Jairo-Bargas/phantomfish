-- ============================================================
-- PHANTOM FISH — Esquema de base de datos (PostgreSQL)
-- Núcleo de gestión: socios, pagos, compras, ventas, documentos.
-- No incluye ecommerce (carritos/pedidos) a propósito: ese
-- módulo se agrega después y consulta esta misma base.
-- ============================================================

-- ---------- SOCIOS ----------
CREATE TABLE partners (
    id            SERIAL PRIMARY KEY,
    name          TEXT NOT NULL,
    pct_share     NUMERIC(5,2) NOT NULL CHECK (pct_share > 0 AND pct_share <= 100),
    active        BOOLEAN NOT NULL DEFAULT true,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Regla de aplicación (validar en el backend, no en SQL):
-- la suma de pct_share de los socios activos debe dar 100.

-- ---------- COTIZACIONES (registro histórico, auditable) ----------
CREATE TABLE exchange_rate_log (
    id              SERIAL PRIMARY KEY,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    rate_type       TEXT NOT NULL DEFAULT 'oficial',   -- oficial | blue | mep | ccl
    buy             NUMERIC(12,4),
    sell            NUMERIC(12,4),
    source          TEXT NOT NULL DEFAULT 'dolarapi.com'
);
-- Se guarda cada consulta a la API como log/auditoría.
-- El valor realmente usado en cada pago se guarda aparte,
-- en payments.exchange_rate (inmutable, no depende de este log).

-- ---------- PAGOS ----------
CREATE TABLE payments (
    id                  SERIAL PRIMARY KEY,
    date                DATE NOT NULL,
    concept             TEXT NOT NULL,
    category            TEXT NOT NULL DEFAULT 'otro',
        -- 'importacion' | 'gasto_operativo' | 'impuesto' | 'logistica' | 'comision' | 'otro'
    currency_charged    TEXT NOT NULL,          -- 'ARS' o 'USD': en qué moneda se cargó originalmente
    amount_ars          NUMERIC(14,2) NOT NULL,
    amount_usd          NUMERIC(14,2) NOT NULL,
    exchange_rate       NUMERIC(12,4) NOT NULL, -- cotización usada, confirmada por el usuario al cargar
    exchange_rate_type  TEXT NOT NULL DEFAULT 'oficial',
    status              TEXT NOT NULL DEFAULT 'pagado', -- 'pagado' | 'pendiente' | 'parcial'
    notes               TEXT,
    created_by          TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- amount_ars y amount_usd NUNCA se recalculan después: son el valor
-- histórico real de ese pago, igual que una factura no cambia si
-- mañana cambia la cotización.

-- ---------- APORTES DE CADA SOCIO A UN PAGO ----------
-- Un mismo pago puede tener aportes de varios socios (por eso es
-- una tabla aparte y no dos columnas fijas "aporte1/aporte2").
CREATE TABLE payment_contributions (
    id                  SERIAL PRIMARY KEY,
    payment_id          INTEGER NOT NULL REFERENCES payments(id) ON DELETE CASCADE,
    partner_id          INTEGER NOT NULL REFERENCES partners(id),
    amount_ars          NUMERIC(14,2) NOT NULL,
    receipt_reference   TEXT,   -- nombre de archivo o link a Drive
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (payment_id, partner_id)
);

-- ---------- COMPRAS AL PROVEEDOR (IMPORTACIÓN) ----------
CREATE TABLE purchases (
    id                  SERIAL PRIMARY KEY,
    date                DATE NOT NULL,
    supplier            TEXT NOT NULL,
    invoice_number      TEXT,
    payment_id          INTEGER REFERENCES payments(id), -- pago que cubre esta compra (opcional)
    shipment_status     TEXT NOT NULL DEFAULT 'pendiente_pedido',
        -- 'pendiente_pedido' | 'en_fabrica' | 'en_transito' | 'en_aduana' | 'recibido'
    receipt_reference   TEXT,
    notes               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE purchase_items (
    id                  SERIAL PRIMARY KEY,
    purchase_id         INTEGER NOT NULL REFERENCES purchases(id) ON DELETE CASCADE,
    product_id          INTEGER REFERENCES products(id),  -- null hasta que carguen catálogo
    product_name        TEXT NOT NULL,   -- snapshot del nombre al momento de la compra
    quantity            NUMERIC(12,2) NOT NULL,
    unit_price_usd      NUMERIC(12,4) NOT NULL,
    total_usd           NUMERIC(14,2) GENERATED ALWAYS AS (quantity * unit_price_usd) STORED
);

-- ---------- CATÁLOGO DE PRODUCTOS (preparado para stock futuro) ----------
CREATE TABLE products (
    id            SERIAL PRIMARY KEY,
    sku           TEXT UNIQUE,
    name          TEXT NOT NULL,
    category      TEXT,
    active        BOOLEAN NOT NULL DEFAULT true,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Movimientos de inventario: no usar todavía si no cargan catálogo,
-- pero la tabla ya queda lista para cuando quieran controlar stock real.
CREATE TABLE inventory_movements (
    id              SERIAL PRIMARY KEY,
    product_id      INTEGER NOT NULL REFERENCES products(id),
    quantity_change INTEGER NOT NULL,   -- positivo = entrada, negativo = salida
    reason          TEXT NOT NULL,      -- 'compra' | 'venta' | 'ajuste'
    reference_type  TEXT,               -- 'purchase_item' | 'sale_item'
    reference_id    INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- VENTAS ----------
CREATE TABLE sales (
    id                  SERIAL PRIMARY KEY,
    date                DATE NOT NULL,
    customer            TEXT,
    channel             TEXT,            -- 'mayorista' | 'online' | 'local'
    payment_method      TEXT NOT NULL DEFAULT 'transferencia',
    status              TEXT NOT NULL DEFAULT 'cobrado', -- 'cobrado' | 'pendiente' | 'parcial'
    receipt_reference   TEXT,
    notes               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE sale_items (
    id                  SERIAL PRIMARY KEY,
    sale_id             INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
    product_id          INTEGER REFERENCES products(id),
    product_name        TEXT NOT NULL,   -- snapshot: si el catálogo cambia, esta venta no se altera
    quantity            NUMERIC(12,2) NOT NULL,
    unit_price_ars      NUMERIC(12,2) NOT NULL,
    total_ars           NUMERIC(14,2) GENERATED ALWAYS AS (quantity * unit_price_ars) STORED
);

-- ---------- DOCUMENTOS (referencia centralizada, opcional) ----------
-- Útil si más adelante quieren un buscador único de comprobantes
-- en vez de mirarlos tabla por tabla.
CREATE TABLE documents (
    id              SERIAL PRIMARY KEY,
    entity_type     TEXT NOT NULL,    -- 'payment' | 'purchase' | 'sale'
    entity_id       INTEGER NOT NULL,
    file_reference  TEXT NOT NULL,    -- nombre de archivo o link a Drive
    uploaded_by     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- AUDITORÍA (recomendado desde el día uno) ----------
CREATE TABLE audit_log (
    id              SERIAL PRIMARY KEY,
    table_name      TEXT NOT NULL,
    record_id       INTEGER NOT NULL,
    action          TEXT NOT NULL,    -- 'insert' | 'update' | 'delete'
    changed_by      TEXT,
    changed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    old_values      JSONB,
    new_values      JSONB
);

-- ---------- ÍNDICES BÁSICOS ----------
CREATE INDEX idx_payments_date ON payments(date);
CREATE INDEX idx_purchases_date ON purchases(date);
CREATE INDEX idx_sales_date ON sales(date);
CREATE INDEX idx_contributions_payment ON payment_contributions(payment_id);
CREATE INDEX idx_contributions_partner ON payment_contributions(partner_id);
