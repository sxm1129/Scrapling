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
    const priceSelectors = [
        "[class*='price']", "[class*='Price']",
        "[class*='originPrice']", "[class*='realPrice']",
        "em[class*='tb-rmb-num']", "[id*='J_PromoPriceNum']",
        "span[class*='yuan']",
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
                screenshot_dir = self.screenshot.output_dir
                os.makedirs(str(screenshot_dir), exist_ok=True)
                path = str(screenshot_dir / f"taobao_{item_id}.png")
                await page.screenshot(path=path)
                screenshot_path = path
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


class TmallScraper(TaobaoScraper):
    """天猫采集器 — 继承淘宝采集器 (共享阿里安全体系)"""
    platform = Platform.TMALL

    @staticmethod
    def _normalize_url(url: str) -> str:
        match = re.search(r"id=(\d+)", url)
        if match:
            return f"https://detail.m.tmall.com/item.htm?id={match.group(1)}"
        return url
