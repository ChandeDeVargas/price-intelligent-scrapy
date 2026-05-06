"""
Base spider — shared logic inherited by all store-specific spiders.
"""
import re
import logging
from datetime import datetime, timezone
from abc import abstractmethod

import scrapy
from bs4 import BeautifulSoup

from .items import ProductItem

logger = logging.getLogger(__name__)


class BaseProductSpider(scrapy.Spider):
    """
    Base class for all price intelligence spiders.

    Subclasses must implement:
        - start_urls (list[str])
        - parse_product(response) -> ProductItem

    Subclasses may override:
        - parse(response)  — to handle listing/pagination pages
    """

    # Override in subclass
    store_name: str = "unknown"
    currency: str = "USD"

    custom_settings = {
        "DOWNLOAD_DELAY": 2,
        "RANDOMIZE_DOWNLOAD_DELAY": True,
        "AUTOTHROTTLE_ENABLED": True,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.items_scraped = 0
        self.items_failed = 0

    # ── Helpers ───────────────────────────────────────────────────────────────

    def clean_price(self, raw: str | None) -> float | None:
        """
        Normalize a raw price string to float.

        Handles formats like:
            "$ 1.299,99"  → 1299.99
            "1,299.99"    → 1299.99
            "RD$4500"     → 4500.0
        """
        if not raw:
            return None

        raw = str(raw).strip()

        # Remove currency symbols and non-numeric chars except , and .
        cleaned = re.sub(r"[^\d.,]", "", raw)

        if not cleaned:
            return None

        # Detect format: if last separator is comma → European (1.299,99)
        dot_count = cleaned.count(".")
        comma_count = cleaned.count(",")

        if dot_count > 1:
            # Multiple dots → thousands separators: "1.299.999" → 1299999
            cleaned = cleaned.replace(".", "")
        elif comma_count > 1:
            # Multiple commas → thousands separators: "1,299,999" → 1299999
            cleaned = cleaned.replace(",", "")
        elif "," in cleaned and "." in cleaned:
            if cleaned.rfind(",") > cleaned.rfind("."):
                # European format: "1.299,99"
                cleaned = cleaned.replace(".", "").replace(",", ".")
            else:
                # US format: "1,299.99"
                cleaned = cleaned.replace(",", "")
        elif "," in cleaned and comma_count == 1:
            parts = cleaned.split(",")
            if len(parts[1]) == 2:
                # Treat as decimal: "1299,99" → 1299.99
                cleaned = cleaned.replace(",", ".")
            else:
                # Treat as thousands: "1,299" → 1299
                cleaned = cleaned.replace(",", "")

        try:
            return float(cleaned)
        except ValueError:
            logger.warning(f"Could not parse price: {raw!r}")
            return None

    def make_item(self, **kwargs) -> ProductItem:
        """Crea un ProductItem con defaults para todos los campos (Día 1 + Día 2)."""
        item = ProductItem()
        # Día 1
        item["store"] = self.store_name
        item["currency"] = self.currency
        item["scraped_at"] = datetime.now(timezone.utc).isoformat()
        item["spider_name"] = self.name
        item["in_stock"] = True
        item["sku"] = None
        item["brand"] = None
        item["category"] = None
        item["original_price"] = None
        # Día 2
        item["name_normalized"] = None
        item["description"] = None
        item["image_url"] = None
        item["specs"] = {}
        item["discount_pct"] = None
        item["is_on_sale"] = False
        item["stock_qty"] = None
        item["seller_name"] = None
        item["seller_rating"] = None
        item.update(kwargs)
        return item

    def soup(self, response) -> BeautifulSoup:
        """Return a BeautifulSoup object from a Scrapy response."""
        return BeautifulSoup(response.text, "lxml")

    # ── Abstract interface ────────────────────────────────────────────────────

    @abstractmethod
    def parse_product(self, response) -> ProductItem:
        """Parse a product detail page and return a ProductItem."""
        raise NotImplementedError

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def closed(self, reason: str):
        logger.info(
            f"[{self.name}] Finished. "
            f"Scraped: {self.items_scraped} | Failed: {self.items_failed} | Reason: {reason}"
        )