"""
美团闪购采集器
策略: Tier-1 HTTP API (Scrapling Fetcher + Playwright Interception)

美团闪购的 H5 页面极其严格, 需要经纬度定位, 并且搜索时必须具有有效的登录 Cookie。
此爬虫使用 Playwright 的网络拦截功能, 抓取含有详细价格的 globalpage API。
"""

import re
import json
import logging
import asyncio
from typing import Optional, List

from scrapling.fetchers import StealthyFetcher

from price_monitor.models import (
    ProductPrice, ScrapeTask, Platform,
    CouponInfo, CouponType,
)
from price_monitor.scrapers import BaseScraper
from price_monitor.account_pool import AccountPool

log = logging.getLogger("price_monitor.scrapers.meituan")


class MeituanFlashScraper(BaseScraper):
    platform = Platform.MEITUAN_FLASH

    # 默认定位 (可通过 task.latitude/longitude 覆盖)
    DEFAULT_LAT = 30.5728  # 上海
    DEFAULT_LNG = 104.0668

    async def scrape_search(self, task: ScrapeTask) -> List[ProductPrice]:
        """Tier-1: 通过 Playwright 网络拦截美团闪购搜索页面 API"""
        results = []
        try:
            log.info(f"[{self.platform.value}] Starting search for: {task.keyword}")
            url = f"https://h5.waimai.meituan.com/waimai/mindex/search"
            # Fetch cookies from AccountPool
            pool = AccountPool()
            cookies = pool.get_playwright_cookies("meituan_flash") or []
            if cookies:
                log.info(f"[{self.platform.value}] Injected {len(cookies)} cookies from AccountPool")
            else:
                log.warning(f"[{self.platform.value}] No Meituan cookies found. Search will likely fail or redirect.")

            async def page_action(page):
                # Trigger search
                log.info(f"[{self.platform.value}] Waiting for search input box...")
                try:
                    await page.wait_for_selector('input', timeout=10000)
                    await page.fill('input', task.keyword)
                    await page.keyboard.press('Enter')
                    log.info(f"[{self.platform.value}] Typed keyword and pressed Enter")
                except Exception as e:
                    log.warning(f"[{self.platform.value}] Could not type into input (might be a redirect to login): {e}")

                # Wait for potential results
                await page.wait_for_timeout(5000)

            # Use intercept_url_pattern to capture the globalpage JSON
            fetch_params = {
                "headless": True,
                "network_idle": True,
                "timeout": 30000,
                "page_action": page_action,
                "cookies": cookies,
                "intercept_url_pattern": "globalpage",
                "google_search": False
            }

            page = await StealthyFetcher.async_fetch(url, **fetch_params)
            
            # Extract JSON from response metadata
            if page and hasattr(page, 'response_data') and page.response_data:
                for req_url, res_data in page.response_data.items():
                    if "globalpage" in req_url and res_data.get("json"):
                        api_json = res_data["json"]
                        results.extend(self._parse_globalpage_json(api_json, task))
                        break # Successfully parsed one

            if not results:
                log.warning(f"[{self.platform.value}] No results extracted. Possibly redirected or API empty.")
                
            return results

        except Exception as e:
            log.error(f"[{self.platform.value}] Meituan search failed: {e}")
            return results

    def _parse_globalpage_json(self, api_json: dict, task: ScrapeTask) -> List[ProductPrice]:
        """解析美团闪购搜索结果(Globalpage API)的 JSON"""
        results = []
        try:
            data = api_json.get("data", {})
            module_list = data.get("module_list", [])
            
            for module in module_list:
                if module.get("module_id") == "poi_mode":
                    string_data_str = module.get("string_data", "{}")
                    try:
                        string_data = json.loads(string_data_str)
                    except Exception:
                        continue
                        
                    shop_name = string_data.get("name", "")
                    
                    product_list = string_data.get("product_list", [])
                    for prod in product_list:
                        product_name = prod.get("product_name", "")
                        
                        # Apply keyword filter since globalpage returns mixed items
                        if task.keyword and task.keyword.lower() not in product_name.lower():
                            # Soft matching for "卡士" and "酸奶"
                            if not all(term in product_name for term in ["卡士"]):
                                continue

                        spu_id = prod.get("product_spu_id", "")
                        sku_id = prod.get("product_sku_id", "")
                        
                        price = prod.get("price", 0.0)
                        original_price = prod.get("original_price", 0.0)
                        
                        result = ProductPrice(
                            platform=self.platform,
                            product_id=str(spu_id),
                            product_name=product_name,
                            product_url=f"https://h5.waimai.meituan.com/waimai/mindex/menu?poi_id={string_data.get('poi_id_str', '')}&spu_id={spu_id}",
                            current_price=float(price),
                            original_price=float(original_price) if float(original_price) > 0 else float(price),
                            shop_name=shop_name,
                        )
                        
                        # Add coupon logic (Meituan API sometimes includes "activity_tag")
                        act_info = prod.get("activity_info", {})
                        if act_info:
                            act_tag = act_info.get("activity_tag")
                            if act_tag and "折" in act_tag:
                                try:
                                    discount_match = re.search(r'([\d\.]+)折', act_tag)
                                    if discount_match:
                                        discount = float(discount_match.group(1))
                                        result.coupons.append(
                                            CouponInfo(
                                                coupon_type=CouponType.DIRECT_DISCOUNT,
                                                description=act_tag,
                                                discount_value=discount / 10
                                            )
                                        )
                                except Exception:
                                    pass

                        result.calculate_final_price()
                        results.append(result)

        except Exception as e:
            log.error(f"[{self.platform.value}] Failed parsing globalpage json: {e}")
            
        return results

    async def scrape_product(self, task: ScrapeTask) -> Optional[ProductPrice]:
        """Tier-1: 通过网络拦截抓取美团闪购商品页面
        目前大部分需求通过 scrape_search 即可满足, 此处为了兼容直接进入商品页的情况也使用 Fetcher
        """
        try:
            # Note: A real product page might be meituanwaimai:// scheme or h5
            page = await asyncio.to_thread(
                StealthyFetcher.get,
                task.product_url,
                impersonate="chrome",
                stealthy_headers=True,
                timeout=15,
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml",
                    "Accept-Language": "zh-CN,zh;q=0.9",
                },
            )

            if page.status != 200:
                log.warning(f"[{self.platform.value}] Meituan returned status {page.status}")
                return None

            return self._parse_product_page(page, task)

        except Exception as e:
            log.error(f"[{self.platform.value}] Meituan scrape failed: {e}")
            return None

    def _parse_product_page(self, page, task: ScrapeTask) -> Optional[ProductPrice]:
        """解析美团闪购商品页面 (旧 DOM 逻辑作为 fallback)"""

        result = ProductPrice(
            platform=self.platform,
            product_id=task.product_id or self._extract_product_id(task.product_url),
            product_url=task.product_url,
        )

        # 商品名称
        name_el = page.css('h1, .product-name, .goods-name, [class*="title"]')
        if name_el:
            result.product_name = name_el.css("::text").get("").strip()

        # 当前价格
        price_el = page.css('.price, .current-price, [class*="price"]')
        if price_el:
            price_text = price_el.css("::text").get("")
            result.current_price = self._parse_price(price_text)

        # 原价
        origin_el = page.css('.origin-price, .original-price, [class*="origin"]')
        if origin_el:
            origin_text = origin_el.css("::text").get("")
            result.original_price = self._parse_price(origin_text)

        # 店铺名称
        shop_el = page.css('.shop-name, .store-name, [class*="shop"]')
        if shop_el:
            result.shop_name = shop_el.css("::text").get("").strip()

        result.calculate_final_price()
        return result if result.product_name else None

    @staticmethod
    def _extract_product_id(url: str) -> str:
        patterns = [
            r"product/(\d+)",
            r"goods[_-]?id=(\d+)",
            r"/item/(\d+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return url.split("/")[-1].split("?")[0]

    @staticmethod
    def _parse_price(text: str) -> float:
        if not text:
            return 0.0
        match = re.search(r"[\d]+\.?\d*", text.replace(",", ""))
        return float(match.group()) if match else 0.0

