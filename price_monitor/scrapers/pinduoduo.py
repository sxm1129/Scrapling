"""
拼多多采集器
策略: Tier-2 StealthyFetcher 浏览器渲染

拼多多 Web 端数据极度受限, 但 mobile.yangkeduo.com 仍可访问部分商品页。
使用 StealthyFetcher 渲染移动端页面作为最佳努力采集。

注意: 拼多多反爬极其严格, anti_content 加密频繁更新。
浏览器渲染方案可获取基础数据, 但稳定性有限。
"""

import re
import logging
import os
from typing import Optional

from scrapling.fetchers import StealthyFetcher

from price_monitor.models import (
    ProductPrice, ScrapeTask, Platform,
    CouponInfo, CouponType,
)
from price_monitor.scrapers import BaseScraper

log = logging.getLogger("price_monitor.scrapers.pinduoduo")

JS_EXTRACT_DATA = """() => {
    const result = {};

    // 商品名称
    const titleEls = document.querySelectorAll(
        "h1, [class*='title'], [class*='name'], [class*='goods-name']"
    );
    result.titles = [];
    titleEls.forEach(el => {
        const t = el.textContent.trim();
        if (t && t.length > 3 && t.length < 200) result.titles.push(t);
    });

    // 价格
    const allText = document.body.innerText || "";
    result.price_lines = allText.split("\\n").filter(
        line => (line.includes("¥") || line.includes("￥") || line.includes("拼")) && line.length < 80
    ).slice(0, 15);

    const priceSelectors = [
        "[class*='price']", "[class*='Price']",
        "[class*='amount']", "[class*='num']",
    ];
    const priceEls = document.querySelectorAll(priceSelectors.join(", "));
    result.price_elements = [];
    const seen = new Set();
    priceEls.forEach(el => {
        const text = el.innerText ? el.innerText.trim() : "";
        if (text && text.length < 60 && /[0-9]/.test(text) && !seen.has(text)) {
            seen.add(text);
            result.price_elements.push({cls: el.className.substring(0, 60), text});
        }
    });

    if (result.price_elements.length === 0) {
        document.querySelectorAll("span").forEach(el => {
            const text = el.innerText ? el.innerText.trim() : "";
            if (text && text.length < 30 && (text.includes("¥") || text.includes("￥")) && /[0-9]/.test(text) && !seen.has(text)) {
                seen.add(text);
                result.price_elements.push({cls: "span", text});
            }
        });
    }

    // 店铺
    const shopEls = document.querySelectorAll(
        "[class*='shop'], [class*='store'], [class*='mall'], [class*='merchant']"
    );
    result.shops = [];
    shopEls.forEach(el => {
        const text = el.innerText ? el.innerText.trim() : "";
        if (text && text.length > 1 && text.length < 60) result.shops.push(text);
    });

    // 优惠
    const promoEls = document.querySelectorAll(
        "[class*='coupon'], [class*='promo'], [class*='discount'], [class*='tag']"
    );
    result.promos = [];
    promoEls.forEach(el => {
        const text = el.innerText ? el.innerText.trim() : "";
        if (text && text.length > 1 && text.length < 100) result.promos.push(text);
    });

    // 发货地
    const addrEls = document.querySelectorAll("[class*='delivery'], [class*='ship'], [class*='origin']");
    result.addresses = [];
    addrEls.forEach(el => {
        const text = el.innerText ? el.innerText.trim() : "";
        if (text && text.length > 1 && text.length < 80) result.addresses.push(text);
    });

    // 销量
    const salesEls = document.querySelectorAll("[class*='sale'], [class*='sold'], [class*='group']");
    result.sales = [];
    salesEls.forEach(el => {
        const text = el.innerText ? el.innerText.trim() : "";
        if (text && /[0-9]/.test(text) && text.length < 30) result.sales.push(text);
    });

    result.is_login_page = window.location.href.includes("login");
    result.current_url = window.location.href;
    return result;
}"""


class PinduoduoScraper(BaseScraper):
    """拼多多采集器 — StealthyFetcher 浏览器渲染 (最佳努力)

    注意: 拼多多反爬极其严格, 此采集器使用浏览器渲染方案,
    可获取基础数据但稳定性有限。建议关注第三方数据服务备选。
    """

    platform = Platform.PINDUODUO

    async def scrape_product(self, task: ScrapeTask) -> Optional[ProductPrice]:
        url = self._normalize_url(task.product_url)
        goods_id = task.product_id or self._extract_goods_id(task.product_url)

        extracted_data: dict = {}
        screenshot_path: Optional[str] = None

        async def page_action(page):
            nonlocal extracted_data, screenshot_path
            try:
                await page.wait_for_selector("[class*='price'], [class*='title']", timeout=15000)
            except Exception:
                pass
            await page.wait_for_timeout(5000)

            try:
                screenshot_path = await self.screenshot.capture_full_page(
                    page, 
                    filename=f"pdd_{goods_id}.png",
                    context_str=f"Pinduoduo | ID: {goods_id}"
                )
            except Exception as e:
                log.error(f"Screenshot error: {e}")

            try:
                extracted_data = await page.evaluate(JS_EXTRACT_DATA)
            except Exception as e:
                log.error(f"JS extraction error: {e}")

        cookies = None
        if self.account_pool:
            account = self.account_pool.get_cookie(self.platform.value)
            if account:
                cookies = account["cookies"]

        try:
            kw = {
                "headless": self.config.scraping.headless,
                "network_idle": True,
                "page_action": page_action,
                "timeout": self.config.scraping.browser_timeout,
            }
            if cookies:
                kw["cookies"] = cookies

            await StealthyFetcher.async_fetch(url, **kw)

            if extracted_data.get("is_login_page"):
                log.warning(f"PDD login redirect: {url}")
                return None

            return self._build_result(extracted_data, task, goods_id, screenshot_path)

        except Exception as e:
            log.error(f"PDD scrape failed: {e}")
            return None

    def _build_result(self, data, task, goods_id, screenshot_path):
        result = ProductPrice(platform=self.platform, product_id=goods_id, product_url=task.product_url)

        titles = data.get("titles", [])
        if titles:
            result.product_name = max(titles, key=len)

        for pe in data.get("price_elements", []):
            price = self._parse_price(pe.get("text", ""))
            if price > 0 and result.current_price == 0:
                result.current_price = price

        if result.current_price == 0:
            for line in data.get("price_lines", []):
                price = self._parse_price(line)
                if price > 0:
                    result.current_price = price
                    break

        shops = [s for s in set(data.get("shops", [])) if 1 < len(s) < 30]
        if shops:
            result.shop_name = shops[0]

        for text in data.get("promos", []):
            coupon = self._parse_coupon(text)
            if coupon:
                result.coupons.append(coupon)

        for addr in data.get("addresses", []):
            city = self._extract_city(addr)
            if city:
                result.ship_from_city = city
                break

        sales = data.get("sales", [])
        if sales:
            result.sales_volume = sales[0]

        if screenshot_path:
            result.screenshot_local = screenshot_path
        result.calculate_final_price()
        return result if result.product_name else None

    @staticmethod
    def _normalize_url(url: str) -> str:
        match = re.search(r"goods_id=(\d+)", url)
        if match:
            return f"https://mobile.yangkeduo.com/goods2.html?goods_id={match.group(1)}"
        match = re.search(r"/goods/(\d+)", url)
        if match:
            return f"https://mobile.yangkeduo.com/goods2.html?goods_id={match.group(1)}"
        return url

    @staticmethod
    def _extract_goods_id(url: str) -> str:
        match = re.search(r"goods_id=(\d+)", url)
        if match:
            return match.group(1)
        match = re.search(r"/goods/(\d+)", url)
        return match.group(1) if match else ""

    @staticmethod
    def _parse_price(text: str) -> float:
        if not text:
            return 0.0
        match = re.search(r"[\d]+\.?\d*", text.replace(",", ""))
        return float(match.group()) if match else 0.0

    @staticmethod
    def _extract_city(text: str) -> str:
        match = re.search(r"([\u4e00-\u9fa5]{2,4}(?:市|区|省))", text)
        return match.group(1) if match else ""

    @staticmethod
    def _parse_coupon(text: str) -> Optional[CouponInfo]:
        text = text.strip()
        if not text or len(text) <= 1:
            return None
        match = re.search(r"满(\d+)减(\d+)", text)
        if match:
            return CouponInfo(coupon_type=CouponType.FULL_REDUCTION, description=text,
                              threshold=float(match.group(1)), discount_value=float(match.group(2)))
        # 拼团价
        match = re.search(r"拼.*?(\d+\.?\d*)", text)
        if match:
            return CouponInfo(coupon_type=CouponType.GROUP_BUY, description=text,
                              discount_value=float(match.group(1)))
        return None

    async def scrape_search(self, keyword: str, max_items: int = 5) -> list["ProductPrice"]:
        """通过拼多多移动端搜索页采集搜索结果列表

        使用 StealthyFetcher + Cookie 加载 mobile.yangkeduo.com/search_result.html
        通过 JS 提取搜索结果中的商品卡片。
        """
        from urllib.parse import quote
        from datetime import datetime, timezone

        kw_enc = quote(keyword)
        search_url = f"https://mobile.yangkeduo.com/search_result.html?search_key={kw_enc}"
        results = []

        JS_PDD_SEARCH = """() => {
            const items = [];
            // 拼多多搜索结果卡片
            const selectors = [
                "[class*='goods-list'] li",
                "[class*='product-list'] li",
                "[class*='goodsItem']",
                "[class*='goods-item']",
                "[data-goods-id]",
            ];
            let cards = [];
            for (const sel of selectors) {
                const found = document.querySelectorAll(sel);
                if (found.length > 1) { cards = Array.from(found); break; }
            }
            if (cards.length === 0) {
                // 降级: 抓所有含价格的 div
                cards = Array.from(document.querySelectorAll("div")).filter(el => {
                    const t = el.innerText || "";
                    return t.length > 5 && t.length < 400 &&
                        (t.includes("¥") || t.includes("￥") || t.includes("券")) &&
                        el.querySelector("[class*='price'], [class*='Price']");
                }).slice(0, 20);
            }
            for (const card of cards.slice(0, 10)) {
                const text = card.innerText || "";
                if (!text.trim()) continue;
                // goods_id
                let goods_id = card.getAttribute("data-goods-id") || "";
                if (!goods_id) {
                    const links = card.querySelectorAll("a[href*='goods_id='], a[href*='goods2']");
                    for (const a of links) {
                        const m = a.href.match(/goods_id=(\\d+)/);
                        if (m) { goods_id = m[1]; break; }
                    }
                }
                // 价格
                let price = "";
                const priceEl = card.querySelector("[class*='price'], [class*='Price']");
                if (priceEl) price = priceEl.innerText.trim().replace(/[^0-9.]/g, "");
                // 标题
                let title = "";
                const titleEl = card.querySelector(
                    "[class*='title'], [class*='name'], [class*='goods-name'], h2, h3"
                );
                if (titleEl) title = titleEl.innerText.trim().slice(0, 120);
                if (!price && !title) continue;
                items.push({ goods_id, price, title });
            }
            return { items, url: window.location.href,
                     is_login: window.location.href.includes("login"),
                     total_text: document.body.innerText.slice(0, 400) };
        }"""

        extracted: dict = {}

        async def page_action(page):
            nonlocal extracted
            try:
                await page.wait_for_selector(
                    "[class*='goods'], [class*='product'], [class*='item'], [class*='price']",
                    timeout=12000
                )
            except Exception:
                pass
            await page.wait_for_timeout(2500)
            try:
                extracted = await page.evaluate(JS_PDD_SEARCH)
            except Exception as e:
                log.error(f"[PDD Search] JS eval error: {e}")

        cookies = None
        account_id = None
        if self.account_pool:
            account = self.account_pool.get_cookie(self.platform.value)
            if account:
                cookies = account["cookies"]
                account_id = account["id"]
                log.info(f"[PDD Search] Using Cookie: {account_id}")

        try:
            fetch_kwargs = {
                "headless": self.config.scraping.headless,
                "network_idle": True,
                "google_search": True,
                "page_action": page_action,
                "timeout": self.config.scraping.browser_timeout,
            }
            if cookies:
                fetch_kwargs["cookies"] = cookies
            await StealthyFetcher.async_fetch(search_url, **fetch_kwargs)
        except Exception as e:
            log.error(f"[PDD Search] Fetch error: {e}")
            return []

        if extracted.get("is_login"):
            log.warning("[PDD Search] Redirected to login.")
            return []

        items = extracted.get("items", [])
        if not items:
            log.warning(f"[PDD Search] No items found. Preview: {extracted.get('total_text','')[:200]}")
            return []

        for item in items[:max_items]:
            goods_id = item.get("goods_id", "")
            title = item.get("title", "").strip()
            price_str = item.get("price", "")

            price = 0.0
            try:
                price = float(re.sub(r"[^\d.]", "", price_str)) if price_str else 0.0
            except ValueError:
                pass

            if not title:
                continue

            product = ProductPrice(
                platform=self.platform,
                product_id=goods_id or title[:20],
                product_name=title,
                current_price=price,
                final_price=price,
                product_url=(
                    f"https://mobile.yangkeduo.com/goods2.html?goods_id={goods_id}"
                    if goods_id else search_url
                ),
                scraped_at=datetime.now(timezone.utc).isoformat(),
            )
            results.append(product)
            log.info(f"[PDD Search] {title[:40]} | ¥{price:.2f}")

        return results

