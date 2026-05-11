"""
Inicialización de la base de datos.

Uso:
    # Crear todas las tablas (dev/test)
    python -m db.init_db

    # O desde código:
    from db.init_db import init_db, seed_demo_data
    init_db()
    seed_demo_data()   # opcional: datos de prueba
"""

import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.models import Base
from db.session import engine, db_session, ping
from db.repository import ProductRepository, PriceHistoryRepository, MonitoredUrlRepository

logger = logging.getLogger(__name__)


def init_db(drop_first: bool = False) -> None:
    """
    Crea todas las tablas definidas en los modelos.

    Args:
        drop_first: Si True, elimina todas las tablas antes de crearlas.
                    ¡PELIGROSO en producción! Solo para tests/dev.
    """
    if not ping():
        raise RuntimeError("No se puede conectar a la base de datos.")

    if drop_first:
        logger.warning("[init_db] Dropping all tables...")
        Base.metadata.drop_all(engine)

    logger.info("[init_db] Creating tables...")
    Base.metadata.create_all(engine)
    logger.info("[init_db] ✓ Tables created successfully")


def seed_demo_data() -> None:
    """
    Inserta datos de prueba para desarrollo.
    Simula 3 productos con historial de precios.
    """
    from datetime import datetime, timezone, timedelta
    from db.models import Product, PriceHistory, MonitoredUrl
    from db.price_detector import PriceChangeDetector

    logger.info("[seed] Inserting demo data...")

    demo_products = [
        {
            "url": "https://www.mercadolibre.com.do/laptop-hp-15/MLM-111111",
            "store": "MercadoLibre",
            "sku": "MLM-111111",
            "name": "Laptop HP 15-dw3003la Core i5 8GB 256GB SSD",
            "name_normalized": "laptop hp 15 dw3003la core i5 8gb 256gb ssd",
            "brand": "HP",
            "category": "Computación > Laptops",
            "current_price": 42500.0,
            "current_currency": "DOP",
            "current_original_price": 48000.0,
            "current_discount_pct": 11.5,
            "is_on_sale": True,
            "in_stock": True,
            "image_url": "https://http2.mlstatic.com/D_NQ_NP_dummy.jpg",
            "prices": [48000, 46500, 45000, 43000, 42500],  # historial simulado
        },
        {
            "url": "https://www.mercadolibre.com.do/samsung-galaxy-a54/MLM-222222",
            "store": "MercadoLibre",
            "sku": "MLM-222222",
            "name": "Samsung Galaxy A54 5G 128GB 6GB RAM",
            "name_normalized": "samsung galaxy a54 5g 128gb 6gb ram",
            "brand": "Samsung",
            "category": "Celulares > Smartphones",
            "current_price": 18900.0,
            "current_currency": "DOP",
            "current_original_price": None,
            "current_discount_pct": None,
            "is_on_sale": False,
            "in_stock": True,
            "prices": [19500, 19500, 19200, 19000, 18900],
        },
        {
            "url": "https://www.mercadolibre.com.do/monitor-lg-27/MLM-333333",
            "store": "MercadoLibre",
            "sku": "MLM-333333",
            "name": "Monitor LG 27\" Full HD IPS 75Hz",
            "name_normalized": "monitor lg 27 full hd ips 75hz",
            "brand": "LG",
            "category": "Computación > Monitores",
            "current_price": 15800.0,
            "current_currency": "DOP",
            "current_original_price": 18500.0,
            "current_discount_pct": 14.6,
            "is_on_sale": True,
            "in_stock": False,  # agotado
            "prices": [18500, 17800, 16500, 15800, 15800],
        },
    ]

    with db_session() as db:
        for i, data in enumerate(demo_products):
            # Verificar si ya existe
            from sqlalchemy import select
            existing = db.query(Product).filter(Product.url == data["url"]).first()
            if existing:
                logger.info(f"[seed] Product already exists: {data['name'][:40]}")
                continue

            prices = data.pop("prices")

            product = Product(**data)
            product.last_scraped_at = datetime.now(timezone.utc)
            db.add(product)
            db.flush()

            # Insertar historial de precios (simulando scrapes diarios)
            for j, price in enumerate(prices):
                days_ago = len(prices) - j - 1
                scraped_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
                history = PriceHistory(
                    product_id=product.id,
                    price=price,
                    currency=product.current_currency,
                    in_stock=product.in_stock if j == len(prices) - 1 else True,
                    scraped_at=scraped_at,
                    spider_name="seed",
                )
                db.add(history)

            # Agregar URL a monitored_urls
            monitored = MonitoredUrl(
                url=product.url,
                store=product.store,
                label=product.name[:80],
                product_id=product.id,
                is_active=True,
                scrape_interval_hours=6,
                next_scrape_at=datetime.now(timezone.utc),
            )
            db.add(monitored)

            logger.info(f"[seed] ✓ {product.name[:50]} ({len(prices)} price records)")

    logger.info("[seed] Demo data inserted successfully")


if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Inicializar la base de datos")
    parser.add_argument("--drop", action="store_true", help="Drop y recrear todas las tablas")
    parser.add_argument("--seed", action="store_true", help="Insertar datos de prueba")
    args = parser.parse_args()

    init_db(drop_first=args.drop)

    if args.seed:
        seed_demo_data()

    print("\n✓ Base de datos lista")
    print(f"  DB URL: {os.getenv('DATABASE_URL', 'sqlite:///./price_intelligence.db')}")
