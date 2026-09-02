"""Modelo de datos (SQLAlchemy 2.0).

Sigue el esquema de ESQUEMA_BASE_DATOS.md / schema.sql con dos ajustes:
- nombres reales de socios en vez de "Socio1/Socio2";
- los aportes son filas (payment_contributions), no columnas fijas.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.money import Money, Rate, dsum, money


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Partner(Base):
    __tablename__ = "partners"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    pct_share: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    username: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Administrador: puede eliminar registros (pagos, pedidos, ventas, etc.).
    is_owner: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    contributions: Mapped[list["PaymentContribution"]] = relationship(back_populates="partner")


class Category(Base):
    """Categorías de pagos, editables por el usuario desde la app."""

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Order(Base):
    """Pedido de importación: agrupa sus pagos y sus compras para calcular
    el costo real por señuelo y el precio de venta sugerido."""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[int] = mapped_column(Integer, nullable=False)  # "Pedido N°{number}"
    title: Mapped[str | None] = mapped_column(String(160))
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="abierto")
    markup_pct: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False, default=Decimal(150))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    payments: Mapped[list["Payment"]] = relationship(
        back_populates="order", order_by="Payment.date, Payment.id"
    )
    purchases: Mapped[list["Purchase"]] = relationship(
        back_populates="order", order_by="Purchase.date, Purchase.id"
    )

    @property
    def display_name(self) -> str:
        base = f"Pedido N°{self.number}"
        return f"{base} — {self.title}" if self.title else base


class ExchangeRateLog(Base):
    __tablename__ = "exchange_rate_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    rate_type: Mapped[str] = mapped_column(String(20), nullable=False, default="oficial")
    buy: Mapped[Decimal | None] = mapped_column(Rate())
    sell: Mapped[Decimal | None] = mapped_column(Rate())
    source: Mapped[str] = mapped_column(String(60), nullable=False, default="dolarapi.com")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    concept: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False, default="otro")

    currency_charged: Mapped[str] = mapped_column(String(3), nullable=False)  # ARS | USD
    amount_original: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    exchange_rate: Mapped[Decimal] = mapped_column(Rate(), nullable=False)
    exchange_rate_type: Mapped[str] = mapped_column(String(20), nullable=False, default="oficial")

    # Congelados: nunca se recalculan después de guardar.
    amount_ars: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    amount_usd: Mapped[Decimal] = mapped_column(Money(), nullable=False)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pagado")
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    order: Mapped["Order | None"] = relationship(back_populates="payments")
    contributions: Mapped[list["PaymentContribution"]] = relationship(
        back_populates="payment",
        cascade="all, delete-orphan",
        order_by="PaymentContribution.id",
    )
    purchases: Mapped[list["Purchase"]] = relationship(back_populates="payment")
    documents: Mapped[list["Document"]] = relationship(
        primaryjoin="and_(foreign(Document.entity_id)==Payment.id, "
        "Document.entity_type=='payment')",
        viewonly=True,
        order_by="Document.id",
    )

    @property
    def contributed_total(self) -> Decimal:
        return dsum(c.amount_ars for c in self.contributions)

    @property
    def control_difference(self) -> Decimal:
        """amount_ars - suma de aportes. 0 => cargado correcto."""
        return money(self.amount_ars - self.contributed_total)

    @property
    def control_ok(self) -> bool:
        return abs(self.control_difference) <= Decimal("0.01")


class PaymentContribution(Base):
    __tablename__ = "payment_contributions"
    __table_args__ = (UniqueConstraint("payment_id", "partner_id", name="uq_contribution"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[int] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE"), nullable=False
    )
    partner_id: Mapped[int] = mapped_column(ForeignKey("partners.id"), nullable=False)
    amount_ars: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    receipt_reference: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    payment: Mapped["Payment"] = relationship(back_populates="contributions")
    partner: Mapped["Partner"] = relationship(back_populates="contributions")

    @property
    def should_contribute(self) -> Decimal:
        """Lo que le correspondía poner a este socio en este pago (según su %)."""
        pct = Decimal(str(self.partner.pct_share)) if self.partner else Decimal(0)
        return money(Decimal(str(self.payment.amount_ars)) * pct / Decimal(100))

    @property
    def contribution_diff(self) -> Decimal:
        """aportó - le correspondía. Positivo = puso de más; negativo = puso de menos."""
        return money(Decimal(str(self.amount_ars)) - self.should_contribute)


class Purchase(Base):
    __tablename__ = "purchases"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    supplier: Mapped[str] = mapped_column(String(160), nullable=False)
    invoice_number: Mapped[str | None] = mapped_column(String(80))
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id"))
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    shipment_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pendiente_pedido"
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    payment: Mapped["Payment | None"] = relationship(back_populates="purchases")
    order: Mapped["Order | None"] = relationship(back_populates="purchases")
    items: Mapped[list["PurchaseItem"]] = relationship(
        back_populates="purchase", cascade="all, delete-orphan", order_by="PurchaseItem.id"
    )
    documents: Mapped[list["Document"]] = relationship(
        primaryjoin="and_(foreign(Document.entity_id)==Purchase.id, "
        "Document.entity_type=='purchase')",
        viewonly=True,
        order_by="Document.id",
    )

    @property
    def total_usd(self) -> Decimal:
        return dsum(i.total_usd for i in self.items)


class PurchaseItem(Base):
    __tablename__ = "purchase_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_id: Mapped[int] = mapped_column(
        ForeignKey("purchases.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"))
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    unit_price_usd: Mapped[Decimal] = mapped_column(Money(), nullable=False)

    purchase: Mapped["Purchase"] = relationship(back_populates="items")
    product: Mapped["Product | None"] = relationship()

    @property
    def total_usd(self) -> Decimal:
        return money(Decimal(str(self.quantity)) * Decimal(str(self.unit_price_usd)))


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str | None] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str | None] = mapped_column(String(80))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    quantity_change: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(20), nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(20))
    reference_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Sale(Base):
    __tablename__ = "sales"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    customer: Mapped[str | None] = mapped_column(String(160))
    channel: Mapped[str | None] = mapped_column(String(20))
    payment_method: Mapped[str] = mapped_column(String(20), nullable=False, default="transferencia")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="cobrado")
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    items: Mapped[list["SaleItem"]] = relationship(
        back_populates="sale", cascade="all, delete-orphan", order_by="SaleItem.id"
    )
    documents: Mapped[list["Document"]] = relationship(
        primaryjoin="and_(foreign(Document.entity_id)==Sale.id, Document.entity_type=='sale')",
        viewonly=True,
        order_by="Document.id",
    )

    @property
    def total_ars(self) -> Decimal:
        return dsum(i.total_ars for i in self.items)


class SaleItem(Base):
    __tablename__ = "sale_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"))
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    unit_price_ars: Mapped[Decimal] = mapped_column(Money(), nullable=False)

    sale: Mapped["Sale"] = relationship(back_populates="items")
    product: Mapped["Product | None"] = relationship()

    @property
    def total_ars(self) -> Decimal:
        return money(Decimal(str(self.quantity)) * Decimal(str(self.unit_price_ars)))


class Settlement(Base):
    """Movimiento de plata entre socios (uno le devuelve/paga su parte al otro).

    No es un costo de la empresa: es la cuenta corriente entre socios. Se descuenta
    del 'saldo por aportes' que muestra el tablero.
    """

    __tablename__ = "settlements"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    from_partner_id: Mapped[int] = mapped_column(ForeignKey("partners.id"), nullable=False)
    to_partner_id: Mapped[int] = mapped_column(ForeignKey("partners.id"), nullable=False)
    # En qué moneda se pagó y cuánto (congelado). amount_ars es el valor convertido.
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="ARS")
    amount_original: Mapped[Decimal] = mapped_column(Money(), nullable=False, default=Decimal(0))
    exchange_rate: Mapped[Decimal] = mapped_column(Rate(), nullable=False, default=Decimal(1))
    amount_ars: Mapped[Decimal] = mapped_column(Money(), nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False, default="transferencia")
    # Vínculo opcional a un pago (solo informativo, no afecta cálculos).
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id", ondelete="SET NULL"))
    concept: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    from_partner: Mapped["Partner"] = relationship(foreign_keys=[from_partner_id])
    to_partner: Mapped["Partner"] = relationship(foreign_keys=[to_partner_id])
    documents: Mapped[list["Document"]] = relationship(
        primaryjoin="and_(foreign(Document.entity_id)==Settlement.id, "
        "Document.entity_type=='settlement')",
        viewonly=True,
        order_by="Document.id",
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)  # payment|purchase|sale|settlement
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    file_reference: Mapped[str] = mapped_column(String(400), nullable=False)  # ruta relativa
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(120))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    uploaded_by: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    table_name: Mapped[str] = mapped_column(String(60), nullable=False)
    record_id: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(10), nullable=False)  # insert|update|delete
    changed_by: Mapped[str | None] = mapped_column(String(60))
    changed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    summary: Mapped[str | None] = mapped_column(Text)
    old_values: Mapped[str | None] = mapped_column(Text)  # JSON
    new_values: Mapped[str | None] = mapped_column(Text)  # JSON


__all__ = [
    "AuditLog",
    "Category",
    "Document",
    "ExchangeRateLog",
    "InventoryMovement",
    "Order",
    "Partner",
    "Payment",
    "PaymentContribution",
    "Product",
    "Purchase",
    "PurchaseItem",
    "Sale",
    "SaleItem",
    "Settlement",
]
