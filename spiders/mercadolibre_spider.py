"""
MercadoLibre spider — scrapes product listings and detail pages.

Usage:
    scrapy crawl mercadolibre -a category=computacion -a max_pages=3
    scrapy crawl mercadolibre -a url=https://www.mercadolibre.com.do/...
"""
import logging
import re

import scrapy

from .base_spider import BaseProductSpider
from .items import ProductItem

logger = logging.getLogger(__name__)

# MercadoLibre country domains
ML_DOMAINS = {
    "do": "mercadolibre.com.do",   # Dominican Republic
    "mx": "mercadolibre.com.mx",   # Mexico
    "ar": "mercadolibre.com.ar",   # Argentina
    "co": "mercadolibre.com.co",   # Colombia
    "cl": "mercadolibre.cl",       # Chile
    "us": "mercadolibre.com",      # USA
}

CATEGORY_URLS = {
    "computacion": "https://computacion.mercadolibre.com.do/",
    "celulares": "https://celulares-telefonia.mercadolibre.com.do/",
    "electrodomesticos": "https://electrodomesticos.mercadolibre.com.do/",
    "tv-audio-video": "https://tv-audio-video.mercadolibre.com.do/",
}


class MercadoLibreSpider(BaseProductSpider):
    """
    Crawls MercadoLibre listing pages and extracts product data
    from each product detail page.
    """

    name = "mercadolibre"
    store_name = "MercadoLibre"
    currency = "DOP"
    allowed_domains = list(ML_DOMAINS.values())

    custom_settings = {
        **BaseProductSpider.custom_settings,
        "ROBOTSTXT_OBEY": True,
        "DOWNLOAD_DELAY": 2.5,
    }

    def __init__(self, category="computacion", url=None, max_pages=5, country="do", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_pages = int(max_pages)
        self.pages_crawled = 0
        self.country = country

        if url:
            self.start_urls = [url]
        else:
            base = CATEGORY_URLS.get(category)
            if not base:
                available = ", ".join(CATEGORY_URLS.keys())
                raise ValueError(f"Unknown category '{category}'. Available: {available}")
            self.start_urls = [base]

        logger.info(f"[mercadolibre] Starting crawl | category={category} | max_pages={max_pages}")

    # ── Listing page ──────────────────────────────────────────────────────────

    def parse(self, response):
        """Parse a listing/search results page."""
        soup = self.soup(response)

        # Find all product links on the listing
        product_links = response.css(
            "a.poly-component__title::attr(href), "
            "a.ui-search-item__group__element::attr(href)"
        ).getall()

        logger.info(f"[mercadolibre] Listing page: found {len(product_links)} products | {response.url}")

        for link in product_links:
            # Skip sponsored/ad links that redirect off-domain
            if "click1.mercadolibre" in link or "meli" not in link.lower():
                if "mercadolibre" not in link:
                    continue
            yield scrapy.Request(
                url=link,
                callback=self.parse_product,
                errback=self.handle_error,
            )

        # ── Pagination ────────────────────────────────────────────────────────
        self.pages_crawled += 1
        if self.pages_crawled < self.max_pages:
            next_page = response.css(
                "a.andes-pagination__link[title='Siguiente']::attr(href), "
                "a[title='Siguiente']::attr(href)"
            ).get()

            if next_page:
                logger.info(f"[mercadolibre] Following page {self.pages_crawled + 1}: {next_page}")
                yield scrapy.Request(
                    url=next_page,
                    callback=self.parse,
                    errback=self.handle_error,
                )

    # ── Product detail page ───────────────────────────────────────────────────

    def parse_product(self, response) -> ProductItem:
        """Parse a MercadoLibre product detail page."""
        try:
            soup = self.soup(response)

            # Product name
            name = (
                response.css("h1.ui-pdp-title::text").get()
                or response.css("h1.item-title__primary::text").get()
                or ""
            ).strip()

            if not name:
                logger.warning(f"[mercadolibre] No name found at {response.url}")
                self.items_failed += 1
                return

            # Price — MercadoLibre uses andes-money-amount structure
            price_raw = (
                response.css(
                    "span.andes-money-amount__fraction::text"
                ).getall()
            )

            # First price is usually the current price
            price = self.clean_price(price_raw[0]) if price_raw else None

            # Original price (before discount) — typically the second amount shown
            original_price = self.clean_price(price_raw[1]) if len(price_raw) > 1 else None

            # Currency
            currency_symbol = response.css(
                "span.andes-money-amount__currency-symbol::text"
            ).get() or "RD$"
            currency = self._resolve_currency(currency_symbol)

            # Stock status
            add_to_cart = response.css(
                "button.ui-pdp-action--primary, "
                "button#add-to-cart"
            ).get()
            in_stock = add_to_cart is not None

            # SKU / Item ID — usually in the URL
            sku = self._extract_sku(response.url)

            # Brand
            brand = response.css(
                "span.ui-pdp-color--BLACK.ui-pdp-size--XSMALL::text, "
                "span[class*='brand']::text"
            ).get()

            # Category (breadcrumb)
            breadcrumb = response.css(
                "ol.andes-breadcrumb li a::text"
            ).getall()
            category = " > ".join(breadcrumb[1:]) if len(breadcrumb) > 1 else None

            item = self.make_item(
                url=response.url,
                name=name,
                sku=sku,
                brand=brand,
                category=category,
                price=price,
                original_price=original_price,
                currency=currency,
                in_stock=in_stock,
            )

            self.items_scraped += 1
            logger.info(f"[mercadolibre] Scraped: {name[:60]} | Price: {currency} {price}")
            return item

        except Exception as exc:
            self.items_failed += 1
            logger.error(f"[mercadolibre] Error parsing {response.url}: {exc}", exc_info=True)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _extract_sku(self, url: str) -> str | None:
        """Extract MercadoLibre item ID (MLM-XXXXX) from URL."""
        match = re.search(r"ML[A-Z]-?\d+", url, re.IGNORECASE)
        return match.group(0).upper() if match else None

    def _resolve_currency(self, symbol: str) -> str:
        mapping = {
            "RD$": "DOP",
            "$": "USD",
            "MX$": "MXN",
            "AR$": "ARS",
            "COP": "COP",
            "CL$": "CLP",
        }
        return mapping.get(symbol, symbol)

    def handle_error(self, failure):
        self.items_failed += 1
        logger.error(f"[mercadolibre] Request failed: {failure.request.url} — {failure.value}")
