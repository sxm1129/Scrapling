#!/usr/bin/env python3
"""
全平台电商价格监控系统 — 主入口

Usage:
    # 单商品采集示例
    python -m price_monitor.main --platform meituan_flash --url "https://..."

    # 批量任务
    python -m price_monitor.main --tasks tasks.json
"""

import asyncio
import argparse
import logging
import sys
from typing import Optional

from price_monitor.config import Config
from price_monitor.models import ScrapeTask, Platform
from price_monitor.pipeline import DataPipeline
from price_monitor.screenshot import PriceScreenshot
from price_monitor.account_pool import AccountPool

# 平台采集器注册表
SCRAPER_REGISTRY: dict = {}


def _register_scrapers():
    """延迟注册所有采集器 (避免循环导入)"""
    from price_monitor.scrapers.meituan_flash import MeituanFlashScraper
    from price_monitor.scrapers.jd_express import JDExpressScraper

    SCRAPER_REGISTRY[Platform.MEITUAN_FLASH] = MeituanFlashScraper
    SCRAPER_REGISTRY[Platform.JD_EXPRESS] = JDExpressScraper
    # Phase 2/3 的采集器在实现后在此注册:
    # SCRAPER_REGISTRY[Platform.TAOBAO] = TaobaoScraper
    # SCRAPER_REGISTRY[Platform.TMALL] = TmallScraper
    # SCRAPER_REGISTRY[Platform.DOUYIN] = DouyinScraper
    # etc.


def setup_logging(level: int = logging.INFO):
    """配置日志"""
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] %(name)s %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


async def run_single(
    platform_name: str,
    url: str,
    config: Config,
) -> bool:
    """运行单个采集任务"""
    try:
        platform = Platform(platform_name)
    except ValueError:
        logging.error(f"Unknown platform: {platform_name}")
        logging.info(f"Supported: {[p.value for p in Platform]}")
        return False

    if platform not in SCRAPER_REGISTRY:
        logging.error(f"Scraper not implemented for: {platform_name}")
        logging.info(f"Implemented: {[p.value for p in SCRAPER_REGISTRY]}")
        return False

    pipeline = DataPipeline(output_dir="./output")
    screenshot = PriceScreenshot(output_dir="./screenshots")
    account_pool = AccountPool(pool_file="./accounts.json")

    scraper_class = SCRAPER_REGISTRY[platform]
    scraper = scraper_class(
        config=config,
        pipeline=pipeline,
        screenshot=screenshot,
        account_pool=account_pool,
    )

    task = ScrapeTask(
        task_id="manual_1",
        platform=platform,
        product_url=url,
    )

    success = await scraper.run_task(task)

    if pipeline.pending_count > 0:
        filepath = pipeline.flush_to_json()
        logging.info(f"Results saved to: {filepath}")

    return success


def main():
    parser = argparse.ArgumentParser(description="全平台电商价格监控系统")
    parser.add_argument("--platform", "-p", help="目标平台 (如: meituan_flash, jd_express)")
    parser.add_argument("--url", "-u", help="商品 URL")
    parser.add_argument("--tasks", "-t", help="批量任务文件 (JSON)")
    parser.add_argument("--output", "-o", default="./output", help="输出目录")
    parser.add_argument("--debug", action="store_true", help="开启 DEBUG 日志")
    parser.add_argument("--list-platforms", action="store_true", help="列出所有支持平台")

    args = parser.parse_args()

    setup_logging(logging.DEBUG if args.debug else logging.INFO)
    _register_scrapers()

    if args.list_platforms:
        print("\n支持的平台:")
        for p in Platform:
            status = "✅ 已实现" if p in SCRAPER_REGISTRY else "⏳ 待实现"
            print(f"  {p.value:20s} {status}")
        return

    if args.platform and args.url:
        config = Config.from_env()
        success = asyncio.run(run_single(args.platform, args.url, config))
        sys.exit(0 if success else 1)

    parser.print_help()


if __name__ == "__main__":
    main()
