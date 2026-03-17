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
                screenshot_path = await self.screenshot.capture_full_page(
                    page, 
                    filename=f"jd_{sku_id}.png",
                    context_str=f"JD Express | SKU: {sku_id}"
                )
            except Exception as e:
                log.error(f"Screenshot error: {e}")

            # 通过 JS 提取数据
            try:
                extracted_data = await page.evaluate(JS_EXTRACT_DATA)
            except Exception as e:
                log.error(f"JS data extraction error: {e}")

            # 通过 Regex 提取 window._itemOnly
            try:
                content = await page.content()
                import re, json
                match = re.search(r'window\._itemOnly\s*=\s*(.*?);\s*window\.', content, re.DOTALL)
                if match:
                    json_text = match.group(1).strip()
                    if json_text.startswith('('): json_text = json_text[1:-1]
                    item_data = json.loads(json_text).get("item", {})
                    extracted_data["_itemOnly"] = item_data
            except Exception as e:
                log.error(f"SSR extract error: {e}")

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
        if data.get("_itemOnly", {}).get("skuName"):
            result.product_name = data["_itemOnly"]["skuName"]
        elif titles:
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
        # 优先读取 _itemOnly 的 vanderName 或 brandName
        if data.get("_itemOnly", {}).get("brandName"):
            result.shop_name = data["_itemOnly"]["brandName"] + "旗舰店"  # 推测
        elif shops:
            shops = [s for s in shops if s not in ("店铺", "门店", "关注") and len(s) < 30]
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

    async def scrape_search(self, keyword: str, max_items: int = 5) -> list["ProductPrice"]:
        """通过京东移动端搜索页采集搜索结果列表

        使用 StealthyFetcher + Cookie 渲染 so.m.jd.com/ware/search.action，
        通过 JS 提取搜索结果卡片中的商品数据。
        """
        from urllib.parse import quote
        from datetime import datetime, timezone

        kw_enc = quote(keyword)
        search_url = f"https://so.m.jd.com/ware/search.action?keyword={kw_enc}"
        results = []

        JS_JD_SEARCH = """() => {
            const items = [];

            // 1. 尝试点掉可能出现的弹窗（移动设备提示 QR / App 下载）
            const closeButtons = document.querySelectorAll(
                "[class*='close'], [class*='modal-close'], [class*='dialog'] button, [class*='popup'] button"
            );
            for (const btn of closeButtons) {
                const t = btn.innerText || "";
                if (t.includes("取消") || t.includes("关闭") || t.includes("X") || t.includes("×")) {
                    try { btn.click(); } catch(e) {}
                }
            }

            // 2. 尝试 DOM 卡片选择
            const selectors = [
                "ul.m-goods-list > li", "ul.goods-list > li", "ul[class*='goods'] > li",
                "[class*='m-goods-item']", "[class*='search-goods'] li",
                "[class*='m-search-item']", "[class*='search-item']",
                "[data-sku]", "[class*='goods-item']",
            ];
            let cards = [];
            for (const sel of selectors) {
                const found = document.querySelectorAll(sel);
                if (found.length > 1) { cards = Array.from(found); break; }
            }
            // 降级: 取含 ¥ 和商品链接的 li 元素
            if (cards.length === 0) {
                cards = Array.from(document.querySelectorAll("li")).filter(el => {
                    const t = el.innerText || "";
                    return t.length > 10 && t.length < 800 &&
                        (t.includes("¥") || t.includes("￥")) &&
                        el.querySelector("a");
                }).slice(0, 20);
            }

            for (const card of cards.slice(0, 10)) {
                const text = card.innerText || "";
                if (!text.trim()) continue;
                let sku_id = card.getAttribute("data-sku") || card.getAttribute("data-skuid") || "";
                if (!sku_id) {
                    const links = card.querySelectorAll("a");
                    for (const a of links) {
                        const m = (a.getAttribute("href") || "").match(/\/product\/(\d+)|goods_id=(\d+)|(?:id|skuid)=(\d+)/);
                        if (m) { sku_id = m[1] || m[2] || m[3] || ""; if (sku_id) break; }
                    }
                }
                let price = "";
                const priceEl = card.querySelector(
                    ".m-price, [class*='price'][class*='cur'], [class*='price-now'], strong.price, [class*='Price']"
                ) || card.querySelector("[class*='price'], strong");
                if (priceEl) price = priceEl.innerText.trim().replace(/[^0-9.]/g, "");
                let title = "";
                const titleEl = card.querySelector(
                    "[class*='goods-title'], [class*='sku-name'], [class*='title'], [class*='name'], h3, h2"
                );
                if (titleEl) title = titleEl.innerText.trim().slice(0, 120);
                
                let shop = "";
                const shopEl = card.querySelector("[class*='shop'], [class*='store'], [class*='seller'], [class*='shop-name']");
                if (shopEl) shop = shopEl.innerText.trim().slice(0, 60);

                if (!price && !title) continue;
                items.push({ sku_id, price, title, shop });
            }

            // 3. 如果 DOM 取不到, 做文本行解析 (备用)
            let text_items = [];
            if (items.length === 0) {
                const bodyText = document.body.innerText || "";
                const lines = bodyText.split("\\n").map(l => l.trim()).filter(Boolean);
                let cur = { title: "", price: "", sku_id: "" };
                for (const line of lines) {
                    if ((line.includes("¥") || line.includes("￥")) && /\d+\.?\d*/.test(line)) {
                        const pm = line.match(/(\d+\.?\d*)/);
                        if (pm && cur.price === "") cur.price = pm[1];
                    } else if (line.length > 8 && line.length < 150 && !line.includes("评价") &&
                               !line.includes("筛选") && !line.includes("综合") && /[\u4e00-\u9fa5]/.test(line)) {
                        if (cur.title && cur.price) {
                            text_items.push({ ...cur });
                            cur = { title: line, price: "", sku_id: "" };
                        } else {
                            cur.title = line;
                        }
                    }
                }
                if (cur.title && cur.price) text_items.push(cur);
                // 提取链接中的 sku_id
                const allLinks = document.querySelectorAll("a[href*='item.m.jd.com'], a[href*='/product/']");
                const skuIds = Array.from(allLinks).map(a => {
                    const m = a.href.match(/\/product\/(\d+)/);
                    return m ? m[1] : "";
                }).filter(Boolean);
                for (let i = 0; i < text_items.length && i < skuIds.length; i++) {
                    text_items[i].sku_id = skuIds[i];
                }
            }

            return {
                items: items.length > 0 ? items : text_items,
                url: window.location.href,
                is_login: window.location.href.includes("passport.jd.com"),
                total_text: document.body.innerText.slice(0, 600)
            };
        }"""

        extracted: dict = {}

        async def page_action(page):
            nonlocal extracted
            # 等待商品列表加载
            try:
                await page.wait_for_selector(
                    "li, [class*='goods'], [class*='search'], [class*='price']",
                    timeout=12000
                )
            except Exception:
                pass
            await page.wait_for_timeout(2000)
            
            # 强力关闭弹窗和遮罩（特别是二维码）
            try:
                await page.add_style_tag(content="""
                    [class*='modal'], [class*='mask'], [class*='dialog'], [class*='popup'], [class*='qrcode'] {
                        display: none !important; opacity: 0 !important; pointer-events: none !important; z-index: -999 !important;
                    }
                """)
                await page.evaluate("""() => {
                    const btns = document.querySelectorAll('[class*="close"], [class*="modal"] button');
                    for (const b of btns) {
                        const t = b.innerText || "";
                        if (t.includes("取消") || t.includes("关闭") || t.includes("×") || t.includes("X")) b.click();
                    }
                }""")
            except Exception:
                pass
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(500)
            try:
                extracted = await page.evaluate(JS_JD_SEARCH)
            except Exception as e:
                log.error(f"[JD Search] JS eval error: {e}")


        cookies = None
        account_id = None
        if self.account_pool:
            account = self.account_pool.get_cookie(self.platform.value)
            if account:
                cookies = account["cookies"]
                account_id = account["id"]
                log.info(f"[JD Search] Using Cookie: {account_id} ({len(cookies)} cookies)")

        try:
            fetch_kwargs = {
                "headless": self.config.scraping.headless,  # Was hardcoded to False, leading to Linux crashes
                "network_idle": True,
                "google_search": True,
                "page_action": page_action,
                "timeout": self.config.scraping.browser_timeout,
            }
            if cookies:
                fetch_kwargs["cookies"] = cookies
            await StealthyFetcher.async_fetch(search_url, **fetch_kwargs)
        except Exception as e:
            log.error(f"[JD Search] Fetch error: {e}")
            return []

        if extracted.get("is_login"):
            log.warning(f"[JD Search] Redirected to login. Cookie may be expired.")
            return []

        items = extracted.get("items", [])
        if not items:
            log.warning(f"[JD Search] No items extracted. URL={extracted.get('url')} "
                        f"Text: {extracted.get('total_text','')[:200]}")
            return []

        for item in items[:max_items]:
            sku_id = item.get("sku_id", "")
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
                product_id=sku_id or title[:20],
                product_name=title,
                current_price=price,
                final_price=price,
                shop_name=item.get("shop", "").strip(),
                product_url=f"https://item.m.jd.com/product/{sku_id}.html" if sku_id else search_url,
                scraped_at=datetime.now(timezone.utc).isoformat(),
            )
            results.append(product)
            log.info(f"[JD Search] {title[:40]} | ¥{price:.2f}")

        return results
