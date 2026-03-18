"""
taobao.py — 淘宝 Playwright 行为仿真采集器
==========================================
策略:
  1. 通过 taobao.com 搜索、获取列表（H5 页面）
  2. 进入商品详情页，采集价格+优惠
  3. 使用 tbpc 全局 JS 对象尝试读取精确价格

注意: 淘宝与天猫共享账号体系，Cookie 可互用。
"""
import asyncio
import logging
import re
from decimal import Decimal
from urllib.parse import quote
from typing import Optional

from price_monitor.playwright_engine.base_scraper import (
    BasePlaywrightScraper, ProductDetail, SearchResult, CouponDetail
)
from price_monitor.playwright_engine.scrapers.tmall import TmallPlaywrightScraper

log = logging.getLogger("price_monitor.playwright_engine.scrapers.taobao")

_SEARCH_URL = "https://s.taobao.com/search?q={keyword}&sort=sale-desc"

JS_EXTRACT_TAOBAO_LIST = """() => {
    const items = [];
    // 淘宝搜索结果容器
    const cardSelectors = [
        "[class*='item']",
        "[class*='Card']",
        ".m-itemlist-items > li",
        "[data-spm-item]",
    ];
    let cards = [];
    for (const sel of cardSelectors) {
        const found = Array.from(document.querySelectorAll(sel)).filter(el => {
            const t = el.innerText || '';
            return (t.includes('¥') || t.includes('￥')) && el.querySelector('a');
        });
        if (found.length > 1) { cards = found; break; }
    }

    for (const card of cards.slice(0, 10)) {
        const link = card.querySelector('a[href*="taobao.com"], a[href*="item.taobao.com"]');
        const url = link ? (link.href.startsWith('//') ? 'https:' + link.href : link.href) : '';
        const priceEl = card.querySelector("[class*='price'], [class*='Price']");
        let price = priceEl ? priceEl.innerText.replace(/[^0-9.]/g, '') : '';
        if (!price) {
            const pm = (card.innerText || '').match(/[¥￥](\\d+\\.?\\d*)/);
            if (pm) price = pm[1];
        }
        const titleEl = card.querySelector("[class*='title'], h3, h2, [class*='name']");
        const title = titleEl ? titleEl.innerText.trim().slice(0, 120) : '';
        const shopEl = card.querySelector("[class*='shop'], [class*='seller']");
        const shop = shopEl ? shopEl.innerText.trim().slice(0, 60) : '';
        if (!url && !title) continue;
        items.push({ url, price, title, shop });
    }
    return { items, url: window.location.href, is_login: window.location.href.includes('login') };
}"""

JS_EXTRACT_TAOBAO_DETAIL = """() => {
    const result = {};

    // 尝试全局 __INIT_DATA__.data 取精确价格
    try {
        const d = window.__INIT_DATA__?.data;
        if (d?.priceModule?.price?.priceText) {
            result.price_exact = d.priceModule.price.priceText;
        }
    } catch(e) {}

    // DOM 价格
    result.price_elements = [];
    const seen = new Set();
    for (const sel of ["[class*='price']", "[class*='Price']", "[class*='tb-price']"]) {
        for (const el of document.querySelectorAll(sel)) {
            const t = (el.innerText || '').trim();
            if (t && /\\d/.test(t) && t.length < 50 && !seen.has(t)) {
                seen.add(t);
                result.price_elements.push({ cls: el.className.slice(0, 60), text: t });
            }
        }
    }

    result.title = (document.querySelector('h1, [class*="title"]')?.innerText || '').trim().slice(0, 200);
    const shopEl = document.querySelector('[class*="shopName"], [class*="ShopName"], .shopLink');
    result.shop_name = shopEl ? shopEl.innerText.trim().slice(0, 80) : '';

    result.coupons = [];
    document.querySelectorAll('[class*="coupon"], [class*="Coupon"], [class*="quan"]').forEach(el => {
        const t = (el.innerText || '').trim();
        if (t && t.length > 2 && t.length < 100) result.coupons.push(t);
    });

    result.promotions = [];
    document.querySelectorAll('[class*="promo"], [class*="activity"], [class*="Action"]').forEach(el => {
        const t = (el.innerText || '').trim();
        if (t && t.length > 2 && t.length < 150) result.promotions.push(t);
    });

    const shipEl = document.querySelector('[class*="ship"], [class*="deliver"], [class*="addr"]');
    result.ship_city = shipEl ? shipEl.innerText.trim().slice(0, 30) : '';

    result.price_lines = (document.body.innerText || '').split('\\n').filter(
        l => (l.includes('¥') || l.includes('￥')) && l.length < 80
    ).slice(0, 15);

    result.is_login = window.location.href.includes('login') || window.location.href.includes('passport');
    result.current_url = window.location.href;
    return result;
}"""


class TaobaoPlaywrightScraper(TmallPlaywrightScraper):
    """
    淘宝 Playwright 采集器。
    继承天猫 scraper，覆盖平台标识、搜索 URL 和 JS 提取脚本。
    """
    platform = "taobao"
    search_result_selector = "[class*='item']"
    login_page_indicators = ["login.taobao.com", "login", "passport"]

    async def search(self, page, keyword: str, human, limit: int = 10) -> list[SearchResult]:
        search_url = _SEARCH_URL.format(keyword=quote(keyword))
        log.info(f"[taobao] Searching: {search_url}")
        await page.goto(search_url, timeout=30_000, wait_until="domcontentloaded")
        try:
            await page.wait_for_selector("[class*='item'], [class*='Card']", timeout=12_000)
        except Exception:
            log.warning("[taobao] Search result selector timeout")

        await human.random_pause(2000, 4000)
        await human.simulate_reading(2)

        data = await page.evaluate(JS_EXTRACT_TAOBAO_LIST)
        if data.get("is_login"):
            log.warning("[taobao] Redirected to login during search")
            return []

        items = data.get("items", [])
        log.info(f"[taobao] Found {len(items)} results for '{keyword}'")
        results = []
        for item in items[:limit]:
            url = item.get("url", "")
            price_str = item.get("price", "")
            price = Decimal(price_str) if price_str else None
            results.append(SearchResult(
                title=item.get("title", ""),
                url=url,
                display_price=price,
                shop_name=item.get("shop", ""),
            ))
        return results

    async def get_detail(self, page, url: str, keyword: str, human, screenshot_dir: str = "./data/screenshots") -> ProductDetail:
        log.info(f"[taobao] Getting detail: {url}")
        await page.goto(url, timeout=30_000, wait_until="domcontentloaded")
        try:
            await page.wait_for_selector("[class*='Price'], [class*='price']", timeout=15_000)
        except Exception:
            log.warning("[taobao] Price selector timeout on detail page")

        await human.simulate_reading(4)

        current_url = page.url
        if self.is_login_page(current_url):
            log.warning(f"[taobao] Redirected to login: {current_url}")
            return ProductDetail(platform=self.platform, keyword=keyword, url=url, error="login_required")

        data = await page.evaluate(JS_EXTRACT_TAOBAO_DETAIL)
        screenshot_path = await self.take_screenshot(page, screenshot_dir, "detail")

        display_price = self._extract_best_price(self, data)
        final_price = display_price
        if data.get("price_exact"):
            try:
                final_price = Decimal(re.sub(r"[^\d.]", "", data["price_exact"]))
            except Exception:
                pass

        coupons = []
        for text in data.get("coupons", [])[:5]:
            cd = self._parse_coupon_text(text)
            if cd:
                coupons.append(cd)

        return ProductDetail(
            platform=self.platform,
            keyword=keyword,
            url=url,
            title=data.get("title", ""),
            display_price=display_price,
            final_price=final_price,
            coupons=coupons,
            promotions=data.get("promotions", [])[:5],
            shop_name=data.get("shop_name", ""),
            ship_from_city=data.get("ship_city", ""),
            screenshot_path=screenshot_path,
            error=None,
        )
