"""
Tests — Day 1: base spider and price cleaning.

Run:
    pytest tests/test_day1.py -v
"""

import pytest
from unittest.mock import MagicMock

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from spiders.base_spider import BaseProductSpider
from spiders.items import ProductItem


class ConcreteSpider(BaseProductSpider):
    """Minimal concrete spider for testing abstract base."""
    name = "test_spider"
    store_name = "TestStore"
    start_urls = ["http://example.com"]

    def parse_product(self, response):
        pass


@pytest.fixture
def spider():
    return ConcreteSpider()


class TestCleanPrice:
    """Test the price normalization logic."""

    def test_simple_integer(self, spider):
        assert spider.clean_price("1299") == 1299.0

    def test_us_format_thousands(self, spider):
        assert spider.clean_price("1,299.99") == 1299.99

    def test_european_format(self, spider):
        assert spider.clean_price("1.299,99") == 1299.99

    def test_with_currency_symbol(self, spider):
        assert spider.clean_price("RD$4500") == 4500.0

    def test_with_dollar_sign(self, spider):
        assert spider.clean_price("$1,234.56") == 1234.56

    def test_with_spaces(self, spider):
        assert spider.clean_price("  999 ") == 999.0

    def test_empty_string(self, spider):
        assert spider.clean_price("") is None

    def test_none_input(self, spider):
        assert spider.clean_price(None) is None

    def test_non_numeric(self, spider):
        assert spider.clean_price("N/A") is None

    def test_simple_decimal(self, spider):
        assert spider.clean_price("29.99") == 29.99

    def test_comma_as_decimal(self, spider):
        assert spider.clean_price("1299,99") == 1299.99

    def test_large_price(self, spider):
        assert spider.clean_price("$ 1.299.999") == 1299999.0


class TestMakeItem:
    """Test the make_item factory method."""

    def test_defaults_populated(self, spider):
        item = spider.make_item(url="http://ex.com", name="Test", price=99.0)
        assert item["store"] == "TestStore"
        assert item["currency"] == "USD"
        assert item["in_stock"] is True
        assert item["sku"] is None
        assert item["scraped_at"] is not None

    def test_overrides_work(self, spider):
        item = spider.make_item(
            url="http://ex.com",
            name="Laptop",
            price=500.0,
            currency="DOP",
            in_stock=False,
        )
        assert item["currency"] == "DOP"
        assert item["in_stock"] is False

    def test_returns_product_item(self, spider):
        item = spider.make_item(url="http://ex.com", name="X", price=1.0)
        assert isinstance(item, ProductItem)


class TestProductItem:
    """Test ProductItem field structure."""

    def test_all_fields_accessible(self):
        item = ProductItem()
        fields = [
            "url", "store", "name", "sku", "brand", "category",
            "price", "original_price", "currency", "in_stock",
            "scraped_at", "spider_name",
        ]
        for field in fields:
            item[field] = None  # Should not raise KeyError

    def test_item_is_dict_like(self):
        item = ProductItem()
        item["name"] = "Test Product"
        assert dict(item)["name"] == "Test Product"
