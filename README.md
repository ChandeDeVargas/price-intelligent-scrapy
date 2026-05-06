# Price Intelligence System

Sistema de scraping e inteligencia de precios para e-commerce.

Monitorea precios de competidores, guarda historial, detecta cambios y notifica cuando un competidor baja precios.

## Stack

- **Scrapy** — crawling y scraping
- **BeautifulSoup 4** — parsing HTML
- **FastAPI** — API REST (Día 4)
- **PostgreSQL + SQLAlchemy** — base de datos (Día 3)
- **APScheduler** — tareas automáticas (Día 5)

## Estructura del proyecto

```
price-intelligence/
├── spiders/              # Scrapy spiders
│   ├── base_spider.py    # Clase base compartida
│   ├── mercadolibre_spider.py
│   ├── generic_spider.py
│   ├── items.py          # Definición de campos
│   └── pipelines.py      # Validación y export
├── parsers/              # (Día 2) BeautifulSoup parsers
├── db/                   # (Día 3) Modelos y migraciones
├── api/                  # (Día 4) FastAPI endpoints
├── engine/               # (Día 5) Detección de cambios
├── notifiers/            # (Día 6) Email y webhooks
├── dashboard/            # (Día 7) UI web
├── config/
│   ├── settings.py       # Variables de entorno
│   └── scrapy_settings.py
├── tests/
├── output/               # JSON output de spiders (gitignored)
├── run_spider.py         # CLI runner
├── .env.example
└── requirements.txt
```

## Setup

### 1. Clonar y crear entorno virtual

```bash
git clone https://github.com/tu-usuario/price-intelligence.git
cd price-intelligence

python -m venv venv
source venv/bin/activate   # Linux/Mac
venv\Scripts\activate      # Windows

pip install -r requirements.txt
```

### 2. Variables de entorno

```bash
cp .env.example .env
# Editar .env con tus valores
```

## Uso — Día 1

### Correr el spider de MercadoLibre

```bash
# Categoría de computación, 2 páginas
python run_spider.py mercadolibre --category computacion --max-pages 2

# Categoría de celulares
python run_spider.py mercadolibre --category celulares --max-pages 3

# Desde una URL específica
python run_spider.py mercadolibre --url "https://www.mercadolibre.com.do/..." --max-pages 1
```

### Correr el spider genérico

```bash
python run_spider.py generic \
  --url https://example.com/products \
  --store MiTienda \
  --max-pages 2
```

### O con Scrapy directamente

```bash
# Con Scrapy CLI directamente
scrapy crawl mercadolibre -a category=computacion -a max_pages=2 \
  --set SCRAPY_SETTINGS_MODULE=config.scrapy_settings

# Ver output
cat output/mercadolibre.jsonl | python -m json.tool | head -60
```

### Correr tests

```bash
pytest tests/test_day1.py -v
```

## Progreso por día

| Día | Módulo | Estado |
|-----|--------|--------|
| 1 | Setup + Scrapy Spiders | ✅ |
| 2 | BeautifulSoup Parser | 🔜 |
| 3 | Base de datos + Historial | 🔜 |
| 4 | FastAPI REST API | 🔜 |
| 5 | Price Engine + Scheduler | 🔜 |
| 6 | Notificaciones | 🔜 |
| 7 | Dashboard + Docker | 🔜 |

## Categorías disponibles (MercadoLibre RD)

- `computacion`
- `celulares`
- `electrodomesticos`
- `tv-audio-video`

## Output

Cada spider genera un archivo `.jsonl` en `output/`:

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
