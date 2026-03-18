"""
pdd.py — 拼多多 Playwright 行为仿真采集器（挑战级）
====================================================
策略:
  - 使用 patchright 二进制层指纹消除
  - DOM + API 双轨提取
  - PDD 风控极强，预期成功率 50-60%，是整个引擎中风险最高的平台

注意:
  PDD 底层使用 __pdd_risk__ 等客户端 JS 检测，即使通过 patchright 也可能被识别。
  - 遇到滑块时：当前不自动处理，记录到 error 字段，由 fallback 链处理
  - Cookie 质量对成功率影响最大，建议确保账号有消费历史
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

log = logging.getLogger("price_monitor.playwright_engine.scrapers.pdd")

_SEARCH_URL = "https://mobile.yangkeduo.com/search_result.html?search_key={keyword}"
# 备用: www.pinduoduo.com 桌面搜索
_DESKTOP_SEARCH = "https://www.pinduoduo.com/search_result.html?search_key={keyword}"


class PDDPlaywrightScraper(BasePlaywrightScraper):
    """
    拼多多 Playwright 采集器（挑战级 ⭐⭐⭐⭐⭐）
    
    ⚠️ 拼多多风控等级最高，可能遇到:
      - 滑块验证 (captcha_slider)
      - 人机验证 (risk check)
      - 无价格展示（需要登录）
    
    当 error="captcha" 时，fallback.py 会自动触发飞书人工告警。
    """
    platform = "pinduoduo"
    login_page_indicators = ["login.pinduoduo.com", "passport", "login", "verify"]

    async def search(self, page, keyword: str, human, limit: int = 10) -> list[SearchResult]:
        url = _DESKTOP_SEARCH.format(keyword=quote(keyword))
        log.info(f"[pdd] Searching: {url}")

        captured_items: list[dict] = []

        async def capture_response(response):
            try:
                resp_url = response.url
                ctype = response.headers.get("content-type", "")
                if ("search" in resp_url or "anti_spider" in resp_url) and "json" in ctype:
                    body = await response.json()
                    items = (
                        body.get("items") or
                        body.get("data", {}).get("items") or
                        body.get("search_result", {}).get("goods_list") or
                        []
                    )
                    if items:
                        log.info(f"[pdd] API captured {len(items)} items")
                        captured_items.extend(items)
            except Exception:
                pass

        page.on("response", capture_response)
        await page.goto(url, timeout=30_000, wait_until="domcontentloaded")
        await asyncio.sleep(4)

        # 检测滑块
        slider = await page.query_selector('[class*="slider"], [class*="captcha"], [class*="verify"]')
        if slider:
            log.warning("[pdd] Slider/Captcha detected! Unable to auto-resolve.")
            return []

        await human.random_pause(2000, 4000)
        await human.simulate_reading(2)

        if captured_items:
            return self._format_api_items(captured_items, limit)

        log.info("[pdd] API capture missed, falling back to DOM extraction")
        return await self._dom_search(page, keyword, limit)

    def _format_api_items(self, raw: list, limit: int) -> list[SearchResult]:
        results = []
        for item in raw[:limit]:
            name = item.get("goods_name") or item.get("goods_simple_name") or item.get("name", "")
            price = item.get("min_group_price") or item.get("min_normal_price") or item.get("price", "")
            goods_id = item.get("goods_id") or item.get("id", "")
            url = f"https://mobile.yangkeduo.com/goods.html?goods_id={goods_id}" if goods_id else ""
            try:
                p = Decimal(str(int(price or 0) / 100.0)) if isinstance(price, int) else Decimal(str(price))
            except Exception:
                p = None
            results.append(SearchResult(title=str(name), url=url, display_price=p))
        return results

    async def _dom_search(self, page, keyword: str, limit: int) -> list[SearchResult]:
        js = """() => {
            const items = [];
            // PDD 商品容器
            const cardSels = ['[class*="goods-item"]', '[class*="item-container"]', '[class*="GoodsItem"]', 'li'];
            let cards = [];
            for (const sel of cardSels) {
                const found = Array.from(document.querySelectorAll(sel)).filter(el => {
                    const t = el.innerText || '';
                    return (t.includes('¥') || t.includes('₱') || t.includes('￥')) && t.length < 600;
                });
                if (found.length > 1) { cards = found; break; }
            }
            for (const card of cards.slice(0, 10)) {
                const priceEl = card.querySelector('[class*="price"], strong, [class*="num"]');
                const price = priceEl ? priceEl.innerText.replace(/[^0-9.]/g, '') : '';
                const link = card.querySelector('a');
                const url = link ? link.href : '';
                const titleEl = card.querySelector('[class*="name"], [class*="title"], h3, h2');
                const title = titleEl ? titleEl.innerText.trim().slice(0, 120) : '';
                if (!title && !url) continue;
                items.push({ url, price, title });
            }
            return { items, is_captcha: !!document.querySelector('[class*="captcha"], [class*="slider"]') };
        }"""
        data = await page.evaluate(js)
        if data.get("is_captcha"):
            log.warning("[pdd] Captcha detected in DOM check")
            return []
        results = []
        for item in data.get("items", [])[:limit]:
            p_str = item.get("price", "")
            p = Decimal(p_str) if p_str else None
            results.append(SearchResult(title=item.get("title", ""), url=item.get("url", ""), display_price=p))
        return results

    async def get_detail(self, page, url: str, keyword: str, human, screenshot_dir: str = "./data/screenshots") -> ProductDetail:
        log.info(f"[pdd] Getting detail: {url}")

        captured_detail: dict = {}
        async def capture_detail(response):
            try:
                resp_url = response.url
                ctype = response.headers.get("content-type", "")
                if "/goods" in resp_url and "json" in ctype:
                    body = await response.json()
                    d = body.get("goods_details") or body.get("details") or {}
                    if d.get("goods_name") or d.get("min_group_price"):
                        captured_detail.update(d)
            except Exception:
                pass

        page.on("response", capture_detail)

        await page.goto(url, timeout=30_000, wait_until="domcontentloaded")
        await asyncio.sleep(3)

        # 滑块检测
        slider = await page.query_selector('[class*="slider"], [class*="captcha"]')
        if slider:
            log.warning("[pdd] Captcha/slider on detail page")
            return ProductDetail(platform=self.platform, keyword=keyword, url=url, error="captcha")

        if self.is_login_page(page.url):
            return ProductDetail(platform=self.platform, keyword=keyword, url=url, error="login_required")

        await human.simulate_reading(4)
        screenshot_path = await self.take_screenshot(page, screenshot_dir, "pdd")

        # API 优先
        if captured_detail:
            raw_price = captured_detail.get("min_group_price") or captured_detail.get("min_normal_price", 0)
            try:
                p = Decimal(str(int(raw_price) / 100.0)) if isinstance(raw_price, int) else None
            except Exception:
                p = None
            return ProductDetail(
                platform=self.platform, keyword=keyword, url=url,
                title=captured_detail.get("goods_name", ""),
                display_price=p, final_price=p,
                screenshot_path=screenshot_path,
            )

        # DOM fallback
        js = """() => ({
            prices: Array.from(document.querySelectorAll('[class*="price"], strong, [class*="amount"]'))
                        .map(el => (el.innerText || '').trim()).filter(t => /\\d/.test(t) && t.length < 50),
            title: (document.querySelector('h1, [class*="goods-name"], [class*="title"]')?.innerText || '').trim().slice(0, 200),
            shop: (document.querySelector('[class*="shop"], [class*="seller"], [class*="mall"]')?.innerText || '').trim().slice(0, 80),
            coupons: Array.from(document.querySelectorAll('[class*="coupon"], [class*="quan"]'))
                         .map(el => (el.innerText || '').trim()).filter(t => t.length > 2 && t.length < 100).slice(0, 5),
        })"""
        data = await page.evaluate(js)

        display_price = None
        for pstr in data.get("prices", []):
            m = re.search(r"(\d+\.?\d*)", pstr)
            if m:
                try:
                    v = Decimal(m.group(1))
                    if Decimal("0.1") < v < Decimal("9999"):
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
