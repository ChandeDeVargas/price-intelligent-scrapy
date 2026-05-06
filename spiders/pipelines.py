"""
Scrapy Item Pipelines.

Order (configured in scrapy_settings.py):
    100 — ValidatePipeline       Drop items missing required fields
    200 — DuplicateFilterPipeline Drop items seen in this run
    900 — JsonExportPipeline     Write clean items to output/
"""
import json
import logging
import os
from pathlib import Path

from scrapy.exceptions import DropItem

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ["url", "name", "price", "store", "scraped_at"]


class ValidatePipeline:
    """Drop items that are missing required fields or have invalid prices."""

    def process_item(self, item, spider):
        for field in REQUIRED_FIELDS:
            if not item.get(field):
                raise DropItem(f"Missing required field '{field}' in item: {dict(item)}")

        if item.get("price") is not None and item["price"] <= 0:
            raise DropItem(f"Invalid price {item['price']} for: {item.get('name')}")

        return item


class DuplicateFilterPipeline:
    """Drop items with duplicate URLs within the same spider run."""

    def __init__(self):
        self.seen_urls: set[str] = set()

    def process_item(self, item, spider):
        url = item.get("url", "")
        if url in self.seen_urls:
            raise DropItem(f"Duplicate URL: {url}")
        self.seen_urls.add(url)
        return item


class JsonExportPipeline:
    """
    Write scraped items to a JSON Lines file in output/.

    Each spider run appends to its own file:
        output/mercadolibre.jsonl
        output/generic.jsonl
    """

    def __init__(self):
        self.files: dict = {}
        Path("output").mkdir(exist_ok=True)

    def open_spider(self, spider):
        path = f"output/{spider.name}.jsonl"
        self.files[spider.name] = open(path, "a", encoding="utf-8")
        logger.info(f"[pipeline] Writing output to {path}")

    def close_spider(self, spider):
        if spider.name in self.files:
            self.files[spider.name].close()

    def process_item(self, item, spider):
        line = json.dumps(dict(item), ensure_ascii=False)
        self.files[spider.name].write(line + "\n")
        return item
