# Price Intelligence System

E-commerce price intelligence and scraping system.

Monitors competitor prices, saves history, detects changes, and notifies when a competitor drops prices.

## Stack

- **Scrapy** — crawling and scraping
- **BeautifulSoup 4** — HTML parsing
- **FastAPI** — REST API (Day 4)
- **PostgreSQL + SQLAlchemy** — database (Day 3)
- **APScheduler** — automated tasks (Day 5)

## Project Structure

```text
price-intelligence/
├── spiders/              # Scrapy spiders
│   ├── base_spider.py    # Shared base class
│   ├── mercadolibre_spider.py
│   ├── generic_spider.py
│   ├── items.py          # Field definitions
│   └── pipelines.py      # Validation and export
├── parsers/              # (Day 2) BeautifulSoup parsers
├── db/                   # (Day 3) Models and migrations
├── api/                  # (Day 4) FastAPI endpoints
├── engine/               # (Day 5) Change detection
├── notifiers/            # (Day 6) Email and webhooks
├── dashboard/            # (Day 7) Web UI
├── config/
│   ├── settings.py       # Environment variables
│   └── scrapy_settings.py
├── tests/
├── output/               # Spiders JSON output (gitignored)
├── run_spider.py         # CLI runner
├── .env.example
└── requirements.txt
```

## Setup

### 1. Clone and create virtual environment

```bash
git clone https://github.com/ChandeDeVargas/price-intelligent-scrapy.git
cd price-intelligence

python -m venv venv
source venv/bin/activate   # Linux/Mac
venv\Scripts\activate      # Windows

pip install -r requirements.txt
```

### 2. Environment variables

```bash
cp .env.example .env
# Edit .env with your values
```

## Usage — Day 1

### Run the MercadoLibre spider

```bash
# Computing category, 2 pages
python run_spider.py mercadolibre --category computacion --max-pages 2

# Cellphones category
python run_spider.py mercadolibre --category celulares --max-pages 3

# From a specific URL
python run_spider.py mercadolibre --url "https://www.mercadolibre.com.do/..." --max-pages 1
```

### Run the generic spider

```bash
python run_spider.py generic \
  --url https://example.com/products \
  --store MyStore \
  --max-pages 2
```

### Or run Scrapy directly

```bash
# With Scrapy CLI directly
scrapy crawl mercadolibre -a category=computacion -a max_pages=2 \
  --set SCRAPY_SETTINGS_MODULE=config.scrapy_settings

# View output
cat output/mercadolibre.jsonl | python -m json.tool | head -60
```

### Run tests

```bash
pytest tests/test_spider.py -v
```

## Daily Progress

| Day | Module | Status |
|-----|--------|--------|
| 1 | Setup + Scrapy Spiders | ✅ |
| 2 | BeautifulSoup Parser | 🔜 |
| 3 | Database + History | 🔜 |
| 4 | FastAPI REST API | 🔜 |
| 5 | Price Engine + Scheduler | 🔜 |
| 6 | Notifications | 🔜 |
| 7 | Dashboard + Docker | 🔜 |

## Available Categories (MercadoLibre RD)

- `computacion`
- `celulares`
- `electrodomesticos`
- `tv-audio-video`

## Output

Each spider generates a `.jsonl` file in `output/`:

```json
{
  "url": "https://www.mercadolibre.com.do/...",
  "store": "MercadoLibre",
  "name": "Laptop HP 15 Core i5...",
  "sku": "MLM-XXXXXXX",
  "brand": "HP",
  "category": "Computación > Laptops",
  "price": 42500.0,
  "original_price": 48000.0,
  "currency": "DOP",
  "in_stock": true,
  "scraped_at": "2024-01-15T14:30:00+00:00",
  "spider_name": "mercadolibre"
}
```
