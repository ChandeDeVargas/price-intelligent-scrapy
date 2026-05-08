"""
DataCleaner — post-scrape cleaning pipeline.

Receives a ParsedProduct (or a dict from the spider) and applies a series of
transformations to ensure consistency before persisting to the DB.

Usage:
    from parsers.cleaner import DataCleaner
    cleaner = DataCleaner()
    clean = cleaner.clean(parsed_product)
"""

import re
import logging
from dataclasses import dataclass
from typing import Optional

from .product_parse import ParsedProduct, normalize_currency

logger = logging.getLogger(__name__)


# ── Cleaning result ───────────────────────────────────────────────────────────

@dataclass
class CleaningReport:
    """Cleaning result with a log of applied transformations."""
    product: ParsedProduct
    transformations: list[str]
    warnings: list[str]

    @property
    def was_modified(self) -> bool:
        return bool(self.transformations)


# ── Main cleaner ──────────────────────────────────────────────────────────────

class DataCleaner:
    """
    Cleaning pipeline for ParsedProduct.

    Each _clean_* method is independent and logs what changed.
    The order of application matters (price before discount, etc.)
    """

    # Reasonable maximum price for validation (avoid erroneous parsing)
    MAX_PRICE = 10_000_000
    MIN_PRICE = 0.01

    def clean(self, product: ParsedProduct) -> CleaningReport:
        """
        Applies all cleaning transformations to the product.
        Returns a CleaningReport with the cleaned product and the changelog.
        """
        transforms = []
        warnings = []

        def apply(fn, *args):
            result = fn(product, *args)
            if result:
                transforms.append(result)

        def warn(fn, *args):
            result = fn(product, *args)
            if result:
                warnings.append(result)

        # Text
        apply(self._clean_name)
        apply(self._clean_brand)
        apply(self._clean_category)
        apply(self._clean_description)

        # Price
        apply(self._clean_price_range)
        apply(self._clean_currency)
        apply(self._recalculate_discount)

        # Stock
        apply(self._normalize_stock)

        # Final validations
        warn(self._validate_required_fields)
        warn(self._validate_price_sanity)

        return CleaningReport(product=product, transformations=transforms, warnings=warnings)

    # ── Text cleaners ─────────────────────────────────────────────────────────

    def _clean_name(self, p: ParsedProduct) -> Optional[str]:
        if not p.name:
            return None
        original = p.name
        # Remove quotes and strange characters at the beginning/end
        cleaned = p.name.strip("\"'`")
        # Collapse spaces
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        # Capitalize if all uppercase
        if cleaned == cleaned.upper() and len(cleaned) > 5:
            cleaned = cleaned.title()
        p.name = cleaned
        p.name_normalized = re.sub(r"[^\w\s]", " ", cleaned.lower())
        p.name_normalized = re.sub(r"\s+", " ", p.name_normalized).strip()
        if cleaned != original:
            return f"name: '{original[:40]}' → '{cleaned[:40]}'"
        return None

    def _clean_brand(self, p: ParsedProduct) -> Optional[str]:
        if not p.brand:
            return None
        original = p.brand
        cleaned = p.brand.strip().title()
        # Remove common prefixes
        cleaned = re.sub(r"^(marca:|brand:|by\s+)", "", cleaned, flags=re.IGNORECASE).strip()
        p.brand = cleaned
        if cleaned != original:
            return f"brand: '{original}' → '{cleaned}'"
        return None

    def _clean_category(self, p: ParsedProduct) -> Optional[str]:
        if not p.category:
            return None
        original = p.category
        # Normalize separators
        cleaned = re.sub(r"\s*[>|/\\]\s*", " > ", p.category)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        p.category = cleaned
        if cleaned != original:
            return f"category normalized"
        return None

    def _clean_description(self, p: ParsedProduct) -> Optional[str]:
        if not p.description:
            return None
        original_len = len(p.description)
        # Remove residual HTML
        cleaned = re.sub(r"<[^>]+>", " ", p.description)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        # Cap
        if len(cleaned) > 2000:
            cleaned = cleaned[:2000] + "…"
        p.description = cleaned
        if len(cleaned) != original_len:
            return f"description: cleaned {original_len} → {len(cleaned)} chars"
        return None

    # ── Price cleaners ────────────────────────────────────────────────────────

    def _clean_price_range(self, p: ParsedProduct) -> Optional[str]:
        """Validates that the price is in a reasonable range."""
        if p.price is None:
            return None

        if p.price < self.MIN_PRICE:
            note = f"price {p.price} below min, set to None"
            p.price = None
            return note

        if p.price > self.MAX_PRICE:
            note = f"price {p.price} above max {self.MAX_PRICE}, set to None"
            p.price = None
            return note

        # Round to 2 decimals
        rounded = round(p.price, 2)
        if rounded != p.price:
            p.price = rounded
            return f"price rounded to {rounded}"

        return None

    def _clean_currency(self, p: ParsedProduct) -> Optional[str]:
        """Normalizes currency code to ISO 4217."""
        if not p.currency:
            p.currency = "USD"
            return "currency: defaulted to USD"

        normalized = normalize_currency(p.currency)
        if normalized != p.currency:
            old = p.currency
            p.currency = normalized
            return f"currency: '{old}' → '{normalized}'"
        return None

    def _recalculate_discount(self, p: ParsedProduct) -> Optional[str]:
        """Recalculates discount after cleaning prices."""
        if p.price and p.original_price:
            if p.original_price <= p.price:
                # Original price lower or equal: no real discount
                p.original_price = None
                p.discount_pct = None
                p.is_on_sale = False
                return "discount: original_price <= price, cleared"

            new_pct = round((p.original_price - p.price) / p.original_price * 100, 1)
            if new_pct != p.discount_pct:
                p.discount_pct = new_pct
                p.is_on_sale = True
                return f"discount: recalculated to {new_pct}%"
        return None

    # ── Stock cleaners ────────────────────────────────────────────────────────

    def _normalize_stock(self, p: ParsedProduct) -> Optional[str]:
        """If qty > 0, ensure in_stock = True."""
        if p.stock_qty is not None:
            if p.stock_qty <= 0 and p.in_stock:
                p.in_stock = False
                return "stock: qty=0, set in_stock=False"
            if p.stock_qty > 0 and not p.in_stock:
                p.in_stock = True
                return f"stock: qty={p.stock_qty}, set in_stock=True"
        return None

    # ── Validators ────────────────────────────────────────────────────────────

    def _validate_required_fields(self, p: ParsedProduct) -> Optional[str]:
        missing = []
        if not p.name:
            missing.append("name")
        if p.price is None:
            missing.append("price")
        if not p.url:
            missing.append("url")
        if missing:
            return f"WARNING: missing required fields: {', '.join(missing)}"
        return None

    def _validate_price_sanity(self, p: ParsedProduct) -> Optional[str]:
        if p.price and p.discount_pct:
            if p.discount_pct > 90:
                return f"WARNING: discount {p.discount_pct}% seems too high, verify"
            if p.discount_pct < 0:
                return f"WARNING: negative discount {p.discount_pct}%"
        return None
