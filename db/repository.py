"""
Repository — capa de acceso a datos.

Centraliza todas las queries para que los spiders, la API y el engine
no hagan SQL directamente. Cada método es una operación atómica.

Uso:
    from db.repository import ProductRepository, PriceHistoryRepository
    from db.session import db_session

    with db_session() as db:
        repo = ProductRepository(db)
        product = repo.upsert_from_parsed(parsed_product)
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import desc, func, and_
from sqlalchemy.orm import Session

from .models import Product, PriceHistory, MonitoredUrl, PriceAlert

logger = logging.getLogger(__name__)


# ── Product Repository ────────────────────────────────────────────────────────

class ProductRepository:
    """CRUD y queries de negocio para la tabla products."""

    def __init__(self, db: Session):
        self.db = db

    # ── Upsert (operación principal del spider) ───────────────────────────────

    def upsert_from_parsed(self, parsed) -> Product:
        """
        Crea o actualiza un Product a partir de un ParsedProduct (Day 2).

        Si el producto ya existe (por URL), actualiza sus campos.
        Si es nuevo, lo crea.
        En ambos casos, inserta un registro en price_history.

        Args:
            parsed: ParsedProduct del parser del Day 2

        Returns:
            Product (creado o actualizado)
        """
        product = self.get_by_url(parsed.url)

        if product is None:
            product = self._create(parsed)
            logger.info(f"[repo] NEW product: {product.name[:50]} | {parsed.price} {parsed.currency}")
        else:
            self._update_snapshot(product, parsed)
            logger.info(f"[repo] UPD product: {product.name[:50]} | {parsed.price} {parsed.currency}")

        self.db.flush()  # genera product.id sin commitear
        return product

    def _create(self, parsed) -> Product:
        product = Product(
            url=parsed.url,
            store=parsed.store,
            sku=parsed.sku,
            name=parsed.name,
            name_normalized=parsed.name_normalized,
            brand=parsed.brand,
            category=parsed.category,
            description=parsed.description,
            image_url=parsed.image_url,
            specs=parsed.specs or {},
            current_price=parsed.price,
            current_currency=parsed.currency,
            current_original_price=parsed.original_price,
            current_discount_pct=parsed.discount_pct,
            is_on_sale=parsed.is_on_sale,
            in_stock=parsed.in_stock,
            seller_name=parsed.seller_name,
            last_scraped_at=datetime.now(timezone.utc),
        )
        self.db.add(product)
        return product

    def _update_snapshot(self, product: Product, parsed) -> None:
        """Actualiza el snapshot de precio actual en el Product."""
        product.current_price = parsed.price
        product.current_currency = parsed.currency
        product.current_original_price = parsed.original_price
        product.current_discount_pct = parsed.discount_pct
        product.is_on_sale = parsed.is_on_sale
        product.in_stock = parsed.in_stock
        product.last_scraped_at = datetime.now(timezone.utc)
        # Actualizar campos de producto si cambiaron
        if parsed.name:
            product.name = parsed.name
            product.name_normalized = parsed.name_normalized
        if parsed.brand:
            product.brand = parsed.brand
        if parsed.image_url:
            product.image_url = parsed.image_url
        if parsed.description:
            product.description = parsed.description
        if parsed.specs:
            product.specs = parsed.specs
        if parsed.seller_name:
            product.seller_name = parsed.seller_name

    # ── Queries ───────────────────────────────────────────────────────────────

    def get_by_id(self, product_id: int) -> Optional[Product]:
        return self.db.query(Product).filter(Product.id == product_id).first()

    def get_by_url(self, url: str) -> Optional[Product]:
        return self.db.query(Product).filter(Product.url == url).first()

    def list_all(self, store: str | None = None, in_stock: bool | None = None,
                 skip: int = 0, limit: int = 100) -> list[Product]:
        q = self.db.query(Product)
        if store:
            q = q.filter(Product.store == store)
        if in_stock is not None:
            q = q.filter(Product.in_stock == in_stock)
        return q.order_by(desc(Product.last_scraped_at)).offset(skip).limit(limit).all()

    def list_on_sale(self, min_discount: float = 0.0) -> list[Product]:
        return (
            self.db.query(Product)
            .filter(
                Product.is_on_sale == True,
                Product.current_discount_pct >= min_discount,
            )
            .order_by(desc(Product.current_discount_pct))
            .all()
        )

    def search(self, query: str, limit: int = 20) -> list[Product]:
        pattern = f"%{query.lower()}%"
        return (
            self.db.query(Product)
            .filter(Product.name_normalized.like(pattern))
            .limit(limit)
            .all()
        )

    def count(self, store: str | None = None) -> int:
        q = self.db.query(func.count(Product.id))
        if store:
            q = q.filter(Product.store == store)
        return q.scalar()

    def delete(self, product_id: int) -> bool:
        product = self.get_by_id(product_id)
        if not product:
            return False
        self.db.delete(product)
        return True

    def set_alert_threshold(self, product_id: int, threshold_pct: float) -> Optional[Product]:
        product = self.get_by_id(product_id)
        if product:
            product.alert_threshold_pct = threshold_pct
        return product


# ── PriceHistory Repository ───────────────────────────────────────────────────

class PriceHistoryRepository:
    """Operaciones sobre la tabla price_history (append-only)."""

    def __init__(self, db: Session):
        self.db = db

    def add(self, product_id: int, parsed, spider_name: str | None = None) -> PriceHistory:
        """
        Inserta un nuevo registro de precio.
        Siempre se inserta — nunca se actualiza un registro existente.
        """
        record = PriceHistory(
            product_id=product_id,
            price=parsed.price,
            original_price=parsed.original_price,
            currency=parsed.currency,
            discount_pct=parsed.discount_pct,
            is_on_sale=parsed.is_on_sale,
            in_stock=parsed.in_stock,
            stock_qty=getattr(parsed, "stock_qty", None),
            spider_name=spider_name,
            scraped_at=datetime.now(timezone.utc),
        )
        self.db.add(record)
        self.db.flush()
        return record

    def get_history(
        self,
        product_id: int,
        limit: int = 90,
        since: datetime | None = None,
    ) -> list[PriceHistory]:
        """Retorna el historial de precios ordenado del más reciente al más antiguo."""
        q = (
            self.db.query(PriceHistory)
            .filter(PriceHistory.product_id == product_id)
        )
        if since:
            q = q.filter(PriceHistory.scraped_at >= since)
        return q.order_by(desc(PriceHistory.scraped_at)).limit(limit).all()

    def get_latest(self, product_id: int) -> Optional[PriceHistory]:
        """El precio más reciente de un producto."""
        return (
            self.db.query(PriceHistory)
            .filter(PriceHistory.product_id == product_id)
            .order_by(desc(PriceHistory.scraped_at))
            .first()
        )

    def get_previous(self, product_id: int) -> Optional[PriceHistory]:
        """
        El precio anterior al más reciente.
        Útil para detectar si el precio cambió en el último scrape.
        """
        return (
            self.db.query(PriceHistory)
            .filter(PriceHistory.product_id == product_id)
            .order_by(desc(PriceHistory.scraped_at))
            .offset(1)
            .first()
        )

    def get_min_price(self, product_id: int) -> Optional[float]:
        """Precio mínimo histórico."""
        result = (
            self.db.query(func.min(PriceHistory.price))
            .filter(PriceHistory.product_id == product_id)
            .scalar()
        )
        return float(result) if result else None

    def get_max_price(self, product_id: int) -> Optional[float]:
        """Precio máximo histórico."""
        result = (
            self.db.query(func.max(PriceHistory.price))
            .filter(PriceHistory.product_id == product_id)
            .scalar()
        )
        return float(result) if result else None

    def get_avg_price(self, product_id: int, days: int = 30) -> Optional[float]:
        """Precio promedio en los últimos N días."""
        since = datetime.now(timezone.utc) - timedelta(days=days)
        result = (
            self.db.query(func.avg(PriceHistory.price))
            .filter(
                PriceHistory.product_id == product_id,
                PriceHistory.scraped_at >= since,
            )
            .scalar()
        )
        return round(float(result), 2) if result else None

    def count_scrapes(self, product_id: int) -> int:
        return (
            self.db.query(func.count(PriceHistory.id))
            .filter(PriceHistory.product_id == product_id)
            .scalar()
        )


# ── MonitoredUrl Repository ───────────────────────────────────────────────────

class MonitoredUrlRepository:
    """CRUD para URLs monitoreadas."""

    def __init__(self, db: Session):
        self.db = db

    def add(self, url: str, store: str | None = None, label: str | None = None,
            interval_hours: int = 6) -> MonitoredUrl:
        existing = self.get_by_url(url)
        if existing:
            return existing

        record = MonitoredUrl(
            url=url,
            store=store,
            label=label,
            scrape_interval_hours=interval_hours,
            next_scrape_at=datetime.now(timezone.utc),
        )
        self.db.add(record)
        self.db.flush()
        return record

    def get_by_url(self, url: str) -> Optional[MonitoredUrl]:
        return self.db.query(MonitoredUrl).filter(MonitoredUrl.url == url).first()

    def get_due(self) -> list[MonitoredUrl]:
        """Retorna URLs que deben ser scrapeadas ahora."""
        now = datetime.now(timezone.utc)
        return (
            self.db.query(MonitoredUrl)
            .filter(
                MonitoredUrl.is_active == True,
                MonitoredUrl.consecutive_errors < 5,
                (MonitoredUrl.next_scrape_at == None)
                | (MonitoredUrl.next_scrape_at <= now),
            )
            .all()
        )

    def mark_scraped(self, url_id: int, success: bool = True) -> None:
        record = self.db.query(MonitoredUrl).filter(MonitoredUrl.id == url_id).first()
        if not record:
            return
        now = datetime.now(timezone.utc)
        record.last_scraped_at = now
        if success:
            record.consecutive_errors = 0
            record.next_scrape_at = now + timedelta(hours=record.scrape_interval_hours)
        else:
            record.consecutive_errors += 1
            # Backoff exponencial: 1h, 2h, 4h, 8h, max 24h
            backoff = min(2 ** record.consecutive_errors, 24)
            record.next_scrape_at = now + timedelta(hours=backoff)

    def list_all(self, active_only: bool = False) -> list[MonitoredUrl]:
        q = self.db.query(MonitoredUrl)
        if active_only:
            q = q.filter(MonitoredUrl.is_active == True)
        return q.order_by(MonitoredUrl.created_at.desc()).all()

    def deactivate(self, url_id: int) -> bool:
        record = self.db.query(MonitoredUrl).filter(MonitoredUrl.id == url_id).first()
        if record:
            record.is_active = False
            return True
        return False


# ── PriceAlert Repository ─────────────────────────────────────────────────────

class PriceAlertRepository:
    """CRUD y queries para alertas de precio."""

    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        product_id: int,
        alert_type: str,
        message: str,
        old_price: float | None = None,
        new_price: float | None = None,
        change_pct: float | None = None,
        currency: str = "USD",
    ) -> PriceAlert:
        alert = PriceAlert(
            product_id=product_id,
            alert_type=alert_type,
            message=message,
            old_price=old_price,
            new_price=new_price,
            change_pct=change_pct,
            currency=currency,
        )
        self.db.add(alert)
        self.db.flush()
        return alert

    def get_pending(self) -> list[PriceAlert]:
        """Alertas que aún no han sido notificadas (para el Day 6)."""
        return (
            self.db.query(PriceAlert)
            .filter(PriceAlert.is_notified == False)
            .order_by(PriceAlert.created_at.asc())
            .all()
        )

    def mark_notified(self, alert_id: int) -> None:
        alert = self.db.query(PriceAlert).filter(PriceAlert.id == alert_id).first()
        if alert:
            alert.is_notified = True
            alert.notified_at = datetime.now(timezone.utc)

    def list_for_product(self, product_id: int, limit: int = 20) -> list[PriceAlert]:
        return (
            self.db.query(PriceAlert)
            .filter(PriceAlert.product_id == product_id)
            .order_by(desc(PriceAlert.created_at))
            .limit(limit)
            .all()
        )

    def list_recent(self, hours: int = 24, limit: int = 50) -> list[PriceAlert]:
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        return (
            self.db.query(PriceAlert)
            .filter(PriceAlert.created_at >= since)
            .order_by(desc(PriceAlert.created_at))
            .limit(limit)
            .all()
        )
