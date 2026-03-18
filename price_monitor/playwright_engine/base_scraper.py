"""
base_scraper.py — 所有平台 Playwright scraper 的抽象父类
==========================================================
定义统一的 ProductDetail 数据模型 和 BasePlaywrightScraper 接口。

所有平台 scraper (taobao.py / jd.py / pdd.py ...) 必须继承此类。
"""
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

log = logging.getLogger("price_monitor.playwright_engine.base_scraper")


@dataclass
class CouponDetail:
    """单张优惠券信息"""
    coupon_type: str               # DISCOUNT / CASH / PLATFORM / SHOP
    threshold: Optional[Decimal]   # 满 X 可用，None=无门槛
    discount: Decimal              # 减 Y 元 / 打折值
    expiry_str: Optional[str] = None  # 到期时间文字描述
    raw_text: Optional[str] = None    # 原始文本，用于证据链存储


@dataclass
class ProductDetail:
    """
    Playwright 采集到的商品详情完整数据模型。
    与现有 ProductPrice 并存（用于 fallback 转换）。
    """
    platform: str
    keyword: str                      # 触发此采集的搜索词
    url: str                          # 商品详情页 URL
    title: str = ""                   # 商品标题
    sku: str = ""                     # 选中规格描述
    display_price: Optional[Decimal] = None    # 页面展示价
    final_price: Optional[Decimal] = None      # 到手价（含优惠券折算）
    original_price: Optional[Decimal] = None   # 划线原价
    coupons: list[CouponDetail] = field(default_factory=list)
    promotions: list[str] = field(default_factory=list)  # 促销活动文字
    shop_name: str = ""
    shop_url: str = ""
    ship_from_city: str = ""
    screenshot_path: Optional[str] = None   # 截图存储相对路径
    is_login_required_for_price: bool = False
    error: Optional[str] = None             # 如果采集失败

    def to_product_price_dict(self) -> dict:
        """
        转换为系统内置 ProductPrice 兼容格式，
        便于 Fallback 链传入 process_offers()。
        """
        return {
            "platform": self.platform,
            "keyword": self.keyword,
            "url": self.url,
            "product_name": self.title,
            "price": float(self.final_price or self.display_price or 0),
            "original_price": float(self.original_price) if self.original_price else None,
            "shop_name": self.shop_name,
            "ship_from_city": self.ship_from_city,
            "screenshot_path": self.screenshot_path,
            "coupons": [
                {
                    "type": c.coupon_type,
                    "threshold": float(c.threshold) if c.threshold else None,
                    "discount": float(c.discount),
                    "raw_text": c.raw_text,
                }
                for c in self.coupons
            ],
        }


@dataclass
class SearchResult:
    """搜索结果列表中的单条商品"""
    title: str
    url: str
    display_price: Optional[Decimal] = None
    shop_name: str = ""
    thumbnail_url: str = ""


class BasePlaywrightScraper(ABC):
    """
    Playwright 平台采集器抽象基类。
    子类必须实现 search() 和 get_detail()。
    browser context 和 human_actions 由 fallback.py 注入。
    """

    #: 子类必须声明平台标识符（与 Platform enum 一致）
    platform: str = ""

    #: 搜索结果容器 CSS 选择器（子类可覆盖用于健康检查）
    search_result_selector: str = ""

    #: 登录态检测关键字（落到登录页时 URL 通常含以下字符串）
    login_page_indicators: list[str] = ["login", "sign", "passport", "account"]

    def is_login_page(self, url: str) -> bool:
        """检测当前是否被重定向至登录页"""
        return any(indicator in url.lower() for indicator in self.login_page_indicators)

    @abstractmethod
    async def search(
        self,
        page,             # patchright Page
        keyword: str,
        human,            # HumanActions 实例
        limit: int = 10,
    ) -> list[SearchResult]:
        """
        在平台搜索关键词，返回前 N 个商品的列表摘要。
        page 和 human 由 fallback.py 提供。
        """
        ...

    @abstractmethod
    async def get_detail(
        self,
        page,            # patchright Page
        url: str,
        keyword: str,
        human,           # HumanActions 实例
        screenshot_dir: str = "./data/screenshots",
    ) -> ProductDetail:
        """
        访问商品详情页，提取完整价格+优惠信息+截图。
        """
        ...

    async def extract_coupons(self, page) -> list[CouponDetail]:
        """
        通用优惠券提取逻辑——子类可 override 以实现平台特定逻辑。
        默认实现尝试从常见 coupon 容器中提取文字。
        """
        coupons = []
        try:
            coupon_els = await page.query_selector_all(
                "[class*='coupon'], [class*='Coupon'], [class*='discount'], [class*='voucher']"
            )
            for el in coupon_els[:5]:
                text = (await el.inner_text()).strip()
                if text and len(text) > 2:
                    coupons.append(CouponDetail(
                        coupon_type="UNKNOWN",
                        threshold=None,
                        discount=Decimal("0"),
                        raw_text=text,
                    ))
        except Exception as e:
            log.debug(f"[{self.platform}] extract_coupons failed (non-critical): {e}")
        return coupons

    async def take_screenshot(self, page, dir: str, prefix: str) -> Optional[str]:
        """拍摄全页截图，返回相对路径"""
        import os
        import time
        os.makedirs(dir, exist_ok=True)
        filename = f"{prefix}_{self.platform}_{int(time.time())}.png"
        path = os.path.join(dir, filename)
        try:
            await page.screenshot(path=path, full_page=True)
            log.info(f"[{self.platform}] Screenshot saved: {path}")
            return path
        except Exception as e:
            log.warning(f"[{self.platform}] Screenshot failed: {e}")
            return None
