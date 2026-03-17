"""
淘宝/天猫采集器
策略: Tier-2 StealthyFetcher 浏览器渲染

淘宝/天猫共用阿里安全体系, 登录态通过 Cookie 共享。
移动端 H5 页面通过 StealthyFetcher 渲染后提取数据。
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

log = logging.getLogger("price_monitor.scrapers.taobao")

JS_EXTRACT_DATA = """() => {
    const result = {};

    // 商品名称
    const titleEls = document.querySelectorAll(
        "h1, [class*='title'], [class*='Title'], [data-spm*='title']"
    );
    result.titles = [];
    titleEls.forEach(el => {
        const t = el.textContent.trim();
        if (t && t.length > 5 && t.length < 200) result.titles.push(t);
    });

    // 价格行
    const allText = document.body.innerText || "";
    result.price_lines = allText.split("\\n").filter(
        line => (line.includes("¥") || line.includes("￥") || line.includes("到手价")) && line.length < 80
    ).slice(0, 15);

    // 价格元素
    result.price_elements = [];
    const seen = new Set();
    
    // 首选策略: 直接探测天猫/淘宝全局应用上下文对象以获取 100% 准确的价格
    try {
        if (typeof window !== "undefined" && window.__ICE_APP_CONTEXT__) {
            const ctx = window.__ICE_APP_CONTEXT__;
            let exactPriceText = null;
            if (ctx.pcTrade && ctx.pcTrade.pcBuyParams && ctx.pcTrade.pcBuyParams.current_price) {
                exactPriceText = ctx.pcTrade.pcBuyParams.current_price.toString();
            } else if (ctx.priceVO && ctx.priceVO.price && ctx.priceVO.price.priceText) {
                exactPriceText = ctx.priceVO.price.priceText;
            }
            if (exactPriceText) {
                seen.add(exactPriceText);
                result.price_elements.push({cls: "ice_app_context", text: exactPriceText});
            }
        }
    } catch (e) { console.warn("Error parsing __ICE_APP_CONTEXT__", e); }

    // 回退策略: DOM 扫描
    if (result.price_elements.length === 0) {
        const priceSelectors = [
            "[class*='price']", "[class*='Price']",
            "[class*='originPrice']", "[class*='realPrice']",
            "em[class*='tb-rmb-num']", "[id*='J_PromoPriceNum']",
            "span[class*='yuan']",
        ];
        const priceEls = document.querySelectorAll(priceSelectors.join(", "));
        priceEls.forEach(el => {
            const text = el.innerText ? el.innerText.trim() : "";
            if (text && text.length < 60 && /[0-9]/.test(text) && !seen.has(text)) {
                seen.add(text);
                result.price_elements.push({cls: el.className.substring(0, 60), text});
            }
        });
    }

    // 补充 span 搜索
    if (result.price_elements.length === 0) {
        const spans = document.querySelectorAll("span");
        spans.forEach(el => {
            const text = el.innerText ? el.innerText.trim() : "";
            if (text && text.length < 30 && (text.includes("¥") || text.includes("￥")) && /[0-9]/.test(text) && !seen.has(text)) {
                seen.add(text);
                result.price_elements.push({cls: "span", text});
            }
        });
    }

    // 店铺
    const shopEls = document.querySelectorAll(
        "[class*='shop'], [class*='store'], [class*='seller'], [class*='shopName']"
    );
    result.shops = [];
    shopEls.forEach(el => {
        const text = el.innerText ? el.innerText.trim() : "";
        if (text && text.length > 1 && text.length < 60) result.shops.push(text);
    });

    // 优惠券
    const promoEls = document.querySelectorAll(
        "[class*='coupon'], [class*='promo'], [class*='discount'], [class*='quan'], [class*='Coupon']"
    );
    result.promos = [];
    promoEls.forEach(el => {
        const text = el.innerText ? el.innerText.trim() : "";
        if (text && text.length > 1 && text.length < 100) result.promos.push(text);
    });

    // 发货地
    const addrEls = document.querySelectorAll(
        "[class*='delivery'], [class*='location'], [class*='ship'], [class*='addr']"
    );
    result.addresses = [];
    addrEls.forEach(el => {
        const text = el.innerText ? el.innerText.trim() : "";
        if (text && text.length > 1 && text.length < 80) result.addresses.push(text);
    });

    // 销量
    const salesEls = document.querySelectorAll("[class*='sale'], [class*='sold'], [class*='deal']");
    result.sales = [];
    salesEls.forEach(el => {
        const text = el.innerText ? el.innerText.trim() : "";
        if (text && /[0-9]/.test(text) && text.length < 30) result.sales.push(text);
    });

    // 登录检测
    result.is_login_page = window.location.href.includes("login") ||
        window.location.href.includes("LoginForm");
    result.current_url = window.location.href;

    return result;
}"""


class TaobaoScraper(BaseScraper):
    """淘宝采集器 — StealthyFetcher 浏览器渲染"""

    platform = Platform.TAOBAO

    async def scrape_product(self, task: ScrapeTask) -> Optional[ProductPrice]:
        url = self._normalize_url(task.product_url)
        item_id = task.product_id or self._extract_item_id(task.product_url)

        extracted_data: dict = {}
        screenshot_path: Optional[str] = None

        async def page_action(page):
            nonlocal extracted_data, screenshot_path
            try:
                await page.wait_for_selector("[class*='price'], [class*='title']", timeout=12000)
            except Exception:
                log.warning("Selector timeout — page may require login")
            await page.wait_for_timeout(3000)

            try:
                screenshot_path = await self.screenshot.capture_full_page(
                    page, 
                    filename=f"taobao_{item_id}.png",
                    context_str=f"Taobao | Item: {item_id}"
                )
            except Exception as e:
                log.error(f"Screenshot error: {e}")

            try:
                extracted_data = await page.evaluate(JS_EXTRACT_DATA)
            except Exception as e:
                log.error(f"JS extraction error: {e}")

        cookies = None
        account_id = None
        if self.account_pool:
            account = self.account_pool.get_cookie(self.platform.value)
            if account:
                cookies = account["cookies"]
                account_id = account["id"]
                log.info(f"Using Cookie: {account_id} ({len(cookies)} cookies)")

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

            page = await StealthyFetcher.async_fetch(url, **fetch_kwargs)

            if extracted_data.get("is_login_page"):
                log.warning(f"Redirected to login — Cookie expired: {url}")
                if account_id and self.account_pool:
                    self.account_pool.mark_failed(self.platform.value, account_id)
                return None

            return self._build_result(extracted_data, task, item_id, screenshot_path)

        except Exception as e:
            log.error(f"Taobao scrape failed: {e}")
            return None

    def _build_result(self, data, task, item_id, screenshot_path):
        result = ProductPrice(platform=self.platform, product_id=item_id, product_url=task.product_url)

        titles = data.get("titles", [])
        if titles:
            result.product_name = max(titles, key=len)

        # 价格
        for pe in data.get("price_elements", []):
            text = pe.get("text", "")
            price = self._parse_price(text)
            if price > 0 and result.current_price == 0:
                result.current_price = price

        if result.current_price == 0:
            for line in data.get("price_lines", []):
                price = self._parse_price(line)
                if price > 0:
                    result.current_price = price
                    break

        # 店铺
        shops = list(set(data.get("shops", [])))
        shops = [s for s in shops if len(s) > 1 and len(s) < 30 and s not in ("店铺", "关注")]
        if shops:
            result.shop_name = shops[0]

        # 优惠券
        for text in data.get("promos", []):
            coupon = self._parse_coupon(text)
            if coupon:
                result.coupons.append(coupon)

        # 发货地
        for addr in data.get("addresses", []):
            city = self._extract_city(addr)
            if city:
                result.ship_from_city = city
                break

        # 销量
        sales = data.get("sales", [])
        if sales:
            result.sales_volume = sales[0]

        if screenshot_path:
            result.screenshot_local = screenshot_path

        result.calculate_final_price()
        return result if result.product_name else None

    @staticmethod
    def _normalize_url(url: str) -> str:
        match = re.search(r"[?&]id=(\d+)", url)
        if match:
            return f"https://h5.m.taobao.com/awp/core/detail.htm?id={match.group(1)}"
        if "detail.tmall.com" in url or "item.taobao.com" in url:
            match = re.search(r"id=(\d+)", url)
            if match:
                return f"https://h5.m.taobao.com/awp/core/detail.htm?id={match.group(1)}"
        return url

    @staticmethod
    def _extract_item_id(url: str) -> str:
        match = re.search(r"id=(\d+)", url)
        return match.group(1) if match else ""

    @staticmethod
    def _parse_price(text: str) -> float:
        if not text or "??" in text:
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
        if not text or len(text) <= 1 or text in ("优惠", "活动", "促销"):
            return None
        match = re.search(r"满(\d+)减(\d+)", text)
        if match:
            return CouponInfo(coupon_type=CouponType.FULL_REDUCTION, description=text,
                              threshold=float(match.group(1)), discount_value=float(match.group(2)))
        match = re.search(r"(?:领券|立)减(\d+)", text)
        if match:
            return CouponInfo(coupon_type=CouponType.STORE_COUPON, description=text,
                              discount_value=float(match.group(1)))
        match = re.search(r"(\d+\.?\d*)折", text)
        if match:
            return CouponInfo(coupon_type=CouponType.DIRECT_DISCOUNT, description=text,
                              discount_value=float(match.group(1)) / 10)
        return None

    async def scrape_search(self, keyword: str, max_items: int = 5) -> list["ProductPrice"]:
        """通过淘宝移动端搜索页采集搜索结果列表

        使用 StealthyFetcher 加 Cookie 渲染 s.m.taobao.com/search，
        通过 JS 提取搜索结果卡片中的商品数据。
        """
        from urllib.parse import quote
        from datetime import datetime, timezone

        kw_enc = quote(keyword)
        search_url = f"https://s.m.taobao.com/h5?q={kw_enc}"

        # 天猫子类使用天猫 tab
        if self.platform.value == "tmall":
            search_url = f"https://s.m.taobao.com/h5?q={kw_enc}&tab=tmall"

        results = []

        JS_SEARCH_LIST = """() => {
            const items = [];
            // 淘宝搜索结果卡片: .item / [class*='item'] / [data-cache-key]
            const selectors = [
                "[class*='m-itemlist'] li",
                "[class*='item-list'] li",
                "[data-sku]",
                "[class*='itemcard']",
            ];
            let cards = [];
            for (const sel of selectors) {
                const found = document.querySelectorAll(sel);
                if (found.length > 2) { cards = Array.from(found); break; }
            }
            if (cards.length === 0) {
                // fallback: 任何含价格的 div
                cards = Array.from(document.querySelectorAll("div")).filter(el =>
                    el.querySelector && el.querySelector("[class*='price'], [class*='Price']")
                    && el.innerText && el.innerText.length > 5 && el.innerText.length < 500
                ).slice(0, 20);
            }
            for (const card of cards.slice(0, 10)) {
                const text = card.innerText || "";
                if (!text.trim()) continue;
                // 提取 item_id
                const links = card.querySelectorAll("a[href*='item_id='], a[href*='/item/']");
                let item_id = "";
                for (const a of links) {
                    const m = a.href.match(/item_id=(\\d+)|\\/item\\/(\\d+)/);
                    if (m) { item_id = m[1] || m[2]; break; }
                }
                // 提取价格
                let price = "";
                const priceEl = card.querySelector(
                    "[class*='price'], [class*='Price'], [class*='yuan'], em"
                );
                if (priceEl) price = priceEl.innerText.trim().replace(/[^0-9.]/g, "");
                // 提取标题
                let title = "";
                const titleEl = card.querySelector(
                    "[class*='title'], [class*='name'], h3, h2"
                );
                if (titleEl) title = titleEl.innerText.trim().slice(0, 120);
                if (!price && !title) continue;
                items.push({ item_id, price, title, raw: text.slice(0, 300) });
            }
            return { items, url: window.location.href,
                     total_text: document.body.innerText.slice(0, 500) };
        }"""

        extracted: dict = {}

        async def page_action(page):
            nonlocal extracted
            try:
                await page.wait_for_selector(
                    "[class*='item'], [class*='price'], [class*='card']", timeout=12000
                )
            except Exception:
                pass
            await page.wait_for_timeout(2000)
            try:
                extracted = await page.evaluate(JS_SEARCH_LIST)
            except Exception as e:
                log.error(f"[Taobao Search] JS eval error: {e}")

        cookies = None
        account_id = None
        if self.account_pool:
            account = self.account_pool.get_cookie(self.platform.value)
            if account:
                cookies = account["cookies"]
                account_id = account["id"]
                log.info(f"[Taobao Search] Using Cookie: {account_id}")

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
            log.error(f"[Taobao Search] Fetch error: {e}")
            return []

        # 检查是否被重定向到登录页
        if "login" in extracted.get("url", "").lower():
            log.warning(f"[Taobao Search] Redirected to login. Cookie may be expired.")
            return []

        items = extracted.get("items", [])
        if not items:
            log.warning(f"[Taobao Search] No items extracted. URL: {extracted.get('url')} "
                        f"Text preview: {extracted.get('total_text', '')[:200]}")
            return []

        for item in items[:max_items]:
            item_id = item.get("item_id", "")
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
                product_id=item_id or title[:20],
                product_name=title,
                current_price=price,
                final_price=price,
                product_url=f"https://item.taobao.com/item.htm?id={item_id}" if item_id else search_url,
                scraped_at=datetime.now(timezone.utc).isoformat(),
            )
            results.append(product)
            log.info(f"[{self.platform.value} Search] {title[:40]} | ¥{price:.2f}")

        return results


class TmallScraper(TaobaoScraper):
    """天猫采集器 — 继承淘宝采集器 (共享阿里安全体系)"""
    platform = Platform.TMALL

    @staticmethod
    def _normalize_url(url: str) -> str:
        match = re.search(r"id=(\d+)", url)
        if match:
            return f"https://detail.m.tmall.com/item.htm?id={match.group(1)}"
        return url

