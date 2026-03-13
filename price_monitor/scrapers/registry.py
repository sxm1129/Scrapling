"""
采集器注册表 / 工厂
提供 create_scraper() 函数, 根据平台枚举创建对应的采集器实例
"""

import logging
from typing import Optional

from price_monitor.models import Platform
from price_monitor.config import Config
from price_monitor.pipeline import DataPipeline
from price_monitor.screenshot import PriceScreenshot
from price_monitor.account_pool import AccountPool
from price_monitor.scrapers import BaseScraper

log = logging.getLogger("price_monitor.scrapers.registry")


def create_scraper(
    platform: Platform,
    config: Config,
    pipeline: DataPipeline,
    screenshot: PriceScreenshot,
    account_pool: Optional[AccountPool] = None,
) -> BaseScraper:
    """根据平台创建对应的采集器实例

    :param platform: 目标平台
    :param config: 全局配置
    :param pipeline: 数据管道
    :param screenshot: 截图引擎
    :param account_pool: Cookie/账号池 (可选)
    :return: BaseScraper 实例
    :raises ValueError: 不支持的平台
    """
    scraper_cls = _REGISTRY.get(platform)
    if not scraper_cls:
        raise ValueError(f"Unsupported platform: {platform.value}")

    return scraper_cls(
        config=config, pipeline=pipeline,
        screenshot=screenshot, account_pool=account_pool,
    )


def list_supported_platforms() -> list[str]:
    """返回所有已注册的平台名称列表"""
    return [p.value for p in _REGISTRY.keys()]


def _build_registry() -> dict[Platform, type[BaseScraper]]:
    """延迟导入各平台采集器, 构建注册表"""
    registry: dict[Platform, type[BaseScraper]] = {}

    # JD 京东秒送
    try:
        from price_monitor.scrapers.jd_express import JDExpressScraper
        registry[Platform.JD_EXPRESS] = JDExpressScraper
    except ImportError as e:
        log.warning(f"JD Express scraper not available: {e}")

    # 美团闪购
    try:
        from price_monitor.scrapers.meituan_flash import MeituanFlashScraper
        registry[Platform.MEITUAN_FLASH] = MeituanFlashScraper
    except ImportError as e:
        log.warning(f"Meituan Flash scraper not available: {e}")

    # 淘宝
    try:
        from price_monitor.scrapers.taobao import TaobaoScraper
        registry[Platform.TAOBAO] = TaobaoScraper
    except ImportError as e:
        log.warning(f"Taobao scraper not available: {e}")

    # 天猫
    try:
        from price_monitor.scrapers.taobao import TmallScraper
        registry[Platform.TMALL] = TmallScraper
    except ImportError as e:
        log.warning(f"Tmall scraper not available: {e}")

    # 抖音
    try:
        from price_monitor.scrapers.douyin import DouyinScraper
        registry[Platform.DOUYIN] = DouyinScraper
    except ImportError as e:
        log.warning(f"Douyin scraper not available: {e}")

    # 小红书
    try:
        from price_monitor.scrapers.xiaohongshu import XiaohongshuScraper
        registry[Platform.XIAOHONGSHU] = XiaohongshuScraper
    except ImportError as e:
        log.warning(f"Xiaohongshu scraper not available: {e}")

    # 拼多多
    try:
        from price_monitor.scrapers.pinduoduo import PinduoduoScraper
        registry[Platform.PINDUODUO] = PinduoduoScraper
    except ImportError as e:
        log.warning(f"Pinduoduo scraper not available: {e}")

    # 淘宝闪购
    try:
        from price_monitor.scrapers.taobao_flash import TaobaoFlashScraper
        registry[Platform.TAOBAO_FLASH] = TaobaoFlashScraper
    except ImportError as e:
        log.warning(f"Taobao Flash scraper not available: {e}")

    # 前置仓 — 朴朴
    try:
        from price_monitor.scrapers.warehouse import PupuScraper
        registry[Platform.PUPU] = PupuScraper
    except ImportError as e:
        log.warning(f"PuPu scraper not available: {e}")

    # 前置仓 — 小象
    try:
        from price_monitor.scrapers.warehouse import XiaoxiangScraper
        registry[Platform.XIAOXIANG] = XiaoxiangScraper
    except ImportError as e:
        log.warning(f"Xiaoxiang scraper not available: {e}")

    # 前置仓 — 叮咚
    try:
        from price_monitor.scrapers.warehouse import DingdongScraper
        registry[Platform.DINGDONG] = DingdongScraper
    except ImportError as e:
        log.warning(f"Dingdong scraper not available: {e}")

    # 社区团购
    try:
        from price_monitor.scrapers.community_group import CommunityGroupScraper
        registry[Platform.COMMUNITY_GROUP] = CommunityGroupScraper
    except ImportError as e:
        log.warning(f"Community Group scraper not available: {e}")

    return registry


_REGISTRY = _build_registry()
