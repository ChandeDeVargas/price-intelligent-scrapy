"""
ProductParser — parsing layer using BeautifulSoup.

Receives raw HTML (string) and returns a ParsedProduct with all
fields normalized, validated, and enriched.

This layer is independent of Scrapy: it can be used from tests,
manual scripts, or the API without needing a running spider.

Basic usage:
    from parsers.product_parse import ProductParser
    from parsers.models import StoreConfig

    config = STORE_CONFIGS["mercadolibre"]
    parser = ProductParser(config)
    result = parser.parse(html_string, url="https://...")
    print(result.price, result.discount_pct, result.is_on_sale)
"""

import re
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class ParsedProduct:
    """
    Fully normalized product, ready to be persisted to DB.
    All numeric fields are Python-native (float, bool, int).
    """
    # Identifiers
    url: str = ""
    store: str = ""
    sku: Optional[str] = None

    # Product info
    name: str = ""
    name_normalized: str = ""       # lowercase, without strange characters
    brand: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    specs: dict = field(default_factory=dict)  # technical attributes table

    # Pricing
    price: Optional[float] = None
    original_price: Optional[float] = None
    currency: str = "USD"
    discount_pct: Optional[float] = None       # calculated discount %
    is_on_sale: bool = False                   # True if there is a crossed-out price

    # Availability
    in_stock: bool = True
    stock_qty: Optional[int] = None            # quantity if available

    # Seller (marketplaces)
    seller_name: Optional[str] = None
    seller_rating: Optional[float] = None

    # Meta
    scraped_at: str = ""
    parse_errors: list = field(default_factory=list)  # non-fatal warnings

    @property
    def has_errors(self) -> bool:
        return bool(self.parse_errors)

    @property
    def is_valid(self) -> bool:
        """A valid product has at least a name and a price."""
        return bool(self.name and self.price and self.price > 0)

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "store": self.store,
            "sku": self.sku,
            "name": self.name,
            "name_normalized": self.name_normalized,
            "brand": self.brand,
            "category": self.category,
            "description": self.description,
            "image_url": self.image_url,
            "specs": self.specs,
            "price": self.price,
            "original_price": self.original_price,
            "currency": self.currency,
            "discount_pct": self.discount_pct,
            "is_on_sale": self.is_on_sale,
            "in_stock": self.in_stock,
            "stock_qty": self.stock_qty,
            "seller_name": self.seller_name,
            "seller_rating": self.seller_rating,
            "scraped_at": self.scraped_at,
            "parse_errors": self.parse_errors,
        }


# ── Store selector config ──────────────────────────────────────────────────────

@dataclass
class StoreConfig:
    """
    CSS/BeautifulSoup selector configuration for an e-commerce.
    Allows supporting new stores without touching the parser logic.
    """
    store_name: str
    currency: str = "USD"

    # CSS selectors (BeautifulSoup find / select)
    sel_name: str = "h1"
    sel_price: str = ""
    sel_original_price: str = ""
    sel_sku: str = ""
    sel_brand: str = ""
    sel_category: str = ""
    sel_description: str = ""
    sel_image: str = "img[src]"
    sel_stock: str = ""
    sel_stock_qty: str = ""
    sel_seller: str = ""
    sel_rating: str = ""
    sel_specs_table: str = ""       # technical specifications table

    # Attribute to extract from selector (default: text content)
    image_attr: str = "src"
    rating_attr: str = "content"    # often in a meta tag

    # Stock detection mode
    # "presence"  → in_stock = True if selector exists
    # "absence"   → in_stock = True if selector DOES NOT exist
    # "text"      → in_stock = selector text DOES NOT contain stock_negative_words
    stock_mode: str = "presence"
    stock_negative_words: list = field(default_factory=lambda: [
        "agotado", "sin stock", "no disponible", "out of stock",
        "sold out", "unavailable",
    ])


# ── Store configs ──────────────────────────────────────────────────────────────

STORE_CONFIGS: dict[str, StoreConfig] = {
    "mercadolibre": StoreConfig(
        store_name="MercadoLibre",
        currency="DOP",
        sel_name="h1.ui-pdp-title",
        sel_price="span.andes-money-amount__fraction",
        sel_original_price="s span.andes-money-amount__fraction",
        sel_brand="span.ui-pdp-color--BLACK.ui-pdp-size--XSMALL",
        sel_category="ol.andes-breadcrumb li a",
        sel_description="div.ui-pdp-description__content p",
        sel_image="figure.ui-pdp-gallery__figure img",
        sel_stock="button.ui-pdp-action--primary",
        sel_stock_qty="span.ui-pdp-buybox__quantity__available",
        sel_seller="span.ui-pdp-seller__header__title",
        sel_rating="span.ui-pdp-review__rating",
        sel_specs_table="table.andes-table",
        stock_mode="presence",
    ),
    "amazon": StoreConfig(
        store_name="Amazon",
        currency="USD",
        sel_name="#productTitle",
        sel_price="span.a-price-whole",
        sel_original_price="span.a-price.a-text-price span.a-offscreen",
        sel_brand="#bylineInfo",
        sel_category="#wayfinding-breadcrumbs_feature_div a",
        sel_description="#productDescription p",
        sel_image="#landingImage",
        sel_stock="#availability span",
        sel_seller="#sellerProfileTriggerId",
        sel_rating="span.a-icon-alt",
        sel_specs_table="#productDetails_techSpec_section_1",
        image_attr="src",
        stock_mode="text",
        stock_negative_words=["currently unavailable", "out of stock"],
    ),
    "generic": StoreConfig(
        store_name="Generic",
        currency="USD",
        sel_name="h1",
        sel_price="[class*='price']",
        sel_image="img.product",
        stock_mode="presence",
    ),
}


# ── Main parser ────────────────────────────────────────────────────────────────

class ProductParser:
    """
    Main parser — converts raw HTML into a clean ParsedProduct.

    The parser is separated from the spider to allow:
    - Testing without network
    - Reusing it in the API (re-parsing saved HTML)
    - Applying post-scrape enrichment logic
    """

    def __init__(self, config: StoreConfig):
        self.config = config

    # ── Public API ────────────────────────────────────────────────────────────

    def parse(self, html: str, url: str = "", sku: str | None = None) -> ParsedProduct:
        """
        Parses a product HTML and returns a normalized ParsedProduct.

        Args:
            html: Complete HTML of the product page
            url:  URL where the HTML came from
            sku:  Known SKU (from the spider), optional

        Returns:
            ParsedProduct with all extracted fields
        """
        product = ParsedProduct(
            url=url,
            store=self.config.store_name,
            currency=self.config.currency,
            scraped_at=datetime.now(timezone.utc).isoformat(),
            sku=sku,
        )

        try:
            soup = BeautifulSoup(html, "lxml")

            product.name          = self._extract_name(soup, product)
            product.name_normalized = self._normalize_name(product.name)
            product.brand         = self._extract_brand(soup, product)
            product.category      = self._extract_category(soup, product)
            product.description   = self._extract_description(soup, product)
            product.image_url     = self._extract_image(soup, product)
            product.specs         = self._extract_specs(soup, product)
            product.seller_name   = self._extract_seller(soup, product)
            product.seller_rating = self._extract_rating(soup, product)

            # Pricing — order matters
            product.price          = self._extract_price(soup, product)
            product.original_price = self._extract_original_price(soup, product)
            product.discount_pct   = self._calculate_discount(product)
            product.is_on_sale     = self._detect_sale(product)

            # Stock
            product.in_stock  = self._extract_stock(soup, product)
            product.stock_qty = self._extract_stock_qty(soup, product)

            # Post-parse enrichment
            self._enrich(product)

        except Exception as exc:
            logger.error(f"[parser] Fatal error parsing {url}: {exc}", exc_info=True)
            product.parse_errors.append(f"FATAL: {exc}")

        return product

    # ── Extractors ────────────────────────────────────────────────────────────

    def _extract_name(self, soup: BeautifulSoup, p: ParsedProduct) -> str:
        el = soup.select_one(self.config.sel_name)
        if not el:
            p.parse_errors.append("name: selector not found")
            return ""
        return self._clean_text(el.get_text())

    def _extract_price(self, soup: BeautifulSoup, p: ParsedProduct) -> Optional[float]:
        if not self.config.sel_price:
            p.parse_errors.append("price: no selector configured")
            return None

        el = soup.select_one(self.config.sel_price)
        if not el:
            p.parse_errors.append("price: element not found")
            return None

        raw = el.get_text()
        price = normalize_price(raw)
        if price is None:
            p.parse_errors.append(f"price: could not parse {raw!r}")
        return price

    def _extract_original_price(self, soup: BeautifulSoup, p: ParsedProduct) -> Optional[float]:
        if not self.config.sel_original_price:
            return None
        el = soup.select_one(self.config.sel_original_price)
        if not el:
            return None
        return normalize_price(el.get_text())

    def _extract_brand(self, soup: BeautifulSoup, p: ParsedProduct) -> Optional[str]:
        if not self.config.sel_brand:
            return None
        el = soup.select_one(self.config.sel_brand)
        return self._clean_text(el.get_text()) if el else None

    def _extract_category(self, soup: BeautifulSoup, p: ParsedProduct) -> Optional[str]:
        if not self.config.sel_category:
            return None
        items = soup.select(self.config.sel_category)
        if not items:
            return None
        parts = [self._clean_text(i.get_text()) for i in items if i.get_text(strip=True)]
        # Skip first crumb (usually "Home" or store name)
        return " > ".join(parts[1:]) if len(parts) > 1 else parts[0] if parts else None

    def _extract_description(self, soup: BeautifulSoup, p: ParsedProduct) -> Optional[str]:
        if not self.config.sel_description:
            return None
        els = soup.select(self.config.sel_description)
        if not els:
            return None
        text = " ".join(self._clean_text(e.get_text()) for e in els)
        return text[:2000] if text else None  # cap at 2000 chars

    def _extract_image(self, soup: BeautifulSoup, p: ParsedProduct) -> Optional[str]:
        if not self.config.sel_image:
            return None
        el = soup.select_one(self.config.sel_image)
        if not el:
            return None
        # Try data-src first (lazy-loaded images), then src
        return (
            el.get("data-zoom-image")
            or el.get("data-src")
            or el.get(self.config.image_attr)
        )

    def _extract_specs(self, soup: BeautifulSoup, p: ParsedProduct) -> dict:
        """
        Extracts technical specifications table as a dict.
        Supports <table> and lists of <tr><th>/<td>.
        """
        specs = {}
        if not self.config.sel_specs_table:
            return specs

        tables = soup.select(self.config.sel_specs_table)
        for table in tables:
            rows = table.select("tr")
            for row in rows:
                cells = row.select("th, td")
                if len(cells) == 2:
                    key = self._clean_text(cells[0].get_text())
                    val = self._clean_text(cells[1].get_text())
                    if key and val:
                        specs[key] = val
                elif len(cells) == 1:
                    # Some sites use definition lists inside tables
                    pass

        # Also try <ul> spec lists (some stores use this)
        if not specs:
            dl = soup.select("dl.ui-pdp-specs__item, dl.specs-list")
            for item in dl:
                dt = item.select_one("dt, .specs-item__label")
                dd = item.select_one("dd, .specs-item__value")
                if dt and dd:
                    specs[self._clean_text(dt.get_text())] = self._clean_text(dd.get_text())

        return specs

    def _extract_stock(self, soup: BeautifulSoup, p: ParsedProduct) -> bool:
        if not self.config.sel_stock:
            return True  # assume in stock if we can't tell

        el = soup.select_one(self.config.sel_stock)

        if self.config.stock_mode == "presence":
            return el is not None
        elif self.config.stock_mode == "absence":
            return el is None
        elif self.config.stock_mode == "text":
            if el is None:
                return True
            text = el.get_text().lower()
            return not any(w in text for w in self.config.stock_negative_words)

        return True

    def _extract_stock_qty(self, soup: BeautifulSoup, p: ParsedProduct) -> Optional[int]:
        if not self.config.sel_stock_qty:
            return None
        el = soup.select_one(self.config.sel_stock_qty)
        if not el:
            return None
        # Extract first integer found in text
        match = re.search(r"\d+", el.get_text())
        return int(match.group()) if match else None

    def _extract_seller(self, soup: BeautifulSoup, p: ParsedProduct) -> Optional[str]:
        if not self.config.sel_seller:
            return None
        el = soup.select_one(self.config.sel_seller)
        return self._clean_text(el.get_text()) if el else None

    def _extract_rating(self, soup: BeautifulSoup, p: ParsedProduct) -> Optional[float]:
        if not self.config.sel_rating:
            return None
        el = soup.select_one(self.config.sel_rating)
        if not el:
            return None
        raw = el.get(self.config.rating_attr) or el.get_text()
        match = re.search(r"[\d.]+", raw)
        if match:
            try:
                return float(match.group())
            except ValueError:
                pass
        return None

    # ── Enrichment ────────────────────────────────────────────────────────────

    def _calculate_discount(self, p: ParsedProduct) -> Optional[float]:
        """Calculates discount % if original price exists."""
        if p.price and p.original_price and p.original_price > p.price:
            pct = (p.original_price - p.price) / p.original_price * 100
            return round(pct, 1)
        return None

    def _detect_sale(self, p: ParsedProduct) -> bool:
        """A product is on sale if original price is greater than current price."""
        return (
            p.original_price is not None
            and p.price is not None
            and p.original_price > p.price
        )

    def _enrich(self, p: ParsedProduct):
        """
        Post-parse enrichment:
        - Extracts brand from name if not found in HTML
        - Normalizes currency symbol to ISO code
        - Sanity checks
        """
        # If no brand found but name has a token that looks like a brand
        if not p.brand and p.name:
            p.brand = _guess_brand_from_name(p.name)

        # Sanity: price cannot be greater than original
        if p.price and p.original_price and p.price > p.original_price:
            p.original_price = None
            p.discount_pct = None
            p.is_on_sale = False

        # Sanity: rating between 0 and 5
        if p.seller_rating and not (0 <= p.seller_rating <= 5):
            p.seller_rating = None

    # ── Utils ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _clean_text(text: str) -> str:
        """Normalizes whitespace and control characters."""
        return re.sub(r"\s+", " ", text or "").strip()

    @staticmethod
    def _normalize_name(name: str) -> str:
        """
        Normalized version of the name to compare products across stores.
        Example: "Laptop HP 15-dw3003la, Core i5" → "laptop hp 15 dw3003la core i5"
        """
        n = name.lower()
        n = re.sub(r"[^\w\s]", " ", n)   # remove punctuation
        n = re.sub(r"\s+", " ", n).strip()
        return n


# ── Standalone helpers ────────────────────────────────────────────────────────

# Known brands for guess_brand
_KNOWN_BRANDS = [
    "HP", "Dell", "Lenovo", "Apple", "Samsung", "Sony", "LG", "Asus",
    "Acer", "Toshiba", "MSI", "Huawei", "Xiaomi", "Motorola", "Nokia",
    "Canon", "Nikon", "Epson", "Brother", "Philips", "Panasonic",
    "Whirlpool", "Mabe", "Frigidaire", "Bosch", "Haier",
]
_BRAND_RE = re.compile(
    r"\b(" + "|".join(re.escape(b) for b in _KNOWN_BRANDS) + r")\b",
    re.IGNORECASE,
)


def _guess_brand_from_name(name: str) -> Optional[str]:
    """Searches for a known brand in the product name."""
    match = _BRAND_RE.search(name)
    return match.group(1).upper() if match else None


def normalize_price(raw: str | None) -> Optional[float]:
    """
    Standalone price normalization function.
    Accepts formats: "$1,299.99", "RD$4.500", "1.299,99", "42500"

    Can be imported directly without instantiating the parser:
        from parsers.product_parse import normalize_price
    """
    if not raw:
        return None

    raw = str(raw).strip()
    cleaned = re.sub(r"[^\d.,]", "", raw)

    if not cleaned:
        return None

    dot_count   = cleaned.count(".")
    comma_count = cleaned.count(",")

    if dot_count > 1:
        cleaned = cleaned.replace(".", "")
    elif comma_count > 1:
        cleaned = cleaned.replace(",", "")
    elif "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned and comma_count == 1:
        parts = cleaned.split(",")
        if len(parts[1]) <= 2:
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")

    try:
        return float(cleaned)
    except ValueError:
        logger.warning(f"[normalize_price] Could not parse: {raw!r}")
        return None


def normalize_currency(symbol: str) -> str:
    """Converts currency symbol to ISO 4217 code."""
    SYMBOL_MAP = {
        "RD$": "DOP", "$": "USD", "US$": "USD",
        "MX$": "MXN", "AR$": "ARS", "CL$": "CLP",
        "COP": "COP", "€": "EUR", "£": "GBP",
        "¥": "JPY", "R$": "BRL",
    }
    return SYMBOL_MAP.get(symbol.strip(), symbol.strip().upper())