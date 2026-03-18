"""
meituan_flash.py — 美团闪购 Playwright 行为仿真采集器
======================================================
策略:
  美团闪购 H5 页面（h5.meituan.com/meishi/flash）
  - 需要地理位置（已在 BrowserFactory 注入 geolocation）
  - 拦截 API 接口（/api/retail/search）作为主要数据来源
  - DOM 提取作为 fallback
"""
import asyncio
import json
import logging
import re
from decimal import Decimal
from urllib.parse import quote
from typing import Optional

from price_monitor.playwright_engine.base_scraper import (
    BasePlaywrightScraper, ProductDetail, SearchResult, CouponDetail
)

log = logging.getLogger("price_monitor.playwright_engine.scrapers.meituan_flash")

_FLASH_URL = "https://h5.meituan.com/search/keyword/?keyword={keyword}&cat=all"
_HOME_URL = "https://h5.meituan.com/retail/"


class MeituanFlashPlaywrightScraper(BasePlaywrightScraper):
    """
    美团闪购 Playwright 采集器
    依赖 BrowserFactory 注入 geolocation（上海坐标，可在 browser.py 修改）
    """
    platform = "meituan_flash"
    login_page_indicators = ["passport.meituan.com", "login", "passport"]

    async def search(self, page, keyword: str, human, limit: int = 10) -> list[SearchResult]:
        search_url = _FLASH_URL.format(keyword=quote(keyword))
        log.info(f"[meituan] Searching: {search_url}")

        captured_items: list[dict] = []

        async def capture_response(response):
            try:
                url = response.url
                ctype = response.headers.get("content-type", "")
                if "/search" in url or "/retail" in url or "suggest" in url:
                    if "json" in ctype:
                        body = await response.json()
                        # 美团接口结构: data.list / data.items
                        items = (
                            body.get("data", {}).get("list") or
                            body.get("data", {}).get("items") or
                            body.get("result", {}).get("list") or
                            []
                        )
                        if items:
                            log.info(f"[meituan] API captured {len(items)} items from {url[:80]}")
                            captured_items.extend(items)
            except Exception:
                pass

        page.on("response", capture_response)

        await page.goto(search_url, timeout=30_000, wait_until="domcontentloaded")
        await asyncio.sleep(4)  # 等待 API 触发

        await human.random_pause(1500, 3000)
        await human.simulate_reading(2)

        if captured_items:
            return self._format_api_results(captured_items, limit)

        log.info("[meituan] API interception missed, falling back to DOM extraction")
        return await self._dom_search(page, keyword, limit)

    def _format_api_results(self, raw_items: list, limit: int) -> list[SearchResult]:
        results = []
        for item in raw_items[:limit]:
            name = item.get("name") or item.get("productName") or item.get("goodsName", "")
            price = item.get("price") or item.get("salePrice") or item.get("currentPrice", "")
            url = item.get("detailUrl") or item.get("url", "")
            shop = item.get("storeName") or item.get("shopName", "")
            try:
                p = Decimal(str(price)) if price else None
            except Exception:
                p = None
            results.append(SearchResult(title=str(name), url=str(url), display_price=p, shop_name=str(shop)))
        return results

    async def _dom_search(self, page, keyword: str, limit: int) -> list[SearchResult]:
        js = """() => {
            const items = [];
            const cards = Array.from(document.querySelectorAll('[class*="item"], [class*="goods"], [class*="product"]')).filter(el => {
                const t = el.innerText || '';
                return t.length > 10 && el.querySelector('a');
            }).slice(0, 15);
            for (const card of cards.slice(0, 10)) {
                const link = card.querySelector('a');
                const url = link ? link.href : '';
                const priceEl = card.querySelector('[class*="price"], [class*="Price"]');
                const price = priceEl ? priceEl.innerText.replace(/[^0-9.]/g, '') : '';
                const titleEl = card.querySelector('[class*="name"], [class*="title"], h3');
                const title = titleEl ? titleEl.innerText.trim().slice(0, 120) : '';
                items.push({ url, price, title });
            }
            return items;
        }"""
        raw = await page.evaluate(js)
        results = []
        for item in raw[:limit]:
            price_str = item.get("price", "")
            price = Decimal(price_str) if price_str else None
            results.append(SearchResult(title=item.get("title", ""), url=item.get("url", ""), display_price=price))
        return results

    async def get_detail(self, page, url: str, keyword: str, human, screenshot_dir: str = "./data/screenshots") -> ProductDetail:
        log.info(f"[meituan] Getting detail: {url}")

        captured_detail: dict = {}
        async def capture_detail_resp(response):
            try:
                resp_url = response.url
                ctype = response.headers.get("content-type", "")
                if "/detail" in resp_url and "json" in ctype:
                    body = await response.json()
                    d = body.get("data", {})
                    if d.get("name") or d.get("price"):
                        captured_detail.update(d)
            except Exception:
                pass

        page.on("response", capture_detail_resp)

        if not url:
            return ProductDetail(platform=self.platform, keyword=keyword, url=url, error="no_url")

        await page.goto(url, timeout=30_000, wait_until="domcontentloaded")
        await asyncio.sleep(3)
        await human.simulate_reading(3)

        if self.is_login_page(page.url):
            return ProductDetail(platform=self.platform, keyword=keyword, url=url, error="login_required")

        screenshot_path = await self.take_screenshot(page, screenshot_dir, "meituan")

        # 优先使用 API 拦截数据
        if captured_detail:
            price_val = captured_detail.get("price") or captured_detail.get("salePrice")
            try:
                p = Decimal(str(price_val)) if price_val else None
            except Exception:
                p = None
            return ProductDetail(
                platform=self.platform, keyword=keyword, url=url,
                title=captured_detail.get("name", ""),
                display_price=p, final_price=p,
                shop_name=captured_detail.get("storeName", ""),
                screenshot_path=screenshot_path,
            )

        # DOM fallback
        js = """() => ({
            prices: Array.from(document.querySelectorAll('[class*="price"], [class*="Price"]'))
                        .map(el => (el.innerText || '').trim()).filter(t => /\\d/.test(t) && t.length < 50),
            title: (document.querySelector('h1, [class*="name"], [class*="title"]')?.innerText || '').trim().slice(0, 200),
            shop: (document.querySelector('[class*="shop"], [class*="store"]')?.innerText || '').trim().slice(0, 80),
        })"""
        data = await page.evaluate(js)

        display_price = None
        for pstr in data.get("prices", []):
            m = re.search(r"(\d+\.?\d*)", pstr)
            if m:
                try:
                    display_price = Decimal(m.group(1))
                    break
                except Exception:
                    pass

        return ProductDetail(
            platform=self.platform, keyword=keyword, url=url,
            title=data.get("title", ""),
            display_price=display_price, final_price=display_price,
            shop_name=data.get("shop", ""),
            screenshot_path=screenshot_path,
        )
