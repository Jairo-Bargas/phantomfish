"""Migraciones aditivas y seguras para SQLite.

No hay Alembic: la app usa create_all() para las tablas nuevas. Este módulo se
encarga de las COLUMNAS nuevas en tablas que ya existen (create_all no las agrega).
Todo lo de acá es aditivo — nunca borra ni cambia datos existentes.
"""

from __future__ import annotations

from sqlalchemy import Engine, text

# (tabla, columna, definición SQL) — se agrega solo si falta.
_ADD_COLUMNS: list[tuple[str, str, str]] = [
    ("payments", "order_id", "INTEGER REFERENCES orders(id)"),
    ("purchases", "order_id", "INTEGER REFERENCES orders(id)"),
    ("partners", "is_owner", "INTEGER NOT NULL DEFAULT 0"),
    ("settlements", "currency", "TEXT NOT NULL DEFAULT 'ARS'"),
    ("settlements", "amount_original", "TEXT"),
    ("settlements", "exchange_rate", "TEXT"),
    ("settlements", "payment_id", "INTEGER REFERENCES payments(id)"),
]

# Se corren después de agregar columnas, solo si la columna acaba de aparecer.
# (tabla, sentencia) — completan valores de filas viejas.
_BACKFILL: list[tuple[str, str]] = [
    ("settlements", "UPDATE settlements SET amount_original = amount_ars WHERE amount_original IS NULL"),
    ("settlements", "UPDATE settlements SET exchange_rate = '1' WHERE exchange_rate IS NULL"),
    ("partners", "UPDATE partners SET is_owner = 1 WHERE lower(username) = 'jairo'"),
]


def _sqlite_columns(conn, table: str) -> set[str]:
    rows = conn.execute(text(f'PRAGMA table_info("{table}")')).fetchall()
    return {r[1] for r in rows}


def _table_exists(conn, table: str) -> bool:
    row = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:t"), {"t": table}
    ).fetchone()
    return row is not None


def run_migrations(engine: Engine) -> list[str]:
    """Devuelve la lista de cambios aplicados (para log)."""
    if engine.dialect.name != "sqlite":
        return []
    applied: list[str] = []
    touched: set[str] = set()
    with engine.begin() as conn:
        for table, column, ddl in _ADD_COLUMNS:
            if not _table_exists(conn, table):
                continue
            if column in _sqlite_columns(conn, table):
                continue
            conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN {column} {ddl}'))
            applied.append(f"{table}.{column}")
            touched.add(table)

        for table, stmt in _BACKFILL:
            if table in touched:
                conn.execute(text(stmt))
    return applied
