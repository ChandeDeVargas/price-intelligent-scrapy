"""
Scrapy Items — define the data structure for scraped products.
"""
import scrapy

class ProductItem(scrapy.Item):
    """Represents a single scraped product"""

    # Identifiers
    url = scrapy.Field()
    store = scrapy.Field() # e.g. "mercadolibre", "amazon"

    # Product data
    name = scrapy.Field()
    name_normalized = scrapy.Field()
    description = scrapy.Field()
    image_url = scrapy.Field()
    specs = scrapy.Field()
    discount_pct = scrapy.Field()
    is_on_sale = scrapy.Field()
    stock_qty = scrapy.Field()
    seller_name = scrapy.Field()
    seller_rating = scrapy.Field()
    sku = scrapy.Field() # Store' internal product ID
    brand = scrapy.Field()
    category = scrapy.Field()

    # Pricing
    price = scrapy.Field() # Current price (float)
    original_price = scrapy.Field() # Before discount (float or none)
    currency = scrapy.Field() # e.g. "USD", "DOP"
    in_stock = scrapy.Field() # Boolean

    # Meta
    scraped_at = scrapy.Field() # ISO datetime string
    spider_name = scrapy.Field()