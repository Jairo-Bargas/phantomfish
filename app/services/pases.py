"""Pasadas por el puente a Colón: saldo entre socios, por moneda, sin conversión."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.money import ZERO, money
from app.models import PaseColon, Partner


@dataclass
class PaseSaldo:
    # Saldo neto que un socio le debe al otro por las pasadas, por moneda.
    # Positivo = el segundo socio (por id) le debe al primero.
    net_ars: Decimal = ZERO
    net_uyu: Decimal = ZERO
    acreedor: str | None = None  # a quién le deben (mismo para ambas monedas salvo raro)
    deudor: str | None = None
    total_ars: Decimal = ZERO   # gastado en pasadas (histórico)
    total_uyu: Decimal = ZERO
    count: int = 0
    count_mes: int = 0
    ultima: dt.date | None = None


def _month_start(today: dt.date | None = None) -> dt.date:
    return (today or dt.date.today()).replace(day=1)


def pase_saldo(db: Session, partners: list[Partner]) -> PaseSaldo:
    """Calcula quién le debe a quién por las pasadas (dos monedas, sin convertir).

    Regla: el socio que registró la pasada la pagó. El otro le debe su parte
    (según pct_share). Se netea entre los dos.
    """
    s = PaseSaldo()
    rows = list(db.scalars(select(PaseColon).order_by(PaseColon.date.desc(), PaseColon.id.desc())))
    s.count = len(rows)
    if not rows:
        return s

    s.ultima = rows[0].date
    m0 = _month_start()
    s.count_mes = sum(1 for r in rows if r.date >= m0)
    s.total_ars = money(sum((money(r.amount_ars) for r in rows), ZERO))
    s.total_uyu = money(sum((money(r.amount_uyu) for r in rows), ZERO))

    if len(partners) != 2:
        return s
    a, b = partners  # ordenados por id
    a_pct = Decimal(str(a.pct_share)) / Decimal(100)
    b_pct = Decimal(str(b.pct_share)) / Decimal(100)

    net_ars = ZERO
    net_uyu = ZERO
    for r in rows:
        if r.paid_by_partner_id == a.id:
            net_ars += money(r.amount_ars) * b_pct   # b le debe a a
            net_uyu += money(r.amount_uyu) * b_pct
        elif r.paid_by_partner_id == b.id:
            net_ars -= money(r.amount_ars) * a_pct   # a le debe a b
            net_uyu -= money(r.amount_uyu) * a_pct
    s.net_ars = money(net_ars)
    s.net_uyu = money(net_uyu)

    # dirección (usamos el que tenga saldo; si difieren por moneda es raro pero
    # se muestra el neto igual y el signo indica la dirección)
    ref = s.net_ars if s.net_ars != ZERO else s.net_uyu
    if ref > ZERO:
        s.acreedor, s.deudor = a.name, b.name
    elif ref < ZERO:
        s.acreedor, s.deudor = b.name, a.name
    return s
