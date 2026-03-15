"""
平台采集器基类 — 定义统一接口
每个平台实现自己的 scrape_product 方法
"""

import logging
import asyncio
from abc import ABC, abstractmethod
from typing import Optional

from price_monitor.models import ProductPrice, ScrapeTask, Platform
from price_monitor.config import Config, PlatformConfig
from price_monitor.screenshot import PriceScreenshot
from price_monitor.account_pool import AccountPool

log = logging.getLogger("price_monitor.scraper")


class BaseScraper(ABC):
    """所有平台采集器的基类"""

    platform: Platform  # 子类必须设置

    def __init__(
        self,
        config: Config,
        screenshot: PriceScreenshot,
        account_pool: Optional[AccountPool] = None,
    ):
        self.config = config
        self.screenshot = screenshot
        self.account_pool = account_pool
        self._platform_config: PlatformConfig = config.platforms.get(
            self.platform.value,
            PlatformConfig()
        )

    @property
    def delay(self) -> float:
        """当前平台的请求间隔"""
        return self._platform_config.delay

    @property
    def strategy(self) -> str:
        """采集策略: http_api / browser / app_protocol"""
        return self._platform_config.strategy

    @abstractmethod
    async def scrape_product(self, task: ScrapeTask) -> Optional[ProductPrice]:
        """采集单个商品的价格信息

        :param task: 采集任务
        :return: ProductPrice 数据, 失败返回 None
        """
        raise NotImplementedError



    def _get_cookies(self) -> Optional[dict]:
        """从账号池获取 Cookie"""
        if self.account_pool:
            account = self.account_pool.get_cookie(self.platform.value)
            if account:
                return account["cookies"]
        return None

    def _get_account(self) -> Optional[dict]:
        """从账号池获取完整账号信息 (含 UA)"""
        if self.account_pool:
            return self.account_pool.get_cookie(self.platform.value)
        return None
