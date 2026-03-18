"""
jd.py — 京东/京东秒送 Playwright 行为仿真采集器
==================================================
策略:
  so.m.jd.com (移动版搜索) → item.m.jd.com (移动版详情页)
  Cookie 注入后可获取真实到手价（否则部分价格掩码 ¥1??9）
"""
import logging
import re
from decimal import Decimal
from urllib.parse import quote
from typing import Optional

from price_monitor.playwright_engine.base_scraper import (
    BasePlaywrightScraper, ProductDetail, SearchResult, CouponDetail
)

log = logging.getLogger("price_monitor.playwright_engine.scrapers.jd")

_SEARCH_URL = "https://so.m.jd.com/ware/search.action?keyword={keyword}"

JS_JD_LIST = """() => {
    const items = [];
    const selectors = [
        "ul.m-goods-list > li", "ul.goods-list > li",
        "[class*='search-goods'] li", "[class*='goods-item']",
        "[data-sku]",
    ];
    let cards = [];
    for (const sel of selectors) {
        const found = Array.from(document.querySelectorAll(sel)).filter(el =>
            (el.innerText || '').includes('¥') && el.querySelector('a')
        );
        if (found.length > 1) { cards = found; break; }
    }
    if (cards.length === 0) {
        cards = Array.from(document.querySelectorAll('li')).filter(el => {
            const t = el.innerText || '';
            return (t.includes('¥') || t.includes('￥')) && el.querySelector('a') && t.length < 600;
        }).slice(0, 15);
    }
    for (const card of cards.slice(0, 10)) {
        let sku_id = card.getAttribute('data-sku') || '';
        if (!sku_id) {
            const a = card.querySelector('a[href*="/product/"]');
            if (a) { const m = a.href.match(/\\/product\\/(\\d+)/); if (m) sku_id = m[1]; }
        }
        const priceEl = card.querySelector("[class*='price'][class*='cur'], strong.price, [class*='Price']") || card.querySelector("[class*='price']");
        const price = priceEl ? priceEl.innerText.replace(/[^0-9.]/g, '') : '';
        const titleEl = card.querySelector("[class*='title'], [class*='name'], h3, h2");
        const title = titleEl ? titleEl.innerText.trim().slice(0, 120) : '';
        const shopEl = card.querySelector("[class*='shop'], [class*='seller']");
        const shop = shopEl ? shopEl.innerText.trim().slice(0, 60) : '';
        const url = sku_id ? `https://item.m.jd.com/product/${sku_id}.html` : '';
        if (!title && !sku_id) continue;
        items.push({ url, sku_id, price, title, shop });
    }
    return { items, is_login: window.location.href.includes('passport.jd.com') };
}"""

JS_JD_DETAIL = """() => {
    const result = {};
    // window._itemOnly (SSR 数据)
    try {
        const content = document.documentElement.innerHTML;
        const m = content.match(/window\._itemOnly\\s*=\\s*(\\{.+?\\});/s);
        if (m) {
            const d = JSON.parse(m[1]);
            result.sku_name = d.item?.skuName || '';
            result.brand_name = d.item?.brandName || '';
        }
    } catch(e) {}

    result.price_elements = [];
    const seen = new Set();
    for (const sel of ["[class*='price']", "[class*='Price']", "[class*='jdPrice']", "span[class*='yuan']"]) {
        for (const el of document.querySelectorAll(sel)) {
            const t = (el.innerText || '').trim();
            if (t && /\\d/.test(t) && !t.includes('??') && t.length < 50 && !seen.has(t)) {
                seen.add(t);
                result.price_elements.push({ cls: el.className.slice(0, 60), text: t });
            }
        }
    }
    result.has_masked = (document.body.innerText || '').includes('??');
    result.title = (document.querySelector('h1, [class*="goodsName"], .fn_goods_name')?.innerText || result.sku_name || '').trim().slice(0, 200);
    const shopEl = document.querySelector('[class*="shop'], [class*="seller"]');
    result.shop_name = shopEl ? shopEl.innerText.trim().slice(0, 80) : (result.brand_name || '');
    result.coupons = [];
    document.querySelectorAll('[class*="coupon"], [class*="promo"], [class*="quan"]').forEach(el => {
        const t = (el.innerText || '').trim();
        if (t && t.length > 2 && t.length < 100) result.coupons.push(t);
    });
    const addrEl = document.querySelector('[class*="addr"], [class*="deliver"]');
    result.ship_city = addrEl ? addrEl.innerText.trim().slice(0, 30) : '';
    result.price_lines = (document.body.innerText || '').split('\\n').filter(
        l => (l.includes('¥') || l.includes('￥')) && !l.includes('??') && l.length < 80
    ).slice(0, 15);
    result.is_login = window.location.href.includes('plogin') || window.location.href.includes('passport.jd.com');
    return result;
}"""


class JDPlaywrightScraper(BasePlaywrightScraper):
    platform = "jd_express"
    search_result_selector = "ul.m-goods-list > li"
    login_page_indicators = ["plogin.m.jd.com", "passport.jd.com", "login"]

    async def search(self, page, keyword: str, human, limit: int = 10) -> list[SearchResult]:
        url = _SEARCH_URL.format(keyword=quote(keyword))
        log.info(f"[jd] Searching: {url}")
        await page.goto(url, timeout=30_000, wait_until="domcontentloaded")
        try:
            await page.wait_for_selector("[class*='goods'], li", timeout=12_000)
        except Exception:
            log.warning("[jd] Search result selector timeout")

        # 关闭可能出现的 App 弹窗
        try:
            await page.evaluate("""() => {
                document.querySelectorAll('[class*="modal"], [class*="mask"]').forEach(el => el.remove());
            }""")
            await page.keyboard.press("Escape")
        except Exception:
            pass

        await human.random_pause(2000, 4000)
        data = await page.evaluate(JS_JD_LIST)
        if data.get("is_login"):
            log.warning("[jd] Redirected to login during search")
            return []

        items = data.get("items", [])
        log.info(f"[jd] Found {len(items)} results for '{keyword}'")
        results = []
        for item in items[:limit]:
            price_str = item.get("price", "")
            price = Decimal(price_str) if price_str else None
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                display_price=price,
                shop_name=item.get("shop", ""),
            ))
        return results

    async def get_detail(self, page, url: str, keyword: str, human, screenshot_dir: str = "./data/screenshots") -> ProductDetail:
        log.info(f"[jd] Getting detail: {url}")
        await page.goto(url, timeout=30_000, wait_until="domcontentloaded")
        try:
            await page.wait_for_selector("[class*='price'], .fn_goods_name", timeout=15_000)
        except Exception:
            log.warning("[jd] Price selector timeout on detail page")

        await human.simulate_reading(3)

        if self.is_login_page(page.url):
            log.warning(f"[jd] Redirected to login: {page.url}")
            return ProductDetail(platform=self.platform, keyword=keyword, url=url, error="login_required")

        data = await page.evaluate(JS_JD_DETAIL)
        screenshot_path = await self.take_screenshot(page, screenshot_dir, "detail")
        display_price = self._extract_price(data)

        coupons = [CouponDetail("UNKNOWN", None, Decimal("0"), raw_text=t)
                   for t in data.get("coupons", [])[:5] if t]

        return ProductDetail(
            platform=self.platform, keyword=keyword, url=url,
            title=data.get("title", ""),
            display_price=display_price, final_price=display_price,
            is_login_required_for_price=data.get("has_masked", False),
            coupons=coupons,
            shop_name=data.get("shop_name", ""),
            ship_from_city=self._extract_city(data.get("ship_city", "")),
            screenshot_path=screenshot_path,
        )

    def _extract_price(self, data: dict) -> Optional[Decimal]:
        for pe in data.get("price_elements", []):
            try:
                m = re.search(r"(\d+\.?\d*)", pe["text"].replace(",", ""))
                if m:
                    v = Decimal(m.group(1))
                    if Decimal("1") < v < Decimal("99999"):
                        return v
            except Exception:
                pass
        for line in data.get("price_lines", []):
            m = re.search(r"[¥￥](\d+\.?\d*)", line)
            if m:
                try:
                    return Decimal(m.group(1))
                except Exception:
                    pass
        return None

    @staticmethod
    def _extract_city(text: str) -> str:
        m = re.search(r"([\u4e00-\u9fa5]{2,4}(?:市|区|仓|省))", text)
        return m.group(1) if m else text.strip()[:10]
