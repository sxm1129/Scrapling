"""
淘宝闪购采集器
策略: Tier-2 StealthyFetcher 浏览器渲染 + MTOP API 拦截

支持两种模式:
  1. 单品模式: 通过 product_url 抓取单个商品详情
  2. 搜索模式: 通过 keyword 在手淘 H5 搜索页 (s.m.taobao.com) 搜索并拦截 API

搜索模式使用 tab=sg (闪购 Tab) 筛选闪购商品,
通过拦截 mtop.relationrecommend API 获取结构化 JSON 数据。
"""

import json
import re
import logging
import os
from typing import Optional
from urllib.parse import quote

from scrapling.fetchers import StealthyFetcher

from price_monitor.models import (
    ProductPrice, ScrapeTask, Platform,
    CouponInfo, CouponType,
)
from price_monitor.scrapers import BaseScraper

log = logging.getLogger("price_monitor.scrapers.taobao_flash")

# ── 单品模式 JS 提取 ──
JS_EXTRACT_DETAIL = """() => {
    const result = {};

    const titleEls = document.querySelectorAll("h1, [class*='title'], [class*='name']");
    result.titles = [];
    titleEls.forEach(el => {
        const t = el.textContent.trim();
        if (t && t.length > 3 && t.length < 200) result.titles.push(t);
    });

    const allText = document.body.innerText || "";
    result.price_lines = allText.split("\\n").filter(
        line => (line.includes("¥") || line.includes("￥")) && line.length < 80
    ).slice(0, 15);

    const priceEls = document.querySelectorAll(
        "[class*='price'], [class*='Price'], [class*='amount'], span[class*='yuan']"
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

    const shopEls = document.querySelectorAll("[class*='shop'], [class*='store'], [class*='seller']");
    result.shops = [];
    shopEls.forEach(el => {
        const text = el.innerText ? el.innerText.trim() : "";
        if (text && text.length > 1 && text.length < 60) result.shops.push(text);
    });

    const promoEls = document.querySelectorAll("[class*='coupon'], [class*='promo'], [class*='discount']");
    result.promos = [];
    promoEls.forEach(el => {
        const text = el.innerText ? el.innerText.trim() : "";
        if (text && text.length > 1 && text.length < 100) result.promos.push(text);
    });

    const addrEls = document.querySelectorAll("[class*='delivery'], [class*='ship'], [class*='addr']");
    result.addresses = [];
    addrEls.forEach(el => {
        const text = el.innerText ? el.innerText.trim() : "";
        if (text && text.length > 1 && text.length < 80) result.addresses.push(text);
    });

    result.is_login_page = window.location.href.includes("login");
    result.current_url = window.location.href;
    return result;
}"""

# ── MTOP API URL 匹配模式 ──
MTOP_SEARCH_PATTERN = "mtop.relationrecommend.wirelessrecommend.recommend"


class TaobaoFlashScraper(BaseScraper):
    """淘宝闪购/淘鲜达采集器

    支持两种调用模式:
    - scrape_product(task): 单品/搜索采集 (根据 task.keyword 自动判断)
    - search(keyword): 搜索模式, 返回商品列表
    """

    platform = Platform.TAOBAO_FLASH

    # ═══════════════════════════════════════════════════════
    # 公开接口
    # ═══════════════════════════════════════════════════════

    async def scrape_product(self, task: ScrapeTask) -> Optional[ProductPrice]:
        """根据 task 内容自动选择模式"""
        if task.keyword:
            # 搜索模式: 返回第一个匹配商品
            products = await self.search(task.keyword)
            return products[0] if products else None
        else:
            # 单品模式
            return await self._scrape_single(task)

    async def search(self, keyword: str) -> list[ProductPrice]:
        """搜索模式 — 手淘 H5 搜索 + MTOP API 拦截

        使用 s.m.taobao.com/h5?q={keyword}&tab=sg 搜索,
        拦截 MTOP API 获取结构化数据。

        :param keyword: 搜索关键词
        :return: ProductPrice 列表
        """
        search_url = f"https://s.m.taobao.com/h5?q={quote(keyword)}&tab=sg"
        log.info(f"Flash search: {keyword} → {search_url}")

        api_items: list[dict] = []
        screenshot_path: Optional[str] = None

        async def page_action(page):
            nonlocal api_items, screenshot_path

            # 1. 注册 API 拦截
            async def handle_response(response):
                if MTOP_SEARCH_PATTERN not in response.url:
                    return
                try:
                    body_bytes = await response.body()
                    
                    try:
                        if body_bytes.startswith(b'\x1f\x8b'):
                            import gzip
                            body = gzip.decompress(body_bytes).decode('utf-8', errors='ignore')
                        else:
                            enc = response.headers.get("content-encoding", "").lower()
                            if "br" in enc:
                                import brotli
                                body = brotli.decompress(body_bytes).decode('utf-8', errors='ignore')
                            else:
                                body = body_bytes.decode('utf-8', errors='ignore')
                    except Exception:
                        body = body_bytes.decode('utf-8', errors='ignore')

                    if len(body) < 1000:
                        return
                    
                    items = self._parse_mtop_response(body)
                    if items:
                        log.info(f"  ⚡ MTOP api parsed: {len(items)} items")
                        api_items.extend(items)
                except Exception as e:
                    pass

            page.on("response", handle_response)

            # 2. 注入 Cookie
            cookies = self._get_taobao_cookies()
            if cookies:
                await page.context.add_cookies(cookies)
                log.info(f"  Injected {len(cookies)} cookies")

            # 3. 导航到搜索页面
            try:
                await page.goto(search_url, wait_until="domcontentloaded", timeout=25000)
            except Exception as e:
                log.warning(f"  Navigation: {e}")

            await page.wait_for_timeout(5000)
            log.info(f"  Current URL: {page.url}")

            # 4. 登录检测
            if "login" in page.url:
                log.warning("  Redirected to login page — Cookie expired")
                return

            # 5. 滚动加载更多商品
            for i in range(8):
                await page.evaluate("window.scrollBy(0, 600)")
                await page.wait_for_timeout(800)
            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(500)

            # 6. 截图
            try:
                screenshot_path = await self.screenshot.capture_full_page(
                    page, 
                    filename=f"taobao_flash_search_{keyword[:10]}.png",
                    context_str=f"Taobao Flash | Search: {keyword[:10]}"
                )
            except Exception as e:
                log.error(f"  Screenshot error: {e}")

        try:
            await StealthyFetcher.async_fetch(
                search_url,
                headless=self.config.scraping.headless,
                network_idle=False,
                page_action=page_action,
                timeout=self.config.scraping.browser_timeout,
            )
        except Exception as e:
            log.error(f"Flash search failed: {e}")
            return []

        # 7. 将 API 数据转换为 ProductPrice 列表
        products = []
        seen_ids = set()
        for item in api_items:
            item_id = item.get("item_id", "")
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)

            pp = self._api_item_to_product(item, keyword, screenshot_path)
            if pp:
                products.append(pp)

        log.info(f"Flash search complete: {len(products)} products for '{keyword}'")
        return products

    # ═══════════════════════════════════════════════════════
    # 单品模式 (原有逻辑)
    # ═══════════════════════════════════════════════════════

    async def _scrape_single(self, task: ScrapeTask) -> Optional[ProductPrice]:
        """单品模式 — 通过 product_url 抓取"""
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
            await page.wait_for_timeout(3000)

            try:
                screenshot_path = await self.screenshot.capture_full_page(
                    page, 
                    filename=f"taobao_flash_{product_id}.png",
                    context_str=f"Taobao Flash | ID: {product_id}"
                )
            except Exception as e:
                log.error(f"Screenshot error: {e}")

            try:
                extracted_data = await page.evaluate(JS_EXTRACT_DETAIL)
            except Exception as e:
                log.error(f"JS extraction error: {e}")

        cookies = self._get_taobao_cookies()

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
                log.warning(f"Flash login redirect: {url}")
                return None

            return self._build_detail_result(extracted_data, task, product_id, screenshot_path)

        except Exception as e:
            log.error(f"Flash single scrape failed: {e}")
            return None

    # ═══════════════════════════════════════════════════════
    # Cookie 获取
    # ═══════════════════════════════════════════════════════

    def _get_taobao_cookies(self) -> Optional[list]:
        """获取淘宝 Cookie (阿里共享登录态)"""
        if not self.account_pool:
            return None
        # 优先用淘宝 Cookie (阿里系通用)
        account = self.account_pool.get_cookie("taobao")
        if not account:
            account = self.account_pool.get_cookie(self.platform.value)
        return account["cookies"] if account else None

    # ═══════════════════════════════════════════════════════
    # MTOP API 解析
    # ═══════════════════════════════════════════════════════

    @staticmethod
    def _parse_mtop_response(body: str) -> list[dict]:
        """解析 MTOP JSONP 响应, 提取商品列表"""
        # 剥离 JSONP 包装: mtopjsonp6({...})
        stripped = body.strip()
        m = re.match(r"mtopjsonp\d+\((.+)\)$", stripped, re.DOTALL)
        json_str = m.group(1) if m else stripped

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return []

        items_array = data.get("data", {}).get("itemsArray", [])
        results = []

        for item in items_array:
            title = item.get("title", "")
            if not title:
                continue
            # 清理 HTML 标签
            title = re.sub(r"<[^>]+>", "", title).strip()

            price_str = item.get("price", "")
            try:
                price = float(price_str) if price_str else 0.0
            except (ValueError, TypeError):
                price = 0.0

            # 提取闪购/小时达标签
            # iconList 可能是 JSON 字符串或 list
            icon_list_raw = item.get("iconList", [])
            icon_list = []
            if isinstance(icon_list_raw, str):
                try:
                    icon_list = json.loads(icon_list_raw)
                except (json.JSONDecodeError, TypeError):
                    icon_list = []
            elif isinstance(icon_list_raw, list):
                icon_list = icon_list_raw

            tags = []
            is_flash = False
            for icon in icon_list:
                icon_text = ""
                if isinstance(icon, dict):
                    icon_text = icon.get("text", "") or icon.get("title", "")
                elif isinstance(icon, str):
                    icon_text = icon
                if icon_text:
                    tags.append(icon_text)
                if any(k in icon_text for k in ("闪购", "小时达", "秒送", "买菜", "鲜达")):
                    is_flash = True

            # 店铺名称: shopInfo 结构 {shopInfoList: ["天猫超市", "进店"], ...}
            shop_info = item.get("shopInfo") or {}
            shop_name = ""
            shop_url = ""
            if isinstance(shop_info, dict):
                shop_list = shop_info.get("shopInfoList", [])
                if shop_list and isinstance(shop_list, list):
                    # 过滤掉导航文本 (如 "进店")
                    candidates = [s for s in shop_list if s and s not in ("进店", "关注", "收藏")]
                    shop_name = candidates[0] if candidates else ""
                shop_url = shop_info.get("url", "")
                # 也尝试 title 字段
                if not shop_name:
                    shop_name = shop_info.get("title", "")
            # fallback: nick 字段
            if not shop_name:
                shop_name = item.get("nick", "")

            # 价格详情
            price_show = item.get("priceShow") or {}
            orig_price = ""
            if isinstance(price_show, dict):
                orig_price = price_show.get("originPrice", "")

            # 商品 ID: 优先 item_id, 其次 nid
            item_id = item.get("item_id", "") or item.get("nid", "")

            results.append({
                "item_id": str(item_id),
                "title": title,
                "price": price,
                "original_price": orig_price,
                "shop_name": shop_name,
                "shop_url": shop_url,
                "sales": item.get("realSales", ""),
                "location": item.get("procity", ""),
                "item_url": item.get("auctionURL", "") or item.get("detail_url", ""),
                "is_flash": is_flash,
                "tags": tags,
            })

        return results

    # ═══════════════════════════════════════════════════════
    # 数据转换
    # ═══════════════════════════════════════════════════════

    def _api_item_to_product(
        self, item: dict, keyword: str, screenshot_path: Optional[str]
    ) -> Optional[ProductPrice]:
        """将 API 提取的 item dict 转为 ProductPrice"""
        title = item.get("title", "")
        price = item.get("price", 0.0)
        if not title or price <= 0:
            return None

        item_id = item.get("item_id", "")
        item_url = item.get("item_url", "")
        if not item_url and item_id:
            item_url = f"https://h5.m.taobao.com/awp/core/detail.htm?id={item_id}"

        result = ProductPrice(
            platform=self.platform,
            product_id=item_id,
            product_url=item_url,
            product_name=title,
            current_price=price,
            shop_name=item.get("shop_name", ""),
            shop_url=item.get("shop_url", ""),
            ship_from_city=item.get("location", ""),
            sales_volume=str(item.get("sales", "")),
            extra={
                "keyword": keyword,
                "is_flash": item.get("is_flash", False),
                "tags": item.get("tags", []),
            },
        )

        # 解析原价
        orig = item.get("original_price", "")
        if orig:
            try:
                result.original_price = float(orig)
            except (ValueError, TypeError):
                pass

        if screenshot_path:
            result.screenshot_local = screenshot_path

        result.calculate_final_price()
        return result

    def _build_detail_result(self, data, task, product_id, screenshot_path):
        """单品模式: 从 DOM 提取结果构建 ProductPrice"""
        result = ProductPrice(
            platform=self.platform,
            product_id=product_id,
            product_url=task.product_url,
        )

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

        if screenshot_path:
            result.screenshot_local = screenshot_path
        result.calculate_final_price()
        return result if result.product_name else None

    # ═══════════════════════════════════════════════════════
    # 工具方法
    # ═══════════════════════════════════════════════════════

    @staticmethod
    def _extract_id(url: str) -> str:
        match = re.search(r"id=(\d+)", url)
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
            return CouponInfo(
                coupon_type=CouponType.FULL_REDUCTION,
                description=text,
                threshold=float(match.group(1)),
                discount_value=float(match.group(2)),
            )
        return None
