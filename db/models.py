"""
Modelos ORM — SQLAlchemy 2.0 (mapped_column / DeclarativeBase).

Tablas:
    products          — catálogo de productos únicos
    price_history     — cada precio scrapeado (append-only, nunca se borra)
    monitored_urls    — URLs que el scheduler debe revisar
    price_alerts      — alertas generadas por el engine (Día 5)

Relaciones:
    Product  1 ──< PriceHistory
    Product  1 ──< PriceAlert
    MonitoredUrl 1 ── 1 Product (opcional, se linkea tras el primer scrape)
"""

import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey,
    Integer, String, Text, JSON,
    UniqueConstraint, Index,
)
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, mapped_column,
    relationship, validates,
)


# ── Base ──────────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    """Base class para todos los modelos."""
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Product ───────────────────────────────────────────────────────────────────

class Product(Base):
    """
    Catálogo de productos únicos.

    Un producto se identifica por (url, store).
    El precio actual siempre se puede obtener vía la relación
    price_history ordenada por scraped_at DESC.
    """
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("url", name="uq_product_url"),
        Index("ix_product_store", "store"),
        Index("ix_product_name_normalized", "name_normalized"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Identifiers
    url: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True)
    store: Mapped[str] = mapped_column(String(100), nullable=False)
    sku: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Product info
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    name_normalized: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    brand: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    specs: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=dict)

    # Current price snapshot (desnormalizado para queries rápidas)
    current_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    current_currency: Mapped[str] = mapped_column(String(10), default="USD")
    current_original_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    current_discount_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_on_sale: Mapped[bool] = mapped_column(Boolean, default=False)
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True)

    # Seller
    seller_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Alert threshold (null = usa el default global de settings)
    alert_threshold_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Timestamps
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now
    )
    last_scraped_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    # Relationships
    price_history: Mapped[list["PriceHistory"]] = relationship(
        "PriceHistory",
        back_populates="product",
        order_by="PriceHistory.scraped_at.desc()",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    alerts: Mapped[list["PriceAlert"]] = relationship(
        "PriceAlert",
        back_populates="product",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    def __repr__(self) -> str:
        return f"<Product id={self.id} store={self.store!r} name={self.name[:40]!r}>"

    @property
    def latest_price(self) -> Optional["PriceHistory"]:
        """Retorna el registro de precio más reciente."""
        return self.price_history.order_by(  # type: ignore[union-attr]
            PriceHistory.scraped_at.desc()
        ).first()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "url": self.url,
            "store": self.store,
            "sku": self.sku,
            "name": self.name,
            "brand": self.brand,
            "category": self.category,
            "image_url": self.image_url,
            "current_price": self.current_price,
            "current_currency": self.current_currency,
            "current_original_price": self.current_original_price,
            "current_discount_pct": self.current_discount_pct,
            "is_on_sale": self.is_on_sale,
            "in_stock": self.in_stock,
            "seller_name": self.seller_name,
            "alert_threshold_pct": self.alert_threshold_pct,
            "first_seen_at": self.first_seen_at.isoformat() if self.first_seen_at else None,
            "last_scraped_at": self.last_scraped_at.isoformat() if self.last_scraped_at else None,
        }


# ── PriceHistory ──────────────────────────────────────────────────────────────

class PriceHistory(Base):
    """
    Historial de precios — append-only.

    Cada vez que el spider scrapea un producto, se inserta un registro aquí.
    NUNCA se actualiza ni borra un registro existente.
    Esta es la fuente de verdad para el engine de detección de cambios.
    """
    __tablename__ = "price_history"
    __table_args__ = (
        Index("ix_price_history_product_scraped", "product_id", "scraped_at"),
        Index("ix_price_history_scraped_at", "scraped_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )

    # Precio en este momento
    price: Mapped[float] = mapped_column(Float, nullable=False)
    original_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    discount_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_on_sale: Mapped[bool] = mapped_column(Boolean, default=False)

    # Disponibilidad en este momento
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True)
    stock_qty: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Origen del scrape
    spider_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Cuándo se scrapeó
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    # Relationship
    product: Mapped["Product"] = relationship("Product", back_populates="price_history")

    def __repr__(self) -> str:
        return (
            f"<PriceHistory product_id={self.product_id} "
            f"price={self.price} at={self.scraped_at}>"
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "product_id": self.product_id,
            "price": self.price,
            "original_price": self.original_price,
            "currency": self.currency,
            "discount_pct": self.discount_pct,
            "is_on_sale": self.is_on_sale,
            "in_stock": self.in_stock,
            "stock_qty": self.stock_qty,
            "spider_name": self.spider_name,
            "scraped_at": self.scraped_at.isoformat() if self.scraped_at else None,
        }


# ── MonitoredUrl ──────────────────────────────────────────────────────────────

class MonitoredUrl(Base):
    """
    URLs que el scheduler debe revisar periódicamente.

    Cuando se agrega una URL aquí, el scheduler la scrapea
    según el intervalo configurado y linkea el resultado a un Product.
    """
    __tablename__ = "monitored_urls"
    __table_args__ = (
        UniqueConstraint("url", name="uq_monitored_url"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True)
    store: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    label: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Link al producto (se llena tras el primer scrape)
    product_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )

    # Scheduling
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    scrape_interval_hours: Mapped[int] = mapped_column(Integer, default=6)
    last_scraped_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_scrape_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    consecutive_errors: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    def __repr__(self) -> str:
        return f"<MonitoredUrl id={self.id} url={self.url[:60]!r} active={self.is_active}>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "url": self.url,
            "store": self.store,
            "label": self.label,
            "product_id": self.product_id,
            "is_active": self.is_active,
            "scrape_interval_hours": self.scrape_interval_hours,
            "last_scraped_at": self.last_scraped_at.isoformat() if self.last_scraped_at else None,
            "next_scrape_at": self.next_scrape_at.isoformat() if self.next_scrape_at else None,
            "consecutive_errors": self.consecutive_errors,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ── PriceAlert ────────────────────────────────────────────────────────────────

class PriceAlert(Base):
    """
    Alertas de cambio de precio generadas por el engine (Día 5).

    Cada vez que se detecta un cambio relevante, se crea un registro aquí.
    El notifier (Día 6) lee alertas no notificadas y envía el mensaje.
    """
    __tablename__ = "price_alerts"
    __table_args__ = (
        Index("ix_price_alerts_product_created", "product_id", "created_at"),
        Index("ix_price_alerts_notified", "is_notified"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )

    # Tipo de alerta
    alert_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )
    # Valores: "price_drop", "price_rise", "back_in_stock",
    #          "out_of_stock", "new_low", "new_high"

    # Precios involucrados
    old_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    new_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    change_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="USD")

    # Mensaje legible
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Estado de notificación
    is_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    notified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    # Relationship
    product: Mapped["Product"] = relationship("Product", back_populates="alerts")

    def __repr__(self) -> str:
        return (
            f"<PriceAlert type={self.alert_type!r} "
            f"product_id={self.product_id} change={self.change_pct}%>"
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "product_id": self.product_id,
            "alert_type": self.alert_type,
            "old_price": self.old_price,
            "new_price": self.new_price,
            "change_pct": self.change_pct,
            "currency": self.currency,
            "message": self.message,
            "is_notified": self.is_notified,
            "notified_at": self.notified_at.isoformat() if self.notified_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
