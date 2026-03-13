"""
数据模型定义
所有平台的采集结果统一到这些标准化数据结构
"""

from enum import Enum
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

import orjson


class Platform(str, Enum):
    """支持的平台枚举"""
    TAOBAO = "taobao"
    TMALL = "tmall"
    PINDUODUO = "pinduoduo"
    DOUYIN = "douyin"
    XIAOHONGSHU = "xiaohongshu"
    MEITUAN_FLASH = "meituan_flash"
    JD_EXPRESS = "jd_express"
    TAOBAO_FLASH = "taobao_flash"
    PUPU = "pupu"
    XIAOXIANG = "xiaoxiang"
    DINGDONG = "dingdong"
    COMMUNITY_GROUP = "community_group"


class CouponType(str, Enum):
    """优惠券类型"""
    STORE_COUPON = "store_coupon"           # 店铺优惠券
    PLATFORM_COUPON = "platform_coupon"     # 平台优惠券
    FULL_REDUCTION = "full_reduction"       # 满减
    DIRECT_DISCOUNT = "direct_discount"     # 直降/折扣
    TIME_LIMITED = "time_limited"           # 限时折扣
    MEMBER_PRICE = "member_price"           # 会员价
    NEW_USER = "new_user"                   # 新人价
    FLASH_SALE = "flash_sale"              # 秒杀价
    GROUP_BUY = "group_buy"                # 拼团价
    LIVE_EXCLUSIVE = "live_exclusive"       # 直播间专属
    OTHER = "other"


@dataclass
class CouponInfo:
    """优惠券信息"""
    coupon_type: CouponType
    description: str = ""           # 原始描述 (如 "满200减30")
    threshold: float = 0.0          # 满减门槛
    discount_value: float = 0.0     # 优惠金额 / 折扣率
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    is_claimable: bool = True       # 是否可领取


@dataclass
class ProductPrice:
    """商品价格信息 — 核心数据模型"""
    # === 基础信息 ===
    platform: Platform
    product_id: str                  # 平台商品 ID
    product_url: str                 # 商品链接
    product_name: str = ""           # 商品名称

    # === 价格信息 ===
    original_price: float = 0.0      # 原价 / 划线价
    current_price: float = 0.0       # 当前售价 (未使用优惠券)
    final_price: float = 0.0         # 实际折后价 (使用所有可用优惠后)
    currency: str = "CNY"

    # === 优惠券信息 ===
    coupons: list[CouponInfo] = field(default_factory=list)

    # === 店铺信息 ===
    shop_name: str = ""              # 店铺名称
    shop_url: str = ""               # 店铺链接
    seller_id: str = ""              # 卖家 ID
    dealer_name: str = ""            # 关联经销商名称

    # === 物流信息 ===
    ship_from_city: str = ""         # 发货城市
    ship_from_province: str = ""     # 发货省份
    warehouse_name: str = ""         # 仓库名称 (前置仓场景)

    # === 截图 ===
    screenshot_url: str = ""         # 价格截图 OSS 链接
    screenshot_local: str = ""       # 本地截图路径

    # === 元数据 ===
    scraped_at: str = field(default_factory=lambda: datetime.now().isoformat())
    sku_id: str = ""                 # SKU
    category: str = ""               # 商品品类
    brand: str = ""                  # 品牌
    sales_volume: str = ""           # 销量
    extra: dict = field(default_factory=dict)  # 平台特有附加数据

    def to_dict(self) -> dict:
        """转为字典 (枚举转字符串)"""
        d = asdict(self)
        d["platform"] = self.platform.value
        d["coupons"] = [
            {**asdict(c), "coupon_type": c.coupon_type.value}
            for c in self.coupons
        ]
        return d

    def to_json(self) -> bytes:
        """序列化为 JSON bytes (使用 orjson 高性能序列化)"""
        return orjson.dumps(self.to_dict(), option=orjson.OPT_INDENT_2)

    def calculate_final_price(self) -> float:
        """计算应用所有可用优惠券后的最终价格"""
        price = self.current_price

        for coupon in self.coupons:
            if not coupon.is_claimable:
                continue

            if coupon.coupon_type in (CouponType.STORE_COUPON, CouponType.PLATFORM_COUPON,
                                      CouponType.FULL_REDUCTION):
                # 满减类: 满足门槛才减
                if price >= coupon.threshold:
                    price -= coupon.discount_value
            elif coupon.coupon_type in (CouponType.DIRECT_DISCOUNT, CouponType.TIME_LIMITED,
                                        CouponType.FLASH_SALE, CouponType.GROUP_BUY):
                # 折扣类: discount_value 是折后价或折扣率
                if 0 < coupon.discount_value < 1:
                    price *= coupon.discount_value
                elif coupon.discount_value > 0:
                    price -= coupon.discount_value

        self.final_price = max(price, 0)
        return self.final_price


@dataclass
class ScrapeTask:
    """采集任务定义"""
    task_id: str
    platform: Platform
    product_url: str
    product_id: str = ""
    keyword: str = ""                # 搜索关键词 (搜索模式)
    city: str = ""                   # 定位城市 (O2O/前置仓)
    latitude: float = 0.0
    longitude: float = 0.0
    priority: int = 0
    cron: str = "0 */6 * * *"        # 执行频率 (默认每6小时)
    enabled: bool = True

    def to_dict(self) -> dict:
        d = asdict(self)
        d["platform"] = self.platform.value
        return d
