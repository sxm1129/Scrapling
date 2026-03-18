"""
playwright_engine — 全手动行为仿真采集引擎
============================================

独立于现有 StealthyFetcher 体系的备选采集方案。
基于 patchright (深度 patch 的 Chromium) + 贝塞尔鼠标/人类键盘 仿真。

使用方式:
    from price_monitor.playwright_engine import PlaywrightFallbackEngine
    engine = PlaywrightFallbackEngine()
    result = await engine.scrape(platform="taobao", keyword="xxx")
"""
from price_monitor.playwright_engine.fallback import PlaywrightFallbackEngine
from price_monitor.playwright_engine.base_scraper import BasePlaywrightScraper, ProductDetail

__all__ = ["PlaywrightFallbackEngine", "BasePlaywrightScraper", "ProductDetail"]
