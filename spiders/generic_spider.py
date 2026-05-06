"""
Generic spider — scrape any e-commerce site by passing CSS selector config.

Usage:
    scrapy crawl generic \\
        -a start_url=https://example.com/products \\
        -a store=MyStore \\
        -a sel_name="h1.product-title::text" \\
        -a sel_price="span.price::text" \\
        -a sel_links="a.product-link::attr(href)"

This spider is useful for quick prototyping before writing a dedicated spider.
"""
import logging
import scrapy
from .base_spider import BaseProductSpider

logger = logging.getLogger(__name__)


class GenericSpider(BaseProductSpider):
    """
    Configurable spider — pass CSS selectors as spider arguments.
    Use this to test a new site before writing a dedicated spider.
    """

    name = "generic"

    def __init__(
        self,
        start_url: str = "",
        store: str = "Generic",
        currency: str = "USD",
        # CSS selectors
        sel_name: str = "h1::text",
        sel_price: str = "span.price::text",
        sel_links: str = "a.product::attr(href)",
        sel_original_price: str = "",
        sel_stock: str = "",
        sel_sku: str = "",
        sel_brand: str = "",
        sel_next_page: str = "a[rel=next]::attr(href)",
        max_pages: int = 3,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        if not start_url:
            raise ValueError("start_url is required for the generic spider")

        self.start_urls = [start_url]
        self.store_name = store
        self.currency = currency
        self.sel_name = sel_name
        self.sel_price = sel_price
        self.sel_links = sel_links
        self.sel_original_price = sel_original_price
        self.sel_stock = sel_stock
        self.sel_sku = sel_sku
        self.sel_brand = sel_brand
        self.sel_next_page = sel_next_page
        self.max_pages = int(max_pages)
        self.pages_crawled = 0

        logger.info(f"[generic] Starting | store={store} | url={start_url}")

    def parse(self, response):
        product_links = response.css(self.sel_links).getall()
        logger.info(f"[generic] Found {len(product_links)} links at {response.url}")

        for link in product_links:
            if not link.startswith("http"):
                link = response.urljoin(link)
            yield scrapy.Request(link, callback=self.parse_product, errback=self.handle_error)

        self.pages_crawled += 1
        if self.pages_crawled < self.max_pages and self.sel_next_page:
            next_page = response.css(self.sel_next_page).get()
            if next_page:
                yield scrapy.Request(response.urljoin(next_page), callback=self.parse)

    def parse_product(self, response):
        try:
            name = response.css(self.sel_name).get("").strip()
            if not name:
                self.items_failed += 1
                return

            price_raw = response.css(self.sel_price).get()
            price = self.clean_price(price_raw)

            original_price = None
            if self.sel_original_price:
                original_price = self.clean_price(response.css(self.sel_original_price).get())

            in_stock = True
            if self.sel_stock:
                in_stock = bool(response.css(self.sel_stock).get())

            sku = response.css(self.sel_sku).get() if self.sel_sku else None
            brand = response.css(self.sel_brand).get() if self.sel_brand else None

            item = self.make_item(
                url=response.url,
                name=name,
                sku=sku,
                brand=brand,
                price=price,
                original_price=original_price,
                in_stock=in_stock,
            )

            self.items_scraped += 1
            logger.info(f"[generic] {name[:60]} | {self.currency} {price}")
            return item

        except Exception as exc:
            self.items_failed += 1
            logger.error(f"[generic] Error at {response.url}: {exc}", exc_info=True)

    def handle_error(self, failure):
        self.items_failed += 1
        logger.error(f"[generic] Request failed: {failure.request.url}")
