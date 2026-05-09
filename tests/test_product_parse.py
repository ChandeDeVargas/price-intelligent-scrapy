"""
Tests — Día 2: ProductParser, DataCleaner y funciones de normalización.

Ejecutar:
    pytest tests/test_day2.py -v
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from parsers.product_parse import (
    ProductParser,
    ParsedProduct,
    StoreConfig,
    STORE_CONFIGS,
    normalize_price,
    normalize_currency,
    _guess_brand_from_name,
)
from parsers.cleaner import DataCleaner, CleaningReport


# ── HTML fixtures ──────────────────────────────────────────────────────────────

def make_ml_html(
    name="Laptop HP 15-dw3003la Core i5",
    price="42,500",
    original_price=None,
    currency_symbol="RD$",
    has_buy_button=True,
    brand="HP",
    category_crumbs=("MercadoLibre", "Computación", "Laptops"),
    description="Procesador Intel Core i5 de 11a generación.",
    specs=(("Procesador", "Intel Core i5"), ("RAM", "8 GB")),
    seller="TechStore RD",
    stock_qty="5",
    image_url="https://img.ml.com/product.jpg",
):
    """Genera HTML mínimo que imita la estructura de MercadoLibre."""

    crumbs_html = "".join(
        f'<li class="andes-breadcrumb__item"><a href="#">{c}</a></li>'
        for c in category_crumbs
    )

    orig_html = (
        f'<s><span class="andes-money-amount__fraction">{original_price}</span></s>'
        if original_price
        else ""
    )

    buy_btn = '<button class="ui-pdp-action--primary">Comprar ahora</button>' if has_buy_button else ""

    spec_rows = "".join(
        f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in (specs or [])
    )

    return f"""
    <html><body>
        <h1 class="ui-pdp-title">{name}</h1>

        <span class="andes-money-amount__currency-symbol">{currency_symbol}</span>
        <span class="andes-money-amount__fraction">{price}</span>
        {orig_html}

        {buy_btn}

        <span class="ui-pdp-color--BLACK ui-pdp-size--XSMALL">{brand}</span>

        <ol class="andes-breadcrumb">
            {crumbs_html}
        </ol>

        <div class="ui-pdp-description__content">
            <p>{description}</p>
        </div>

        <figure class="ui-pdp-gallery__figure">
            <img src="{image_url}" alt="product"/>
        </figure>

        <table class="andes-table">
            <tbody>{spec_rows}</tbody>
        </table>

        <span class="ui-pdp-seller__header__title">{seller}</span>

        <span class="ui-pdp-buybox__quantity__available">{stock_qty} disponibles</span>
    </body></html>
    """


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def ml_config():
    return STORE_CONFIGS["mercadolibre"]


@pytest.fixture
def ml_parser(ml_config):
    return ProductParser(ml_config)


@pytest.fixture
def cleaner():
    return DataCleaner()


@pytest.fixture
def basic_html():
    return make_ml_html()


@pytest.fixture
def sale_html():
    return make_ml_html(price="38,000", original_price="48,000")


@pytest.fixture
def out_of_stock_html():
    return make_ml_html(has_buy_button=False)


# ── normalize_price ────────────────────────────────────────────────────────────

class TestNormalizePrice:

    def test_integer_string(self):
        assert normalize_price("42500") == 42500.0

    def test_us_format(self):
        assert normalize_price("1,299.99") == 1299.99

    def test_european_format(self):
        assert normalize_price("1.299,99") == 1299.99

    def test_with_currency_prefix(self):
        assert normalize_price("RD$4500") == 4500.0

    def test_multiple_dots(self):
        assert normalize_price("1.299.999") == 1299999.0

    def test_multiple_commas(self):
        assert normalize_price("1,299,999") == 1299999.0

    def test_none_returns_none(self):
        assert normalize_price(None) is None

    def test_empty_returns_none(self):
        assert normalize_price("") is None

    def test_non_numeric_returns_none(self):
        assert normalize_price("N/A") is None

    def test_comma_decimal_2_digits(self):
        assert normalize_price("1299,99") == 1299.99

    def test_simple_decimal(self):
        assert normalize_price("99.99") == 99.99


# ── normalize_currency ────────────────────────────────────────────────────────

class TestNormalizeCurrency:

    def test_rd_symbol(self):
        assert normalize_currency("RD$") == "DOP"

    def test_dollar_symbol(self):
        assert normalize_currency("$") == "USD"

    def test_euro_symbol(self):
        assert normalize_currency("€") == "EUR"

    def test_mx_symbol(self):
        assert normalize_currency("MX$") == "MXN"

    def test_unknown_passthrough(self):
        assert normalize_currency("XYZ") == "XYZ"

    def test_strips_spaces(self):
        assert normalize_currency(" RD$ ") == "DOP"


# ── ProductParser ──────────────────────────────────────────────────────────────

class TestProductParser:

    def test_extracts_name(self, ml_parser, basic_html):
        result = ml_parser.parse(basic_html, url="https://ml.com/test")
        assert result.name == "Laptop HP 15-dw3003la Core i5"

    def test_extracts_price(self, ml_parser, basic_html):
        result = ml_parser.parse(basic_html, url="https://ml.com/test")
        assert result.price == 42500.0

    def test_extracts_currency(self, ml_parser, basic_html):
        result = ml_parser.parse(basic_html, url="https://ml.com/test")
        # Symbol RD$ should be in the parsed html; parser reads it
        assert result.currency in ("DOP", "RD$")

    def test_extracts_brand(self, ml_parser, basic_html):
        result = ml_parser.parse(basic_html, url="https://ml.com/test")
        assert result.brand == "HP"

    def test_extracts_category(self, ml_parser, basic_html):
        result = ml_parser.parse(basic_html, url="https://ml.com/test")
        # Skips first crumb "MercadoLibre"
        assert "Computación" in result.category
        assert "Laptops" in result.category

    def test_extracts_description(self, ml_parser, basic_html):
        result = ml_parser.parse(basic_html, url="https://ml.com/test")
        assert "Intel Core i5" in result.description

    def test_extracts_image(self, ml_parser, basic_html):
        result = ml_parser.parse(basic_html, url="https://ml.com/test")
        assert result.image_url == "https://img.ml.com/product.jpg"

    def test_extracts_specs(self, ml_parser, basic_html):
        result = ml_parser.parse(basic_html, url="https://ml.com/test")
        assert result.specs.get("Procesador") == "Intel Core i5"
        assert result.specs.get("RAM") == "8 GB"

    def test_extracts_seller(self, ml_parser, basic_html):
        result = ml_parser.parse(basic_html, url="https://ml.com/test")
        assert result.seller_name == "TechStore RD"

    def test_extracts_stock_qty(self, ml_parser, basic_html):
        result = ml_parser.parse(basic_html, url="https://ml.com/test")
        assert result.stock_qty == 5

    def test_in_stock_true_when_button_present(self, ml_parser, basic_html):
        result = ml_parser.parse(basic_html, url="https://ml.com/test")
        assert result.in_stock is True

    def test_out_of_stock_when_button_absent(self, ml_parser, out_of_stock_html):
        result = ml_parser.parse(out_of_stock_html, url="https://ml.com/test")
        assert result.in_stock is False

    def test_name_normalized(self, ml_parser, basic_html):
        result = ml_parser.parse(basic_html, url="https://ml.com/test")
        assert result.name_normalized == result.name_normalized.lower()
        assert "," not in result.name_normalized

    def test_stores_url(self, ml_parser, basic_html):
        url = "https://www.mercadolibre.com.do/laptop/MLM-123"
        result = ml_parser.parse(basic_html, url=url)
        assert result.url == url

    def test_stores_sku(self, ml_parser, basic_html):
        result = ml_parser.parse(basic_html, url="https://ml.com/test", sku="MLM-123456")
        assert result.sku == "MLM-123456"

    def test_scraped_at_is_set(self, ml_parser, basic_html):
        result = ml_parser.parse(basic_html, url="https://ml.com/test")
        assert result.scraped_at != ""
        assert "T" in result.scraped_at  # ISO format

    def test_is_valid_with_name_and_price(self, ml_parser, basic_html):
        result = ml_parser.parse(basic_html, url="https://ml.com/test")
        assert result.is_valid

    def test_is_invalid_without_name(self, ml_parser):
        html = make_ml_html(name="")
        result = ml_parser.parse(html, url="https://ml.com/test")
        assert not result.is_valid

    def test_empty_specs_when_no_table(self, ml_parser):
        html = make_ml_html(specs=[])
        result = ml_parser.parse(html, url="https://ml.com/test")
        assert isinstance(result.specs, dict)


# ── Sale detection ─────────────────────────────────────────────────────────────

class TestSaleDetection:

    def test_is_on_sale_when_original_price_higher(self, ml_parser, sale_html):
        result = ml_parser.parse(sale_html, url="https://ml.com/test")
        assert result.is_on_sale is True

    def test_discount_pct_calculated(self, ml_parser, sale_html):
        result = ml_parser.parse(sale_html, url="https://ml.com/test")
        # 38000 / 48000 = ~20.8% off
        assert result.discount_pct is not None
        assert 15 < result.discount_pct < 30

    def test_not_on_sale_without_original_price(self, ml_parser, basic_html):
        result = ml_parser.parse(basic_html, url="https://ml.com/test")
        assert result.is_on_sale is False
        assert result.discount_pct is None


# ── DataCleaner ───────────────────────────────────────────────────────────────

class TestDataCleaner:

    def _make_product(self, **kwargs) -> ParsedProduct:
        defaults = dict(
            url="https://example.com/product",
            store="Test",
            name="LAPTOP HP 15",
            price=42500.0,
            currency="RD$",
            in_stock=True,
            scraped_at="2024-01-01T00:00:00+00:00",
        )
        defaults.update(kwargs)
        return ParsedProduct(**defaults)

    def test_returns_cleaning_report(self, cleaner):
        p = self._make_product()
        report = cleaner.clean(p)
        assert isinstance(report, CleaningReport)

    def test_normalizes_currency_symbol(self, cleaner):
        p = self._make_product(currency="RD$")
        report = cleaner.clean(p)
        assert report.product.currency == "DOP"
        assert any("currency" in t for t in report.transformations)

    def test_title_case_for_allcaps_name(self, cleaner):
        p = self._make_product(name="LAPTOP HP 15 CORE I5")
        cleaner.clean(p)
        assert p.name == "Laptop Hp 15 Core I5"

    def test_removes_quotes_from_name(self, cleaner):
        p = self._make_product(name='"Laptop HP 15"')
        cleaner.clean(p)
        assert not p.name.startswith('"')

    def test_rounds_price_to_2_decimals(self, cleaner):
        p = self._make_product(price=42500.999)
        cleaner.clean(p)
        assert p.price == 42501.0

    def test_clears_original_price_if_less_than_price(self, cleaner):
        p = self._make_product(price=500.0, original_price=400.0)
        report = cleaner.clean(p)
        assert p.original_price is None
        assert p.discount_pct is None
        assert p.is_on_sale is False

    def test_recalculates_discount(self, cleaner):
        p = self._make_product(price=38000.0, original_price=48000.0)
        cleaner.clean(p)
        assert p.discount_pct is not None
        assert p.is_on_sale is True

    def test_sets_in_stock_false_when_qty_zero(self, cleaner):
        p = self._make_product(stock_qty=0, in_stock=True)
        cleaner.clean(p)
        assert p.in_stock is False

    def test_sets_in_stock_true_when_qty_positive(self, cleaner):
        p = self._make_product(stock_qty=5, in_stock=False)
        cleaner.clean(p)
        assert p.in_stock is True

    def test_warns_on_missing_name(self, cleaner):
        p = self._make_product(name="")
        report = cleaner.clean(p)
        assert any("name" in w for w in report.warnings)

    def test_cleans_description_html(self, cleaner):
        p = self._make_product(description="<p>Procesador <b>Intel</b> i5</p>")
        cleaner.clean(p)
        assert "<" not in p.description

    def test_caps_description_at_2000_chars(self, cleaner):
        p = self._make_product(description="x" * 3000)
        cleaner.clean(p)
        assert len(p.description) <= 2001  # 2000 + "…"

    def test_was_modified_flag(self, cleaner):
        p = self._make_product(currency="RD$")
        report = cleaner.clean(p)
        assert report.was_modified is True

    def test_normalizes_category_separators(self, cleaner):
        p = self._make_product(category="Computación/Laptops/HP")
        cleaner.clean(p)
        assert "/" not in p.category
        assert ">" in p.category


# ── Brand guesser ─────────────────────────────────────────────────────────────

class TestGuessBrand:

    def test_finds_hp(self):
        assert _guess_brand_from_name("Laptop HP 15 Core i5") == "HP"

    def test_finds_samsung(self):
        assert _guess_brand_from_name("Samsung Galaxy S23 Ultra") == "SAMSUNG"

    def test_case_insensitive(self):
        assert _guess_brand_from_name("laptop dell xps 15") == "DELL"

    def test_returns_none_if_not_found(self):
        assert _guess_brand_from_name("Producto genérico sin marca") is None


# ── ParsedProduct.to_dict ─────────────────────────────────────────────────────

class TestParsedProductToDict:

    def test_to_dict_contains_all_keys(self, ml_parser, basic_html):
        result = ml_parser.parse(basic_html, url="https://ml.com/test")
        d = result.to_dict()
        expected_keys = [
            "url", "store", "sku", "name", "name_normalized", "brand",
            "category", "description", "image_url", "specs", "price",
            "original_price", "currency", "discount_pct", "is_on_sale",
            "in_stock", "stock_qty", "seller_name", "seller_rating", "scraped_at",
            "parse_errors",
        ]
        for key in expected_keys:
            assert key in d, f"Missing key: {key}"

    def test_to_dict_serializable(self, ml_parser, basic_html):
        import json
        result = ml_parser.parse(basic_html, url="https://ml.com/test")
        d = result.to_dict()
        # Should not raise
        json.dumps(d)
