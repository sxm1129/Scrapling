"""
美团闪购采集器
策略: Tier-1 HTTP API (Scrapling Fetcher + TLS 伪装)

美团闪购的 H5 页面有相对开放的 API 接口,
通过移动端 H5 页面分析可以获取商品详情和价格信息。
"""

import re
import logging
from typing import Optional

from scrapling.fetchers import Fetcher

from price_monitor.models import (
    ProductPrice, ScrapeTask, Platform,
    CouponInfo, CouponType,
)
from price_monitor.scrapers import BaseScraper

log = logging.getLogger("price_monitor.scrapers.meituan")


class MeituanFlashScraper(BaseScraper):
    """美团闪购采集器

    数据来源:
    - H5 商品详情页: https://h5.waimai.meituan.com/waimai/mindex/product/...
    - 搜索 API: 通过 Fetcher 发送带签名的请求

    反爬特点:
    - 中等防护等级
    - 需要经纬度定位参数
    - UA 检测 + 频率限制
    """

    platform = Platform.MEITUAN_FLASH

    # 默认定位 (可通过 task.latitude/longitude 覆盖)
    DEFAULT_LAT = 30.5728  # 上海
    DEFAULT_LNG = 104.0668

    async def scrape_product(self, task: ScrapeTask) -> Optional[ProductPrice]:
        """Tier-1: 通过 HTTP 请求抓取美团闪购商品页面"""

        try:
            # 使用 Scrapling Fetcher 发送请求 (TLS 伪装为 Chrome)
            page = Fetcher.get(
                task.product_url,
                impersonate="chrome",
                stealthy_headers=True,
                timeout=15,
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.9",
                },
            )

            if page.status != 200:
                log.warning(f"Meituan returned status {page.status}")
                return None

            return self._parse_product_page(page, task)

        except Exception as e:
            log.error(f"Meituan scrape failed: {e}")
            return None

    def _parse_product_page(self, page, task: ScrapeTask) -> Optional[ProductPrice]:
        """解析美团闪购商品页面 (使用 Scrapling Selector)"""

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

        # 发货/配送信息
        location_el = page.css('.location, .delivery-info, [class*="address"]')
        if location_el:
            result.ship_from_city = location_el.css("::text").get("").strip()

        # 优惠券 (美团闪购常有满减活动)
        coupon_els = page.css('.coupon, .discount, .promotion, [class*="coupon"]')
        for el in coupon_els:
            text = el.css("::text").get("").strip()
            if text:
                coupon = self._parse_coupon_text(text)
                if coupon:
                    result.coupons.append(coupon)

        # 计算最终价格
        result.calculate_final_price()

        return result if result.product_name else None

    @staticmethod
    def _extract_product_id(url: str) -> str:
        """从 URL 提取商品 ID"""
        # 美团商品 URL 格式多样, 尝试多种模式
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
        """从文本中提取价格数值"""
        if not text:
            return 0.0
        match = re.search(r"[\d]+\.?\d*", text.replace(",", ""))
        return float(match.group()) if match else 0.0

    @staticmethod
    def _parse_coupon_text(text: str) -> Optional[CouponInfo]:
        """解析优惠券描述文本"""
        text = text.strip()
        if not text:
            return None

        # "满100减20" 格式
        match = re.search(r"满(\d+)减(\d+)", text)
        if match:
            return CouponInfo(
                coupon_type=CouponType.FULL_REDUCTION,
                description=text,
                threshold=float(match.group(1)),
                discount_value=float(match.group(2)),
            )

        # "减5元" 格式
        match = re.search(r"减(\d+)", text)
        if match:
            return CouponInfo(
                coupon_type=CouponType.DIRECT_DISCOUNT,
                description=text,
                discount_value=float(match.group(1)),
            )

        # "8折" / "85折" 格式
        match = re.search(r"(\d+\.?\d*)折", text)
        if match:
            discount = float(match.group(1))
            return CouponInfo(
                coupon_type=CouponType.DIRECT_DISCOUNT,
                description=text,
                discount_value=discount / 10,  # 8折 -> 0.8
            )

        return CouponInfo(
            coupon_type=CouponType.OTHER,
            description=text,
        )
