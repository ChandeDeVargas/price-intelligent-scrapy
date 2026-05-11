"""
db — capa de persistencia.

Exports:
    Modelos ORM:
        Product, PriceHistory, MonitoredUrl, PriceAlert

    Sesión:
        engine, SessionLocal, get_db, db_session

    Repositorios:
        ProductRepository, PriceHistoryRepository,
        MonitoredUrlRepository, PriceAlertRepository

    Detector:
        PriceChangeDetector, ChangeResult, ChangeType

    Init:
        init_db, seed_demo_data
"""

from .models import Product, PriceHistory, MonitoredUrl, PriceAlert
from .session import engine, SessionLocal, get_db, db_session, ping
from .repository import (
    ProductRepository,
    PriceHistoryRepository,
    MonitoredUrlRepository,
    PriceAlertRepository,
)
from .price_detector import PriceChangeDetector, ChangeResult, ChangeType
from .init_db import init_db, seed_demo_data

__all__ = [
    # Models
    "Product", "PriceHistory", "MonitoredUrl", "PriceAlert",
    # Session
    "engine", "SessionLocal", "get_db", "db_session", "ping",
    # Repositories
    "ProductRepository", "PriceHistoryRepository",
    "MonitoredUrlRepository", "PriceAlertRepository",
    # Detector
    "PriceChangeDetector", "ChangeResult", "ChangeType",
    # Init
    "init_db", "seed_demo_data",
]
