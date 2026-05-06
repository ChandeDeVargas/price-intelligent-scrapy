#!/usr/bin/env python3
"""
CLI para ejecutar spiders manualmente.

Uso:
    python run_spider.py mercadolibre --category computacion --max-pages 2
    python run_spider.py mercadolibre --category celulares
    python run_spider.py generic --url https://example.com --store MyStore

El output se guarda en output/<spider_name>.jsonl
"""
import argparse
import logging
import subprocess
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("run_spider")

SPIDERS = ["mercadolibre", "generic"]


def build_scrapy_command(spider: str, args: argparse.Namespace) -> list[str]:
    cmd = ["scrapy", "crawl", spider, "--set", "SCRAPY_SETTINGS_MODULE=config.scrapy_settings"]

    if spider == "mercadolibre":
        if args.category:
            cmd += ["-a", f"category={args.category}"]
        if args.url:
            cmd += ["-a", f"url={args.url}"]
        if args.max_pages:
            cmd += ["-a", f"max_pages={args.max_pages}"]

    elif spider == "generic":
        if not args.url:
            logger.error("Generic spider requires --url")
            sys.exit(1)
        cmd += ["-a", f"start_url={args.url}"]
        if args.store:
            cmd += ["-a", f"store={args.store}"]
        if args.max_pages:
            cmd += ["-a", f"max_pages={args.max_pages}"]
        if args.sel_name:
            cmd += ["-a", f"sel_name={args.sel_name}"]
        if args.sel_price:
            cmd += ["-a", f"sel_price={args.sel_price}"]
        if args.sel_links:
            cmd += ["-a", f"sel_links={args.sel_links}"]

    return cmd


def main():
    parser = argparse.ArgumentParser(
        description="Price Intelligence — Spider Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python run_spider.py mercadolibre --category computacion --max-pages 2
  python run_spider.py mercadolibre --category celulares
  python run_spider.py generic --url https://example.com --store MiTienda
        """,
    )

    parser.add_argument("spider", choices=SPIDERS, help="Spider a ejecutar")
    parser.add_argument("--url", help="URL de inicio (requerida para generic)")
    parser.add_argument("--category", default="computacion", help="Categoría (mercadolibre)")
    parser.add_argument("--store", help="Nombre de la tienda (generic)")
    parser.add_argument("--max-pages", dest="max_pages", type=int, default=2)
    parser.add_argument("--sel-name", dest="sel_name", help="CSS selector para nombre")
    parser.add_argument("--sel-price", dest="sel_price", help="CSS selector para precio")
    parser.add_argument("--sel-links", dest="sel_links", help="CSS selector para links de productos")

    args = parser.parse_args()

    cmd = build_scrapy_command(args.spider, args)

    logger.info(f"Ejecutando: {' '.join(cmd)}")
    logger.info(f"Output → output/{args.spider}.jsonl\n")

    result = subprocess.run(cmd, cwd=".")

    if result.returncode == 0:
        logger.info("✓ Spider terminó exitosamente")
        logger.info(f"Revisa el output en: output/{args.spider}.jsonl")
    else:
        logger.error(f"✗ Spider falló con código {result.returncode}")
        sys.exit(result.returncode)


if __name__ == "__main__":
    main()
