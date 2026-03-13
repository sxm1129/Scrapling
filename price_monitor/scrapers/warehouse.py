"""
前置仓采集器 — 朴朴超市 / 小象超市 / 叮咚买菜
策略: Tier-2 StealthyFetcher 浏览器渲染

前置仓平台以 App 为主, 但部分有 H5/小程序 Web 页面可用。
使用 StealthyFetcher 渲染 H5 页面提取数据。
需要传入定位信息 (城市/经纬度) 以获取对应仓库的商品和价格。
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

log = logging.getLogger("price_monitor.scrapers.warehouse")

# 共用 JS 提取脚本 (前置仓页面结构相似)
JS_EXTRACT_DATA = """() => {
    const result = {};

    const titleEls = document.querySelectorAll("h1, [class*='title'], [class*='name'], [class*='goods']");
    result.titles = [];
    titleEls.forEach(el => {
        const t = el.textContent.trim();
        if (t && t.length > 2 && t.length < 200) result.titles.push(t);
    });

    const allText = document.body.innerText || "";
    result.price_lines = allText.split("\\n").filter(
        line => (line.includes("¥") || line.includes("￥")) && line.length < 80
    ).slice(0, 15);

    const priceEls = document.querySelectorAll(
        "[class*='price'], [class*='Price'], [class*='amount'], span[class*='yuan'], [class*='num']"
    );
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

    const shopEls = document.querySelectorAll("[class*='shop'], [class*='store'], [class*='warehouse']");
    result.shops = [];
    shopEls.forEach(el => {
        const text = el.innerText ? el.innerText.trim() : "";
        if (text && text.length > 1 && text.length < 60) result.shops.push(text);
    });

    const promoEls = document.querySelectorAll("[class*='coupon'], [class*='promo'], [class*='discount'], [class*='tag']");
    result.promos = [];
    promoEls.forEach(el => {
        const text = el.innerText ? el.innerText.trim() : "";
        if (text && text.length > 1 && text.length < 100) result.promos.push(text);
    });

    result.is_login_page = window.location.href.includes("login");
    result.current_url = window.location.href;
    return result;
}"""


class _WarehouseBaseScraper(BaseScraper):
    """前置仓采集器基类 — 朴朴/小象/叮咚共用"""

    # H5 URL 模板, 子类覆盖
    _h5_base_url: str = ""
    _platform_name: str = ""

    async def scrape_product(self, task: ScrapeTask) -> Optional[ProductPrice]:
        url = task.product_url
        product_id = task.product_id or self._extract_id(url)

        extracted_data: dict = {}
        screenshot_path: Optional[str] = None

        async def page_action(page):
            nonlocal extracted_data, screenshot_path
            try:
                await page.wait_for_selector("[class*='price'], [class*='title']", timeout=12000)
            except Exception:
                pass
            await page.wait_for_timeout(4000)

            try:
                sd = self.screenshot.output_dir
                os.makedirs(str(sd), exist_ok=True)
                path = str(sd / f"{self._platform_name}_{product_id}.png")
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
                log.warning(f"{self._platform_name} login redirect: {url}")
                return None

            return self._build_result(extracted_data, task, product_id, screenshot_path)

        except Exception as e:
            log.error(f"{self._platform_name} scrape failed: {e}")
            return None

    def _build_result(self, data, task, product_id, screenshot_path):
        result = ProductPrice(platform=self.platform, product_id=product_id, product_url=task.product_url)

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

        shops = [s for s in set(data.get("shops", [])) if 1 < len(s) < 40]
        if shops:
            result.shop_name = shops[0]

        # 前置仓: 记录仓库/配送范围
        if task.city:
            result.ship_from_city = task.city
            result.warehouse_name = f"{self._platform_name}_{task.city}"

        for text in data.get("promos", []):
            coupon = self._parse_coupon(text)
            if coupon:
                result.coupons.append(coupon)

        if screenshot_path:
            result.screenshot_local = screenshot_path
        result.calculate_final_price()
        return result if result.product_name else None

    @staticmethod
    def _extract_id(url: str) -> str:
        match = re.search(r"(?:id|productId|goods_id)=(\w+)", url)
        if match:
            return match.group(1)
        match = re.search(r"/(\d{6,})", url)
        return match.group(1) if match else ""

    @staticmethod
    def _parse_price(text: str) -> float:
        if not text:
            return 0.0
        match = re.search(r"[\d]+\.?\d*", text.replace(",", ""))
        return float(match.group()) if match else 0.0

    @staticmethod
    def _parse_coupon(text: str) -> Optional[CouponInfo]:
        text = text.strip()
        if not text or len(text) <= 1:
            return None
        match = re.search(r"满(\d+)减(\d+)", text)
        if match:
            return CouponInfo(coupon_type=CouponType.FULL_REDUCTION, description=text,
                              threshold=float(match.group(1)), discount_value=float(match.group(2)))
        return None


class PupuScraper(_WarehouseBaseScraper):
    """朴朴超市采集器"""
    platform = Platform.PUPU
    _platform_name = "pupu"
    _h5_base_url = "https://j1.pupuapi.com"  # 朴朴 H5


class XiaoxiangScraper(_WarehouseBaseScraper):
    """小象超市 (美团买菜) 采集器"""
    platform = Platform.XIAOXIANG
    _platform_name = "xiaoxiang"
    _h5_base_url = "https://meituan.com"  # 小象超市 H5


class DingdongScraper(_WarehouseBaseScraper):
    """叮咚买菜采集器"""
    platform = Platform.DINGDONG
    _platform_name = "dingdong"
    _h5_base_url = "https://h5.m.ddxq.mobi"  # 叮咚买菜 H5
