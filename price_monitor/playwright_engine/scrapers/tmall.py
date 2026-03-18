"""
tmall.py — 天猫 Playwright 行为仿真采集器
==========================================
策略:
  1. 进入天猫品牌旗舰店搜索页 / tmall.com 搜索
  2. 人类行为：贝塞尔鼠标 + 逐字打字搜索关键词
  3. 进入商品详情页，展开优惠券区域，采集全量价格数据
  4. 利用 ice_app_context 全局 JS 对象直接读取精确到手价（天猫特有）

CSS 选择器（2025-2026 天猫 PC 版，动态 class，用 [class*=] 兜底）:
  搜索框: form > input / #q / [name='q']
  搜索结果卡: [class*='Card--doubleCard'] / [class*='item']
  价格: [class*='price'] / [class*='Price']
  优惠券: [class*='coupon'] / [class*='Coupon']
  店铺名: [class*='shopName'] / .shopLink
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

log = logging.getLogger("price_monitor.playwright_engine.scrapers.tmall")

# 搜索入口（天猫主站）
_SEARCH_URL = "https://list.tmall.com/search_product.htm?q={keyword}&sort=d"
# 备用天猫超市搜索
_CHAOSHI_URL = "https://chaoshi.detail.tmall.com"

JS_EXTRACT_TMALL_LIST = """() => {
    const items = [];
    // 天猫搜索结果卡片 (多种 class 模式)
    const cardSelectors = [
        "[class*='Card--doubleCard']", "[class*='SearchContent']",
        "[class*='m-itemlist-items'] > li", ".m-itemlist-item",
        "[class*='item'] .pic", "[class*='product-item']",
        "[data-spm-item]",
    ];
    let cards = [];
    for (const sel of cardSelectors) {
        const found = document.querySelectorAll(sel);
        if (found.length > 1) { cards = Array.from(found); break; }
    }
    // 降级: 任何包含价格和商品链接的 div
    if (cards.length === 0) {
        cards = Array.from(document.querySelectorAll('div')).filter(el => {
            const t = el.innerText || '';
            const hasPrice = t.includes('¥') || t.includes('￥');
            const hasLink = el.querySelector('a[href*="detail.tmall.com"]');
            return hasPrice && hasLink && t.length < 800;
        }).slice(0, 20);
    }

    for (const card of cards.slice(0, 10)) {
        const text = card.innerText || '';
        if (!text.trim()) continue;

        // 商品链接
        const link = card.querySelector('a[href*="detail.tmall.com"], a[href*="tmall.com"]');
        const url = link ? link.href : '';

        // 价格 (取第一个含数字的价格元素)
        const priceEl = card.querySelector("[class*='price'], [class*='Price'], .price");
        let price = '';
        if (priceEl) {
            price = priceEl.innerText.replace(/[^0-9.]/g, '').trim();
        }
        if (!price) {
            const pm = text.match(/[¥￥](\\d+\\.?\\d*)/);
            if (pm) price = pm[1];
        }

        // 商品标题
        const titleEl = card.querySelector("[class*='title'], [class*='Title'], [class*='name'], h3, h2");
        let title = titleEl ? titleEl.innerText.trim().slice(0, 120) : '';

        // 店铺名
        const shopEl = card.querySelector("[class*='shop'], [class*='Shop'], [class*='seller']");
        let shop = shopEl ? shopEl.innerText.trim().slice(0, 60) : '';

        if (!url && !title) continue;
        items.push({ url, price, title, shop });
    }
    return { items, url: window.location.href };
}"""

JS_EXTRACT_TMALL_DETAIL = """() => {
    const result = {};

    // 1. ice_app_context (天猫独有全局对象，包含精确价格)
    try {
        const ctxKeys = Object.keys(window.__NEXT_DATA__ || window.__INITIAL_STATE__ || {});
        for (const k of ctxKeys) {
            const v = window[k];
            if (v && v.priceVO) {
                result.price_exact = v.priceVO.price?.priceText || v.priceVO.rangePrice?.toLowerCase();
                break;
            }
        }
    } catch(e) {}

    // 2. 页面 DOM 价格 (多层 fallback)
    const priceSelectors = [
        "[class*='price'][class*='current']", "[class*='price-current']",
        "[class*='PriceNow']", "[class*='PromotionPrice']",
        "[class*='price-text']", "[class*='Price']",
        "[class*='price']",
    ];
    result.price_elements = [];
    const seen = new Set();
    for (const sel of priceSelectors) {
        for (const el of document.querySelectorAll(sel)) {
            const t = (el.innerText || el.textContent || '').trim();
            if (t && t.length < 50 && /\\d+/.test(t) && !seen.has(t)) {
                seen.add(t);
                result.price_elements.push({ cls: el.className.slice(0, 60), text: t });
            }
        }
    }

    // 3. 商品标题
    result.title = (document.querySelector('h1, [class*="title"]')?.innerText || '').trim().slice(0, 200);

    // 4. 店铺名
    const shopEl = document.querySelector('[class*="shopName"], .shopLink, [class*="ShopName"]');
    result.shop_name = shopEl ? shopEl.innerText.trim().slice(0, 80) : '';

    // 5. 优惠券区域
    const couponEls = document.querySelectorAll(
        '[class*="coupon"], [class*="Coupon"], [class*="discount"], [class*="quan"]'
    );
    result.coupons = [];
    couponEls.forEach(el => {
        const t = el.innerText ? el.innerText.trim() : '';
        if (t && t.length > 2 && t.length < 100) result.coupons.push(t);
    });

    // 6. 促销活动
    const promoEls = document.querySelectorAll('[class*="promo"], [class*="Promo"], [class*="activity"]');
    result.promotions = [];
    promoEls.forEach(el => {
        const t = el.innerText ? el.innerText.trim() : '';
        if (t && t.length > 2 && t.length < 150) result.promotions.push(t);
    });

    // 7. 发货地
    const shipEl = document.querySelector('[class*="shipfrom"], [class*="deliverTo"], [class*="address"]');
    result.ship_city = shipEl ? shipEl.innerText.trim().slice(0, 30) : '';

    // 8. 价格行 (body 全文)
    result.price_lines = (document.body.innerText || '').split('\\n').filter(
        l => (l.includes('¥') || l.includes('￥')) && l.length < 80
    ).slice(0, 15);

    // 9. 登录检测
    result.is_login = window.location.href.includes('login') || window.location.href.includes('login.taobao');
    result.current_url = window.location.href;

    return result;
}"""


class TmallPlaywrightScraper(BasePlaywrightScraper):
    platform = "tmall"
    search_result_selector = "[class*='CardBox']"
    login_page_indicators = ["login.taobao.com", "login", "passport", "sign"]

    async def search(self, page, keyword: str, human, limit: int = 10) -> list[SearchResult]:
        search_url = _SEARCH_URL.format(keyword=quote(keyword))
        log.info(f"[tmall] Searching: {search_url}")
        await page.goto(search_url, timeout=30_000, wait_until="domcontentloaded")

        # 等待结果加载
        try:
            await page.wait_for_selector("[class*='CardBox'], [class*='item'], .m-itemlist", timeout=12_000)
        except Exception:
            log.warning("[tmall] Search result selector timeout")

        await human.random_pause(2000, 4000)
        await human.simulate_reading(2)

        data = await page.evaluate(JS_EXTRACT_TMALL_LIST)
        items = data.get("items", [])
        log.info(f"[tmall] Found {len(items)} results for '{keyword}'")

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
        log.info(f"[tmall] Getting detail: {url}")
        await page.goto(url, timeout=30_000, wait_until="domcontentloaded")

        # 等待价格元素
        try:
            await page.wait_for_selector("[class*='Price'], [class*='price']", timeout=15_000)
        except Exception:
            log.warning("[tmall] Price selector timeout on detail page")

        # 模拟用户阅读商品页面
        await human.simulate_reading(4)

        # 检测登录重定向
        current_url = page.url
        if self.is_login_page(current_url):
            log.warning(f"[tmall] Redirected to login: {current_url}")
            return ProductDetail(platform=self.platform, keyword=keyword, url=url, error="login_required")

        data = await page.evaluate(JS_EXTRACT_TMALL_DETAIL)

        # 截图
        screenshot_path = await self.take_screenshot(page, screenshot_dir, "detail")

        # 解析价格
        display_price = self._extract_best_price(data)
        final_price = display_price  # 天猫优惠券后的真实价格需要点击领取按钮，初版先用展示价

        # 尝试精确价格
        if data.get("price_exact"):
            try:
                final_price = Decimal(re.sub(r"[^\d.]", "", data["price_exact"]))
            except Exception:
                pass

        # 解析优惠券
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

    def _extract_best_price(self, data: dict) -> Optional[Decimal]:
        """从多个 price_elements 中提取最合理的价格"""
        for pe in data.get("price_elements", []):
            text = pe.get("text", "")
            try:
                match = re.search(r"(\d+\.?\d*)", text.replace(",", ""))
                if match:
                    val = Decimal(match.group(1))
                    if Decimal("0.1") < val < Decimal("99999"):
                        return val
            except Exception:
                continue

        # fallback: 从 price_lines 取
        for line in data.get("price_lines", []):
            match = re.search(r"[¥￥](\d+\.?\d*)", line)
            if match:
                try:
                    return Decimal(match.group(1))
                except Exception:
                    pass
        return None

    @staticmethod
    def _parse_coupon_text(text: str) -> Optional[CouponDetail]:
        """解析优惠券/促销文本"""
        text = text.strip()
        if not text or len(text) <= 1:
            return None

        # 满 X 减 Y
        m = re.search(r"满(\d+)减(\d+)", text)
        if m:
            return CouponDetail(
                coupon_type="CASH",
                threshold=Decimal(m.group(1)),
                discount=Decimal(m.group(2)),
                raw_text=text,
            )

        # 立减 / 领券减 X
        m = re.search(r"(?:立减|领券减)(\d+)", text)
        if m:
            return CouponDetail(
                coupon_type="CASH",
                threshold=None,
                discount=Decimal(m.group(1)),
                raw_text=text,
            )

        return None
