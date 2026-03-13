#!/usr/bin/env python3
"""
实际 URL 集成测试脚本
测试美团闪购和京东秒送采集器对真实网页的采集能力
"""

import asyncio
import sys
import logging
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from price_monitor.config import Config
from price_monitor.models import ScrapeTask, Platform
from price_monitor.pipeline import DataPipeline
from price_monitor.screenshot import PriceScreenshot
from price_monitor.account_pool import AccountPool
from price_monitor.scrapers.meituan_flash import MeituanFlashScraper
from price_monitor.scrapers.jd_express import JDExpressScraper

logging.basicConfig(
    level=logging.DEBUG,
    format="[%(asctime)s] %(name)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("test")


async def test_jd_express():
    """测试京东秒送采集器 — 使用真实京东商品 URL"""
    log.info("=" * 60)
    log.info("TEST: JD Express Scraper (StealthyFetcher)")
    log.info("=" * 60)

    config = Config.from_env()
    pipeline = DataPipeline(output_dir="/tmp/pm_test/output")
    screenshot = PriceScreenshot(output_dir="/tmp/pm_test/screenshots")

    scraper = JDExpressScraper(
        config=config,
        pipeline=pipeline,
        screenshot=screenshot,
    )

    # 京东公开商品页 (不需要登录的基本信息)
    test_urls = [
        # 京东自营商品 (通常有丰富的价格和优惠券信息)
        "https://item.jd.com/100012043978.html",  # 电子产品
    ]

    for url in test_urls:
        log.info(f"\n--- Testing URL: {url} ---")
        task = ScrapeTask(
            task_id="test_jd_1",
            platform=Platform.JD_EXPRESS,
            product_url=url,
        )

        result = await scraper.scrape_product(task)

        if result:
            log.info(f"  Product: {result.product_name}")
            log.info(f"  Current Price: ¥{result.current_price}")
            log.info(f"  Original Price: ¥{result.original_price}")
            log.info(f"  Final Price: ¥{result.final_price}")
            log.info(f"  Shop: {result.shop_name}")
            log.info(f"  Ship From: {result.ship_from_city}")
            log.info(f"  Coupons: {len(result.coupons)}")
            for c in result.coupons:
                log.info(f"    - [{c.coupon_type.value}] {c.description}")
            log.info(f"  Screenshot: {result.screenshot_local}")

            pipeline.save_item(result)
            log.info("  STATUS: SUCCESS ✅")
        else:
            log.warning("  STATUS: FAILED ❌ (no data returned)")

    if pipeline.pending_count > 0:
        filepath = pipeline.flush_to_json("jd_test_results.json")
        log.info(f"\nResults saved to: {filepath}")


async def test_meituan_flash():
    """测试美团闪购采集器 — 使用 Fetcher HTTP 请求"""
    log.info("=" * 60)
    log.info("TEST: Meituan Flash Scraper (Fetcher HTTP)")
    log.info("=" * 60)

    config = Config.from_env()
    pipeline = DataPipeline(output_dir="/tmp/pm_test/output")
    screenshot = PriceScreenshot(output_dir="/tmp/pm_test/screenshots")

    scraper = MeituanFlashScraper(
        config=config,
        pipeline=pipeline,
        screenshot=screenshot,
    )

    # 美团闪购 H5 页面 (测试 HTTP 请求 + 页面解析)
    test_urls = [
        "https://h5.waimai.meituan.com/waimai/mindex/home",
    ]

    for url in test_urls:
        log.info(f"\n--- Testing URL: {url} ---")
        task = ScrapeTask(
            task_id="test_mt_1",
            platform=Platform.MEITUAN_FLASH,
            product_url=url,
        )

        result = await scraper.scrape_product(task)

        if result:
            log.info(f"  Product: {result.product_name}")
            log.info(f"  Price: ¥{result.current_price}")
            log.info(f"  Shop: {result.shop_name}")
            log.info(f"  Ship From: {result.ship_from_city}")
            pipeline.save_item(result)
            log.info("  STATUS: SUCCESS ✅")
        else:
            log.warning("  STATUS: FAILED ❌ (no data returned)")
            log.info("  NOTE: Meituan requires geolocation params, expected for this test")

    if pipeline.pending_count > 0:
        filepath = pipeline.flush_to_json("meituan_test_results.json")
        log.info(f"\nResults saved to: {filepath}")


async def test_jd_fetcher_direct():
    """直接使用 Scrapling Fetcher 测试京东页面 (不走 StealthyFetcher)"""
    log.info("=" * 60)
    log.info("TEST: JD Direct Fetcher (HTTP only, no browser)")
    log.info("=" * 60)

    from scrapling.fetchers import Fetcher

    url = "https://item.m.jd.com/product/100012043978.html"
    log.info(f"Fetching: {url}")

    try:
        page = Fetcher.get(
            url,
            impersonate="chrome",
            stealthy_headers=True,
            timeout=15,
        )
        log.info(f"  Status: {page.status}")
        log.info(f"  URL: {page.url}")
        log.info(f"  Body length: {len(page.body)} bytes")

        # 尝试解析
        title = page.css("title")
        if title:
            log.info(f"  Page title: {title.css('::text').get('')}")

        # 查找价格相关元素
        price_els = page.css('[class*="price"]')
        log.info(f"  Price-related elements found: {len(price_els)}")
        for i, el in enumerate(price_els[:5]):
            text = el.get_all_text(strip=True)
            if text:
                log.info(f"    [{i}] {el.tag}.{el.attrib.get('class', '')} => '{text[:80]}'")

        # 查找商品名称
        name_els = page.css(".sku-name, .product-name, h1, [class*='title']")
        log.info(f"  Name elements found: {len(name_els)}")
        for i, el in enumerate(name_els[:3]):
            text = el.get_all_text(strip=True)
            if text:
                log.info(f"    [{i}] => '{text[:100]}'")

        # 查找店铺名称
        shop_els = page.css("[class*='shop'], [class*='store']")
        log.info(f"  Shop elements found: {len(shop_els)}")
        for i, el in enumerate(shop_els[:3]):
            text = el.get_all_text(strip=True)
            if text:
                log.info(f"    [{i}] => '{text[:80]}'")

        log.info("  STATUS: FETCHER OK ✅")
        return True

    except Exception as e:
        log.error(f"  Error: {e}")
        log.info("  STATUS: FETCHER FAILED ❌")
        return False


async def main():
    log.info("Starting integration tests...")
    log.info(f"Output dir: /tmp/pm_test/")

    # Test 1: Direct HTTP fetch of JD (fastest, validates Scrapling Fetcher)
    await test_jd_fetcher_direct()

    # Test 2: Meituan Flash (HTTP API)
    await test_meituan_flash()

    # Test 3: JD Express with StealthyFetcher (needs browser)
    # Uncomment when Playwright browsers are installed:
    # await test_jd_express()
    log.info("\n[SKIP] JD StealthyFetcher test (requires 'scrapling install' for browser)")
    log.info("  Run: /opt/miniconda3/bin/python -m playwright install chromium")
    log.info("  Then uncomment test_jd_express() in this script")

    log.info("\n" + "=" * 60)
    log.info("Integration tests complete!")


if __name__ == "__main__":
    asyncio.run(main())
