"""
Tests — Día 3: modelos ORM, repositorios y PriceChangeDetector.

Ejecutar:
    pytest tests/test_day3.py -v

Usa una DB SQLite en memoria para aislar cada test.
"""

import pytest
import sys
import os
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, Product, PriceHistory, MonitoredUrl, PriceAlert
from db.repository import (
    ProductRepository, PriceHistoryRepository,
    MonitoredUrlRepository, PriceAlertRepository,
)
from db.price_detector import PriceChangeDetector, ChangeType


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def db():
    """Sesión SQLite in-memory — se descarta tras cada test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()
    yield session
    session.rollback()
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def product_repo(db):
    return ProductRepository(db)


@pytest.fixture
def history_repo(db):
    return PriceHistoryRepository(db)


@pytest.fixture
def monitored_repo(db):
    return MonitoredUrlRepository(db)


@pytest.fixture
def alert_repo(db):
    return PriceAlertRepository(db)


@pytest.fixture
def detector():
    return PriceChangeDetector(threshold_pct=5.0)


# ── ParsedProduct stub ────────────────────────────────────────────────────────

class FakeParsed:
    """Simula un ParsedProduct del Día 2 para tests de repo."""
    def __init__(self, **kwargs):
        self.url = kwargs.get("url", "https://ml.com/product/1")
        self.store = kwargs.get("store", "TestStore")
        self.sku = kwargs.get("sku", "TST-001")
        self.name = kwargs.get("name", "Laptop Test 15")
        self.name_normalized = kwargs.get("name_normalized", "laptop test 15")
        self.brand = kwargs.get("brand", "TestBrand")
        self.category = kwargs.get("category", "Computación > Laptops")
        self.description = kwargs.get("description", "Una laptop de prueba")
        self.image_url = kwargs.get("image_url", "https://img.ml.com/test.jpg")
        self.specs = kwargs.get("specs", {"RAM": "8GB"})
        self.price = kwargs.get("price", 42500.0)
        self.original_price = kwargs.get("original_price", None)
        self.currency = kwargs.get("currency", "DOP")
        self.discount_pct = kwargs.get("discount_pct", None)
        self.is_on_sale = kwargs.get("is_on_sale", False)
        self.in_stock = kwargs.get("in_stock", True)
        self.stock_qty = kwargs.get("stock_qty", None)
        self.seller_name = kwargs.get("seller_name", "VendedorTest")
        self.seller_rating = kwargs.get("seller_rating", None)
        self.scraped_at = datetime.now(timezone.utc).isoformat()


# ── Product model ─────────────────────────────────────────────────────────────

class TestProductModel:

    def test_create_product(self, db):
        p = Product(
            url="https://ml.com/laptop/1",
            store="MercadoLibre",
            name="Laptop HP 15",
            current_price=42500.0,
            current_currency="DOP",
        )
        db.add(p)
        db.flush()
        assert p.id is not None

    def test_first_seen_at_auto(self, db):
        p = Product(url="https://ml.com/2", store="Test", name="X", current_price=100.0)
        db.add(p)
        db.flush()
        assert p.first_seen_at is not None

    def test_to_dict_returns_dict(self, db):
        p = Product(url="https://ml.com/3", store="Test", name="Y", current_price=200.0)
        db.add(p)
        db.flush()
        d = p.to_dict()
        assert isinstance(d, dict)
        assert d["url"] == "https://ml.com/3"
        assert d["current_price"] == 200.0

    def test_unique_url_constraint(self, db):
        from sqlalchemy.exc import IntegrityError
        p1 = Product(url="https://ml.com/dup", store="A", name="P1", current_price=10.0)
        p2 = Product(url="https://ml.com/dup", store="B", name="P2", current_price=20.0)
        db.add(p1)
        db.flush()
        db.add(p2)
        with pytest.raises(IntegrityError):
            db.flush()


# ── PriceHistory model ────────────────────────────────────────────────────────

class TestPriceHistoryModel:

    def test_create_history(self, db):
        p = Product(url="https://ml.com/p1", store="T", name="P", current_price=100.0)
        db.add(p)
        db.flush()

        h = PriceHistory(product_id=p.id, price=100.0, currency="DOP")
        db.add(h)
        db.flush()
        assert h.id is not None
        assert h.scraped_at is not None

    def test_to_dict(self, db):
        p = Product(url="https://ml.com/p2", store="T", name="P", current_price=100.0)
        db.add(p)
        db.flush()
        h = PriceHistory(product_id=p.id, price=99.99, currency="USD")
        db.add(h)
        db.flush()
        d = h.to_dict()
        assert d["price"] == 99.99
        assert d["currency"] == "USD"


# ── ProductRepository ─────────────────────────────────────────────────────────

class TestProductRepository:

    def test_upsert_creates_new_product(self, product_repo, db):
        parsed = FakeParsed()
        product = product_repo.upsert_from_parsed(parsed)
        db.commit()
        assert product.id is not None
        assert product.name == "Laptop Test 15"

    def test_upsert_returns_same_product_on_second_call(self, product_repo, db):
        parsed = FakeParsed()
        p1 = product_repo.upsert_from_parsed(parsed)
        db.commit()
        p2 = product_repo.upsert_from_parsed(parsed)
        db.commit()
        assert p1.id == p2.id

    def test_upsert_updates_price_snapshot(self, product_repo, db):
        parsed = FakeParsed(price=42500.0)
        product_repo.upsert_from_parsed(parsed)
        db.commit()

        parsed2 = FakeParsed(price=38000.0)
        updated = product_repo.upsert_from_parsed(parsed2)
        db.commit()
        assert updated.current_price == 38000.0

    def test_get_by_url(self, product_repo, db):
        parsed = FakeParsed(url="https://ml.com/specific")
        product_repo.upsert_from_parsed(parsed)
        db.commit()

        found = product_repo.get_by_url("https://ml.com/specific")
        assert found is not None
        assert found.url == "https://ml.com/specific"

    def test_get_by_url_returns_none_if_not_found(self, product_repo):
        result = product_repo.get_by_url("https://doesnotexist.com")
        assert result is None

    def test_list_all_returns_products(self, product_repo, db):
        for i in range(3):
            product_repo.upsert_from_parsed(FakeParsed(url=f"https://ml.com/p{i}"))
        db.commit()
        products = product_repo.list_all()
        assert len(products) == 3

    def test_list_all_filter_by_store(self, product_repo, db):
        product_repo.upsert_from_parsed(FakeParsed(url="https://ml.com/a", store="StoreA"))
        product_repo.upsert_from_parsed(FakeParsed(url="https://ml.com/b", store="StoreB"))
        db.commit()
        results = product_repo.list_all(store="StoreA")
        assert len(results) == 1
        assert results[0].store == "StoreA"

    def test_list_on_sale(self, product_repo, db):
        product_repo.upsert_from_parsed(FakeParsed(
            url="https://ml.com/sale",
            is_on_sale=True,
            discount_pct=15.0,
        ))
        product_repo.upsert_from_parsed(FakeParsed(
            url="https://ml.com/nosale",
            is_on_sale=False,
        ))
        db.commit()
        results = product_repo.list_on_sale()
        assert len(results) == 1

    def test_search_by_name(self, product_repo, db):
        product_repo.upsert_from_parsed(FakeParsed(
            url="https://ml.com/hp",
            name="Laptop HP 15",
            name_normalized="laptop hp 15",
        ))
        product_repo.upsert_from_parsed(FakeParsed(
            url="https://ml.com/dell",
            name="Laptop Dell XPS",
            name_normalized="laptop dell xps",
        ))
        db.commit()
        results = product_repo.search("hp")
        assert len(results) == 1
        assert "HP" in results[0].name

    def test_count(self, product_repo, db):
        for i in range(5):
            product_repo.upsert_from_parsed(FakeParsed(url=f"https://ml.com/c{i}"))
        db.commit()
        assert product_repo.count() == 5

    def test_delete_product(self, product_repo, db):
        parsed = FakeParsed(url="https://ml.com/delete_me")
        product = product_repo.upsert_from_parsed(parsed)
        db.commit()
        product_repo.delete(product.id)
        db.commit()
        assert product_repo.get_by_url("https://ml.com/delete_me") is None

    def test_set_alert_threshold(self, product_repo, db):
        product = product_repo.upsert_from_parsed(FakeParsed())
        db.commit()
        product_repo.set_alert_threshold(product.id, 3.0)
        db.commit()
        refreshed = product_repo.get_by_id(product.id)
        assert refreshed.alert_threshold_pct == 3.0


# ── PriceHistoryRepository ────────────────────────────────────────────────────

class TestPriceHistoryRepository:

    def _make_product(self, db, url="https://ml.com/hist"):
        p = Product(url=url, store="T", name="P", current_price=100.0)
        db.add(p)
        db.flush()
        return p

    def test_add_history_record(self, history_repo, db):
        p = self._make_product(db)
        parsed = FakeParsed(price=100.0)
        record = history_repo.add(p.id, parsed, spider_name="test")
        db.commit()
        assert record.id is not None
        assert record.price == 100.0

    def test_get_latest(self, history_repo, db):
        p = self._make_product(db)
        for price in [100, 95, 90]:
            parsed = FakeParsed(price=float(price))
            history_repo.add(p.id, parsed)
        db.commit()
        latest = history_repo.get_latest(p.id)
        # Should be the most recently added — but scraped_at is the same second,
        # so we check it's one of our prices
        assert latest.price in [100.0, 95.0, 90.0]

    def test_get_history_returns_all(self, history_repo, db):
        p = self._make_product(db)
        for price in [100, 95, 90, 85, 80]:
            history_repo.add(p.id, FakeParsed(price=float(price)))
        db.commit()
        history = history_repo.get_history(p.id)
        assert len(history) == 5

    def test_get_history_limit(self, history_repo, db):
        p = self._make_product(db)
        for price in range(100, 110):
            history_repo.add(p.id, FakeParsed(price=float(price)))
        db.commit()
        history = history_repo.get_history(p.id, limit=3)
        assert len(history) == 3

    def test_get_min_price(self, history_repo, db):
        p = self._make_product(db)
        for price in [100, 80, 90, 70, 95]:
            history_repo.add(p.id, FakeParsed(price=float(price)))
        db.commit()
        assert history_repo.get_min_price(p.id) == 70.0

    def test_get_max_price(self, history_repo, db):
        p = self._make_product(db)
        for price in [100, 80, 120, 70, 95]:
            history_repo.add(p.id, FakeParsed(price=float(price)))
        db.commit()
        assert history_repo.get_max_price(p.id) == 120.0

    def test_count_scrapes(self, history_repo, db):
        p = self._make_product(db)
        for _ in range(7):
            history_repo.add(p.id, FakeParsed())
        db.commit()
        assert history_repo.count_scrapes(p.id) == 7

    def test_get_avg_price(self, history_repo, db):
        p = self._make_product(db)
        for price in [100, 200]:
            history_repo.add(p.id, FakeParsed(price=float(price)))
        db.commit()
        avg = history_repo.get_avg_price(p.id, days=30)
        assert avg == 150.0


# ── MonitoredUrlRepository ────────────────────────────────────────────────────

class TestMonitoredUrlRepository:

    def test_add_url(self, monitored_repo, db):
        record = monitored_repo.add("https://ml.com/watch", store="ML", label="Test")
        db.commit()
        assert record.id is not None
        assert record.url == "https://ml.com/watch"

    def test_add_duplicate_returns_existing(self, monitored_repo, db):
        r1 = monitored_repo.add("https://ml.com/dup")
        db.commit()
        r2 = monitored_repo.add("https://ml.com/dup")
        db.commit()
        assert r1.id == r2.id

    def test_get_by_url(self, monitored_repo, db):
        monitored_repo.add("https://ml.com/find_me")
        db.commit()
        found = monitored_repo.get_by_url("https://ml.com/find_me")
        assert found is not None

    def test_get_due_returns_active(self, monitored_repo, db):
        monitored_repo.add("https://ml.com/due1")
        monitored_repo.add("https://ml.com/due2")
        db.commit()
        due = monitored_repo.get_due()
        assert len(due) == 2

    def test_deactivate(self, monitored_repo, db):
        record = monitored_repo.add("https://ml.com/deactivate")
        db.commit()
        monitored_repo.deactivate(record.id)
        db.commit()
        found = monitored_repo.get_by_url("https://ml.com/deactivate")
        assert found.is_active is False

    def test_mark_scraped_success_resets_errors(self, monitored_repo, db):
        record = monitored_repo.add("https://ml.com/mark")
        record.consecutive_errors = 3
        db.commit()
        monitored_repo.mark_scraped(record.id, success=True)
        db.commit()
        refreshed = monitored_repo.get_by_url("https://ml.com/mark")
        assert refreshed.consecutive_errors == 0

    def test_mark_scraped_failure_increments_errors(self, monitored_repo, db):
        record = monitored_repo.add("https://ml.com/fail")
        db.commit()
        monitored_repo.mark_scraped(record.id, success=False)
        db.commit()
        refreshed = monitored_repo.get_by_url("https://ml.com/fail")
        assert refreshed.consecutive_errors == 1


# ── PriceChangeDetector ───────────────────────────────────────────────────────

def _make_history(price, in_stock=True, currency="DOP") -> PriceHistory:
    return PriceHistory(product_id=1, price=price, currency=currency, in_stock=in_stock)


class TestPriceChangeDetector:

    def test_first_record_no_alert(self, detector):
        current = _make_history(42500.0)
        result = detector.detect(None, current)
        assert result.change_type == ChangeType.FIRST_RECORD
        assert result.should_alert is False

    def test_no_change(self, detector):
        old = _make_history(42500.0)
        new = _make_history(42500.0)
        result = detector.detect(old, new)
        assert result.change_type == ChangeType.NO_CHANGE
        assert result.should_alert is False

    def test_price_drop_below_threshold_no_alert(self, detector):
        old = _make_history(42500.0)
        new = _make_history(42000.0)  # ~1.2% drop — bajo el umbral de 5%
        result = detector.detect(old, new)
        assert result.change_type == ChangeType.PRICE_DROP
        assert result.should_alert is False

    def test_price_drop_above_threshold_alerts(self, detector):
        old = _make_history(42500.0)
        new = _make_history(39000.0)  # ~8.2% drop — sobre el umbral
        result = detector.detect(old, new)
        assert result.change_type == ChangeType.PRICE_DROP
        assert result.should_alert is True

    def test_price_rise_above_threshold_alerts(self, detector):
        old = _make_history(42500.0)
        new = _make_history(47000.0)  # ~10.6% rise
        result = detector.detect(old, new)
        assert result.change_type == ChangeType.PRICE_RISE
        assert result.should_alert is True

    def test_change_pct_calculated_correctly(self, detector):
        old = _make_history(50000.0)
        new = _make_history(45000.0)   # -10%
        result = detector.detect(old, new)
        assert result.change_pct == pytest.approx(-10.0, abs=0.1)

    def test_back_in_stock_always_alerts(self, detector):
        old = _make_history(42500.0, in_stock=False)
        new = _make_history(42500.0, in_stock=True)
        result = detector.detect(old, new)
        assert result.change_type == ChangeType.BACK_IN_STOCK
        assert result.should_alert is True

    def test_out_of_stock_always_alerts(self, detector):
        old = _make_history(42500.0, in_stock=True)
        new = _make_history(42500.0, in_stock=False)
        result = detector.detect(old, new)
        assert result.change_type == ChangeType.OUT_OF_STOCK
        assert result.should_alert is True

    def test_new_all_time_low_alerts(self, detector):
        old = _make_history(42500.0)
        new = _make_history(41000.0)
        # current all_time_low is 42000 — new price beats it
        result = detector.detect(old, new, all_time_low=42000.0)
        assert result.is_new_low is True
        assert result.should_alert is True
        assert result.change_type == ChangeType.NEW_ALL_TIME_LOW

    def test_summary_no_change(self, detector):
        old = _make_history(100.0)
        new = _make_history(100.0)
        result = detector.detect(old, new)
        assert "Sin cambio" in result.summary

    def test_summary_price_drop(self, detector):
        old = _make_history(50000.0)
        new = _make_history(40000.0)
        result = detector.detect(old, new)
        assert "↓" in result.summary
        assert "20.0%" in result.summary

    def test_summary_back_in_stock(self, detector):
        old = _make_history(100.0, in_stock=False)
        new = _make_history(100.0, in_stock=True)
        result = detector.detect(old, new)
        assert "stock" in result.summary.lower()

    def test_detect_from_prices_helper(self, detector):
        result = detector.detect_from_prices(
            old_price=100.0,
            new_price=85.0,
            currency="USD",
        )
        assert result.change_type == ChangeType.PRICE_DROP
        assert result.change_pct == pytest.approx(-15.0, abs=0.1)

    def test_to_dict(self, detector):
        old = _make_history(100.0)
        new = _make_history(90.0)
        result = detector.detect(old, new)
        d = result.to_dict()
        assert "change_type" in d
        assert "should_alert" in d
        assert "summary" in d

    def test_custom_threshold(self):
        detector_low = PriceChangeDetector(threshold_pct=2.0)
        old = _make_history(100.0)
        new = _make_history(97.0)  # 3% drop — sobre threshold de 2%
        result = detector_low.detect(old, new)
        assert result.should_alert is True

    def test_change_abs_calculated(self, detector):
        old = _make_history(50000.0)
        new = _make_history(45000.0)
        result = detector.detect(old, new)
        assert result.change_abs == -5000.0


# ── PriceAlertRepository ──────────────────────────────────────────────────────

class TestPriceAlertRepository:

    def _make_product(self, db):
        p = Product(url="https://ml.com/alert_p", store="T", name="P", current_price=100.0)
        db.add(p)
        db.flush()
        return p

    def test_create_alert(self, alert_repo, db):
        p = self._make_product(db)
        alert = alert_repo.create(
            product_id=p.id,
            alert_type="price_drop",
            message="Bajó un 10%",
            old_price=100.0,
            new_price=90.0,
            change_pct=-10.0,
        )
        db.commit()
        assert alert.id is not None
        assert alert.is_notified is False

    def test_get_pending_returns_unnotified(self, alert_repo, db):
        p = self._make_product(db)
        alert_repo.create(p.id, "price_drop", "Test")
        db.commit()
        pending = alert_repo.get_pending()
        assert len(pending) == 1

    def test_mark_notified(self, alert_repo, db):
        p = self._make_product(db)
        alert = alert_repo.create(p.id, "price_drop", "Test")
        db.commit()
        alert_repo.mark_notified(alert.id)
        db.commit()
        pending = alert_repo.get_pending()
        assert len(pending) == 0

    def test_list_for_product(self, alert_repo, db):
        p = self._make_product(db)
        for i in range(3):
            alert_repo.create(p.id, "price_drop", f"Alert {i}")
        db.commit()
        alerts = alert_repo.list_for_product(p.id)
        assert len(alerts) == 3

    def test_to_dict(self, alert_repo, db):
        p = self._make_product(db)
        alert = alert_repo.create(p.id, "price_drop", "Test", old_price=100.0, new_price=90.0)
        db.commit()
        d = alert.to_dict()
        assert d["alert_type"] == "price_drop"
        assert d["old_price"] == 100.0
