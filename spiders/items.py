"""
Scrapy Items — define the data structure of a scraped product.
"""
import scrapy


class ProductItem(scrapy.Item):
    """Represents a scraped product with all its fields normalized."""

    # Identifiers
    url = scrapy.Field()
    store = scrapy.Field()

    # Product info
    name = scrapy.Field()
    name_normalized = scrapy.Field()   # Day 2: normalized name for comparison
    sku = scrapy.Field()
    brand = scrapy.Field()
    category = scrapy.Field()
    description = scrapy.Field()       # Day 2: product description
    image_url = scrapy.Field()         # Day 2: main image URL
    specs = scrapy.Field()             # Day 2: technical specifications dict

    # Pricing
    price = scrapy.Field()
    original_price = scrapy.Field()
    currency = scrapy.Field()
    discount_pct = scrapy.Field()      # Day 2: calculated discount %
    is_on_sale = scrapy.Field()        # Day 2: True if there is a crossed-out price

    # Availability
    in_stock = scrapy.Field()
    stock_qty = scrapy.Field()         # Day 2: available quantity

    # Seller
    seller_name = scrapy.Field()       # Day 2: seller name
    seller_rating = scrapy.Field()     # Day 2: seller rating

    # Meta
    scraped_at = scrapy.Field()
    spider_name = scrapy.Field()