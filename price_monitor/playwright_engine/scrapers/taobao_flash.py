"""
taobao_flash.py — 淘宝闪购 Playwright 行为仿真采集器
=====================================================
策略:
  1. 访问淘宝闪购入口 (品牌频道 / 搜索结果)
  2. 拦截 MTOP 接口响应作为主要数据来源（闪购价格由接口返回）
  3. DOM 价格作为兜底 fallback

MTOP 拦截模式: page.on("response", ...) 捕获 `mtop.alibaba.wisdomsearch` 接口响应，
    解析 returnData.pangu.resultContent.items[].price
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

log = logging.getLogger("price_monitor.playwright_engine.scrapers.taobao_flash")

_FLASH_SEARCH = "https://s.taobao.com/search?q={keyword}&tab=sg"
_FLASH_HOME = "https://taobao.com/markets/flashsale"


class TaobaoFlashPlaywrightScraper(BasePlaywrightScraper):
    """
    淘宝闪购 Playwright 采集器
    核心技术: Playwright 网络响应拦截（MTOP API 明文 JSON）
    """
    platform = "taobao_flash"
    login_page_indicators = ["login.taobao.com", "passport", "login"]

    async def search(self, page, keyword: str, human, limit: int = 10) -> list[SearchResult]:
        url = _FLASH_SEARCH.format(keyword=quote(keyword))
        log.info(f"[taobao_flash] Searching: {url}")

        captured_api_data: list[dict] = []

        # 拦截 MTOP 接口响应
        async def handle_response(response):
            try:
                resp_url = response.url
                if "mtop.alibaba" in resp_url or "wisdomsearch" in resp_url or "search" in resp_url:
                    body = await response.body()
                    text = body.decode("utf-8", errors="replace")
                    # MTOP 响应通常是 JSONP 格式，去掉 callback 包装
                    text = re.sub(r"^[^{]*", "", text).rstrip(");")
                    if "{" in text:
                        data = json.loads(text)
                        captured_api_data.append(data)
            except Exception:
                pass

        page.on("response", handle_response)
        await page.goto(url, timeout=30_000, wait_until="domcontentloaded")
        await asyncio.sleep(3)  # 等待 MTOP 接口触发

        await human.random_pause(1500, 3000)
        await human.simulate_reading(2)

        # 尝试从拦截数据提取
        results = self._parse_api_results(captured_api_data, limit)
        if results:
            log.info(f"[taobao_flash] Extracted {len(results)} results from API interception")
            return results

        # Fallback: DOM 提取
        return await self._dom_search(page, keyword, limit)

    async def _dom_search(self, page, keyword: str, limit: int) -> list[SearchResult]:
        """DOM fallback: 类似淘宝主站提取模式"""
        js = """() => {
            const items = [];
            const cards = Array.from(document.querySelectorAll('[class*="item"], [class*="Card"]')).filter(el => {
                const t = el.innerText || '';
                return (t.includes('¥') || t.includes('￥')) && el.querySelector('a');
            }).slice(0, 15);
            for (const card of cards.slice(0, 10)) {
                const link = card.querySelector('a');
                const url = link ? link.href : '';
                const priceEl = card.querySelector('[class*="price"], [class*="Price"]');
                const price = priceEl ? priceEl.innerText.replace(/[^0-9.]/g, '') : '';
                const titleEl = card.querySelector('[class*="title"], h3');
                const title = titleEl ? titleEl.innerText.trim().slice(0, 120) : '';
                if (!url && !title) continue;
                items.push({ url, price, title });
            }
            return { items };
        }"""
        data = await page.evaluate(js)
        items = data.get("items", [])
        results = []
        for item in items[:limit]:
            price_str = item.get("price", "")
            price = Decimal(price_str) if price_str else None
            results.append(SearchResult(title=item.get("title", ""), url=item.get("url", ""), display_price=price))
        return results

    def _parse_api_results(self, api_data: list[dict], limit: int) -> list[SearchResult]:
        """从 MTOP 接口响应中解析商品列表"""
        results = []
        for data in api_data:
            try:
                items = (
                    data.get("data", {}).get("resultList", []) or
                    data.get("returnValue", {}).get("resultList", []) or
                    data.get("result", {}).get("items", [])
                )
                for item in items[:limit]:
                    name = item.get("name") or item.get("title") or item.get("item_title", "")
                    price = item.get("price") or item.get("currentPrice") or item.get("reservePrice", "")
                    url = item.get("detail_url") or item.get("url") or item.get("item_url", "")
                    if name or url:
                        try:
                            p = Decimal(str(price)) if price else None
                        except Exception:
                            p = None
                        results.append(SearchResult(title=str(name), url=str(url), display_price=p))
                if results:
                    break
            except Exception:
                pass
        return results[:limit]

    async def get_detail(self, page, url: str, keyword: str, human, screenshot_dir: str = "./data/screenshots") -> ProductDetail:
        log.info(f"[taobao_flash] Getting detail: {url}")
        await page.goto(url, timeout=30_000, wait_until="domcontentloaded")
        try:
            await page.wait_for_selector("[class*='Price'], [class*='price']", timeout=15_000)
        except Exception:
            pass

        await human.simulate_reading(3)

        if self.is_login_page(page.url):
            return ProductDetail(platform=self.platform, keyword=keyword, url=url, error="login_required")

        # 复用通用 JS 提取（闪购价格通常在同样的 DOM 位置）
        js = """() => {
            const els = []; const seen = new Set();
            for (const sel of ['[class*="price"]', '[class*="Price"]', '[class*="flash"]']) {
                for (const el of document.querySelectorAll(sel)) {
                    const t = (el.innerText || '').trim();
                    if (t && /\\d/.test(t) && t.length < 50 && !seen.has(t)) { seen.add(t); els.push(t); }
                }
            }
            return {
                prices: els,
                title: (document.querySelector('h1, [class*="title"]')?.innerText || '').trim().slice(0, 200),
                shop: (document.querySelector('[class*="shopName"], [class*="seller"]')?.innerText || '').trim().slice(0, 80),
                coupons: Array.from(document.querySelectorAll('[class*="coupon"], [class*="quan"]')).map(el => (el.innerText || '').trim()).filter(t => t.length > 2 && t.length < 100).slice(0, 5),
            };
        }"""
        data = await page.evaluate(js)
        screenshot_path = await self.take_screenshot(page, screenshot_dir, "flash")

        display_price = None
        for pstr in data.get("prices", []):
            m = re.search(r"(\d+\.?\d*)", pstr.replace(",", ""))
            if m:
                try:
                    v = Decimal(m.group(1))
                    if Decimal("1") < v < Decimal("9999"):
                        display_price = v
                        break
                except Exception:
                    pass

        coupons = [CouponDetail("UNKNOWN", None, Decimal("0"), raw_text=t) for t in data.get("coupons", [])]

        return ProductDetail(
            platform=self.platform, keyword=keyword, url=url,
            title=data.get("title", ""),
            display_price=display_price, final_price=display_price,
            coupons=coupons,
            shop_name=data.get("shop", ""),
            screenshot_path=screenshot_path,
        )
