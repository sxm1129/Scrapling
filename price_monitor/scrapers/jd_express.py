"""
京东秒送采集器
策略: Tier-2 浏览器渲染 (Scrapling StealthyFetcher)

京东秒送基于京东主站, 反爬体系中等偏高,
使用 StealthyFetcher 浏览器渲染 + page_action 模拟交互。

实测结果 (2026-03-12):
- item.m.jd.com 移动端页面全部 JS 渲染, HTTP Fetcher 拿到空 DOM
- 必须使用 StealthyFetcher 浏览器引擎
- 价格在 class="price" 的 div 中, 部分高价值商品显示 ¥1??9 (登录掩码)
- 商品名称在 h1.fn_goods_name 中
- 部分商品会 302 重定向到登录页 (plogin.m.jd.com)
- 截图功能正常, 可通过 page.screenshot() 保存
"""

import re
import logging
import os
from pathlib import Path
from typing import Optional

from scrapling.fetchers import StealthyFetcher

from price_monitor.models import (
    ProductPrice, ScrapeTask, Platform,
    CouponInfo, CouponType,
)
from price_monitor.screenshot import PriceScreenshot
from price_monitor.scrapers import BaseScraper

log = logging.getLogger("price_monitor.scrapers.jd_express")

# JS 数据提取脚本 — 在浏览器渲染完成后执行
# 独立定义避免 Python 内联字符串转义问题
JS_EXTRACT_DATA = """() => {
    const result = {};

    // 商品名称 (h1 标签)
    const h1s = document.querySelectorAll("h1");
    result.titles = [];
    h1s.forEach(el => {
        const t = el.textContent.trim();
        if (t && t.length > 2) result.titles.push(t.substring(0, 150));
    });

    // 价格行 (包含 ¥ 或 ￥ 的文本)
    const allText = document.body.innerText || "";
    result.price_lines = allText.split("\\n").filter(
        line => (line.includes("¥") || line.includes("￥")) && line.length < 80
    ).slice(0, 15);

    // 价格元素 (多种选择器, 兼容登录/未登录页面)
    const priceSelectors = [
        "[class*='price']",
        "[class*='Price']",
        "[class*='jdPrice']",
        "[class*='juPrice']",
        "[class*='jd-price']",
        "span[class*='yuan']",
    ];
    const priceQuery = priceSelectors.join(", ");
    const priceEls = document.querySelectorAll(priceQuery);
    result.price_elements = [];
    const seenPriceText = new Set();
    priceEls.forEach(el => {
        const text = el.innerText ? el.innerText.trim() : "";
        if (text && text.length < 60 && /[0-9]/.test(text) && !seenPriceText.has(text)) {
            seenPriceText.add(text);
            result.price_elements.push({
                cls: el.className.substring(0, 60),
                text: text
            });
        }
    });

    // 补充: 查找包含 ¥/￥ 的 span 元素 (登录态下京东常用 span 显示价格)
    if (result.price_elements.length === 0) {
        const spans = document.querySelectorAll("span");
        spans.forEach(el => {
            const text = el.innerText ? el.innerText.trim() : "";
            if (text && text.length < 30 && (text.includes("¥") || text.includes("￥")) && /[0-9]/.test(text) && !seenPriceText.has(text)) {
                seenPriceText.add(text);
                result.price_elements.push({
                    cls: "span_" + el.className.substring(0, 40),
                    text: text
                });
            }
        });
    }

    // 店铺信息
    const shopEls = document.querySelectorAll("[class*='shop'], [class*='store'], [class*='seller']");
    result.shops = [];
    shopEls.forEach(el => {
        const text = el.innerText ? el.innerText.trim() : "";
        if (text && text.length > 1 && text.length < 60) result.shops.push(text);
    });

    // 优惠券/促销
    const promoEls = document.querySelectorAll("[class*='coupon'], [class*='promo'], [class*='discount'], [class*='quan']");
    result.promos = [];
    promoEls.forEach(el => {
        const text = el.innerText ? el.innerText.trim() : "";
        if (text && text.length > 1 && text.length < 100) result.promos.push(text);
    });

    // 地址/配送
    const addrEls = document.querySelectorAll("[class*='addr'], [class*='deliver'], [class*='ship'], [class*='stock']");
    result.addresses = [];
    addrEls.forEach(el => {
        const text = el.innerText ? el.innerText.trim() : "";
        if (text && text.length > 1 && text.length < 80) result.addresses.push(text);
    });

    // 检测是否在登录页
    result.is_login_page = window.location.href.includes("plogin") || window.location.href.includes("login");
    result.current_url = window.location.href;

    return result;
}"""


class JDExpressScraper(BaseScraper):
    """京东秒送采集器

    数据来源:
    - item.m.jd.com 移动端商品页 (StealthyFetcher 浏览器渲染)

    反爬特点:
    - 全页面 JS 渲染, HTTP-only 无法获取任何内容
    - Cookie 检测 + 频率限制
    - 部分高价值商品价格掩码 (¥1??9), 需要登录
    - 某些商品页直接 302 重定向到登录页
    """

    platform = Platform.JD_EXPRESS

    async def scrape_product(self, task: ScrapeTask) -> Optional[ProductPrice]:
        """Tier-2: 使用 StealthyFetcher 浏览器渲染京东商品页

        如果 AccountPool 中有可用 Cookie, 自动注入以获取完整价格
        """

        url = self._normalize_url(task.product_url)
        sku_id = task.product_id or self._extract_sku_id(task.product_url)

        extracted_data: dict = {}
        screenshot_path: Optional[str] = None

        async def page_action(page):
            nonlocal extracted_data, screenshot_path

            # 等待价格区域加载
            try:
                await page.wait_for_selector("[class*='price']", timeout=10000)
            except Exception:
                log.warning("Price selector timeout — page may require login")

            # 额外等待 JS 渲染完成
            await page.wait_for_timeout(3000)

            # 截图
            try:
                screenshot_dir = self.screenshot.output_dir
                os.makedirs(str(screenshot_dir), exist_ok=True)
                path = str(screenshot_dir / f"jd_{sku_id}.png")
                await page.screenshot(path=path)
                screenshot_path = path
                log.info(f"Screenshot saved: {path}")
            except Exception as e:
                log.error(f"Screenshot error: {e}")

            # 通过 JS 提取数据
            try:
                extracted_data = await page.evaluate(JS_EXTRACT_DATA)
            except Exception as e:
                log.error(f"JS data extraction error: {e}")

        # 从账号池获取 Cookie
        cookies = None
        account_id = None
        if self.account_pool:
            account = self.account_pool.get_cookie(self.platform.value)
            if account:
                cookies = account["cookies"]
                account_id = account["id"]
                log.info(f"Using Cookie from account: {account_id} ({len(cookies)} cookies)")
            else:
                log.info("No cookies available — scraping without login")

        try:
            fetch_kwargs = {
                "headless": self.config.scraping.headless,
                "network_idle": True,
                "google_search": True,
                "page_action": page_action,
                "timeout": self.config.scraping.browser_timeout,
            }

            # 注入 Cookie (Playwright 格式)
            if cookies:
                fetch_kwargs["cookies"] = cookies

            page = await StealthyFetcher.async_fetch(url, **fetch_kwargs)

            if page.status not in (200, 302):
                log.warning(f"JD returned status {page.status}")
                if account_id and self.account_pool:
                    self.account_pool.mark_failed(self.platform.value, account_id)
                return None

            # 检测登录重定向
            if extracted_data.get("is_login_page"):
                log.warning(f"JD redirected to login page — Cookie may be expired: {url}")
                if account_id and self.account_pool:
                    self.account_pool.mark_failed(self.platform.value, account_id)
                return None

            result = self._build_result(extracted_data, task, sku_id, screenshot_path)

            # 如果成功获取了价格, 标记 Cookie 为有效
            if result and result.current_price > 0 and account_id and self.account_pool:
                self.account_pool.mark_active(self.platform.value, account_id)

            return result

        except Exception as e:
            log.error(f"JD scrape failed: {e}")
            return None

    def _build_result(
        self,
        data: dict,
        task: ScrapeTask,
        sku_id: str,
        screenshot_path: Optional[str],
    ) -> Optional[ProductPrice]:
        """从 JS 提取的原始数据构建 ProductPrice"""

        result = ProductPrice(
            platform=self.platform,
            product_id=sku_id,
            product_url=task.product_url,
        )

        # 商品名称 (取最长的 h1 文本, 跳过短标签如 "就是便宜")
        titles = data.get("titles", [])
        if titles:
            result.product_name = max(titles, key=len)

        # 价格提取 (优先从 price_elements, 不够则回退到 price_lines)
        price_lines = data.get("price_lines", [])
        price_elements = data.get("price_elements", [])
        login_required = False

        for pe in price_elements:
            text = pe.get("text", "")
            # 检测价格掩码 (¥1??9)
            if "??" in text:
                login_required = True
                result.extra["price_masked"] = True
                result.extra["price_raw"] = text
                continue

            price = self._parse_price(text)
            if price > 0 and result.current_price == 0:
                result.current_price = price

        # Fallback: 从 price_lines 文本行提取价格
        if result.current_price == 0 and price_lines:
            for line in price_lines:
                if "??" in line:
                    continue
                price = self._parse_price(line)
                if price > 0:
                    result.current_price = price
                    log.info(f"Price extracted from text line: {line.strip()} → {price}")
                    break

        # 如果所有价格都被掩码, 记录到 extra
        if login_required and result.current_price == 0:
            result.extra["login_required"] = True
            log.info(f"Price masked for {sku_id}, login Cookie needed")

        # 店铺名称 (去重, 取包含品牌信息的最短文本)
        shops = list(set(data.get("shops", [])))
        # 过滤掉纯导航文本
        shops = [s for s in shops if s not in ("店铺", "门店", "关注") and len(s) < 30]
        if shops:
            # 优先取包含品牌关键词的
            brand_shops = [s for s in shops if not s.startswith("关注")]
            result.shop_name = brand_shops[0] if brand_shops else shops[0]

        # 优惠券/促销
        promos = data.get("promos", [])
        for text in promos:
            coupon = self._parse_coupon_text(text)
            if coupon:
                result.coupons.append(coupon)

        # 发货/配送地址
        addresses = data.get("addresses", [])
        for addr in addresses:
            city = self._extract_city(addr)
            if city and city != "请选择":
                result.ship_from_city = city
                break

        # 截图
        if screenshot_path:
            result.screenshot_local = screenshot_path

        # 计算最终价格
        result.calculate_final_price()

        return result if result.product_name else None

    @staticmethod
    def _normalize_url(url: str) -> str:
        """统一 URL 格式 → item.m.jd.com 移动端"""
        sku_match = re.search(r"(?:item\.jd\.com|item\.m\.jd\.com/product)/(\d+)", url)
        if sku_match:
            sku_id = sku_match.group(1)
            return f"https://item.m.jd.com/product/{sku_id}.html"
        return url

    @staticmethod
    def _extract_sku_id(url: str) -> str:
        """从 URL 提取 SKU ID"""
        match = re.search(r"/(\d{5,})", url)
        return match.group(1) if match else ""

    @staticmethod
    def _parse_price(text: str) -> float:
        """从文本提取价格数值 (忽略掩码字符)"""
        if not text or "??" in text:
            return 0.0
        match = re.search(r"[\d]+\.?\d*", text.replace(",", ""))
        return float(match.group()) if match else 0.0

    @staticmethod
    def _extract_city(text: str) -> str:
        """从配送文本中提取城市"""
        city_match = re.search(r"([\u4e00-\u9fa5]{2,4}(?:市|区|仓|省))", text)
        return city_match.group(1) if city_match else text.strip()[:10]

    @staticmethod
    def _parse_coupon_text(text: str) -> Optional[CouponInfo]:
        """解析优惠券/促销文本"""
        text = text.strip()
        if not text or len(text) <= 1:
            return None

        # 跳过纯标签 ("优惠", "活动" 等)
        if text in ("优惠", "活动", "促销", "推荐优惠"):
            return None

        # "满xxx减xxx"
        match = re.search(r"满(\d+)减(\d+)", text)
        if match:
            return CouponInfo(
                coupon_type=CouponType.FULL_REDUCTION,
                description=text,
                threshold=float(match.group(1)),
                discount_value=float(match.group(2)),
            )

        # "领券减xxx" / "立减xxx"
        match = re.search(r"(?:领券|立)减(\d+)", text)
        if match:
            return CouponInfo(
                coupon_type=CouponType.STORE_COUPON,
                description=text,
                discount_value=float(match.group(1)),
            )

        # "xxx折"
        match = re.search(r"(\d+\.?\d*)折", text)
        if match:
            return CouponInfo(
                coupon_type=CouponType.DIRECT_DISCOUNT,
                description=text,
                discount_value=float(match.group(1)) / 10,
            )

        return None
