"""
Scrapy settings for price_intelligence project.
"""

BOT_NAME = "price_intelligence"

SPIDER_MODULES = ["spiders"]
NEWSPIDER_MODULE = "spiders"

# ── Crawl responsibly ──────────────────────────────────────────────────────────
# Identify the bot — change this to your project/company name
USER_AGENT = "PriceIntelligenceBot/1.0 (+https://github.com/your-repo)"

# Rotate user agents (requires scrapy-user-agents)
DOWNLOADER_MIDDLEWARES = {
    "scrapy.downloadermiddlewares.useragent.UserAgentMiddleware": None,
    "scrapy_user_agents.middlewares.RandomUserAgentMiddleware": 400,
    "scrapy.downloadermiddlewares.retry.RetryMiddleware": 550,
}

# Obey robots.txt — set to False only for sites that allow it in their ToS
ROBOTSTXT_OBEY = True

# ── Rate limiting ──────────────────────────────────────────────────────────────
DOWNLOAD_DELAY = 2               # Seconds between requests to the same domain
RANDOMIZE_DOWNLOAD_DELAY = True  # Adds 0.5x–1.5x jitter to DOWNLOAD_DELAY
CONCURRENT_REQUESTS = 4
CONCURRENT_REQUESTS_PER_DOMAIN = 2
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 1
AUTOTHROTTLE_MAX_DELAY = 10
AUTOTHROTTLE_TARGET_CONCURRENCY = 2.0

# ── Retry ─────────────────────────────────────────────────────────────────────
RETRY_ENABLED = True
RETRY_TIMES = 3
RETRY_HTTP_CODES = [429, 500, 502, 503, 504]

# ── Output ────────────────────────────────────────────────────────────────────
FEEDS = {
    "output/%(name)s_%(time)s.json": {
        "format": "json",
        "encoding": "utf8",
        "indent": 2,
        "overwrite": False,
    }
}

# ── Item pipelines ─────────────────────────────────────────────────────────────
ITEM_PIPELINES = {
    "spiders.pipelines.ValidatePipeline": 100,
    "spiders.pipelines.DuplicateFilterPipeline": 200,
    "spiders.pipelines.JsonExportPipeline": 900,
}

# ── HTTP cache (useful during development) ─────────────────────────────────────
HTTPCACHE_ENABLED = False        # Enable during dev to avoid hammering sites
HTTPCACHE_EXPIRATION_SECS = 3600
HTTPCACHE_DIR = ".scrapy/httpcache"

# ── Logging ────────────────────────────────────────────────────────────────────
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"

# ── Request fingerprinting ─────────────────────────────────────────────────────
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
FEED_EXPORT_ENCODING = "utf-8"