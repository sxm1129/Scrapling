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
                sd = self.screenshot.output_dir
                os.makedirs(str(sd), exist_ok=True)
                path = str(sd / f"pdd_{goods_id}.png")
                await page.screenshot(path=path)
                screenshot_path = path
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
