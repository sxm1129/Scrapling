"""
browser.py — patchright 浏览器工厂
======================================================
封装 patchright Chromium 上下文创建，提供:
  - 真实 User-Agent
  - zh-CN locale + Asia/Shanghai TZ
  - 有头/无头自动切换（PLAYWRIGHT_HEADED=1 强制有头）
  - Geolocation 注入（O2O 平台定位需要）
"""
import logging
import os
from typing import Optional, AsyncContextManager

from patchright.async_api import async_playwright, Browser, BrowserContext, Playwright

log = logging.getLogger("price_monitor.playwright_engine.browser")

# 环境变量控制有头/无头
_HEADED = os.getenv("PLAYWRIGHT_HEADED", "0") == "1"

# 各平台默认地理位置（城市级）
_DEFAULT_GEOLOCATIONS: dict[str, dict] = {
    "meituan_flash": {"latitude": 31.2304, "longitude": 121.4737},  # 上海
    "taobao_flash":  {"latitude": 31.2304, "longitude": 121.4737},
    "pupu":          {"latitude": 22.5431, "longitude": 114.0579},  # 深圳
    "dingdong":      {"latitude": 31.2304, "longitude": 121.4737},
    "xiaoxiang":     {"latitude": 31.2304, "longitude": 121.4737},
}

# 真实 Chrome macOS UA
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


class BrowserFactory:
    """
    patchright 浏览器上下文工厂。
    通过 async context manager 使用，自动关闭浏览器资源。
    """

    def __init__(self, platform: str):
        self.platform = platform
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    async def __aenter__(self) -> BrowserContext:
        self._playwright = await async_playwright().start()
        headless = not _HEADED  # 开发时 PLAYWRIGHT_HEADED=1
        log.info(f"[{self.platform}] Launching {'headed' if not headless else 'headless'} browser (patchright)")

        self._browser = await self._playwright.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-infobars",
            ],
        )

        ctx_kwargs: dict = {
            "user_agent": _USER_AGENT,
            "viewport": {"width": 1440, "height": 900},
            "locale": "zh-CN",
            "timezone_id": "Asia/Shanghai",
            "accept_downloads": False,
        }

        # 注入地理位置（O2O 类平台）
        geo = _DEFAULT_GEOLOCATIONS.get(self.platform)
        if geo:
            ctx_kwargs["geolocation"] = geo
            ctx_kwargs["permissions"] = ["geolocation"]
            log.debug(f"[{self.platform}] Injecting geolocation: {geo}")

        self._context = await self._browser.new_context(**ctx_kwargs)

        # 禁止图片加载（加速，价格文字不依赖图片）——可选，某些平台图片是价格载体时删掉
        # await self._context.route("**/*.{png,jpg,jpeg,gif,svg,webp,ico}", lambda r: r.abort())

        log.debug(f"[{self.platform}] Browser context ready")
        return self._context

    async def __aexit__(self, *args):
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        log.debug(f"[{self.platform}] Browser closed")
