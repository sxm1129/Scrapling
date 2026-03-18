# scrapers package
from price_monitor.playwright_engine.scrapers.tmall import TmallPlaywrightScraper
from price_monitor.playwright_engine.scrapers.taobao import TaobaoPlaywrightScraper
from price_monitor.playwright_engine.scrapers.jd import JDPlaywrightScraper
from price_monitor.playwright_engine.scrapers.taobao_flash import TaobaoFlashPlaywrightScraper
from price_monitor.playwright_engine.scrapers.meituan_flash import MeituanFlashPlaywrightScraper
from price_monitor.playwright_engine.scrapers.pdd import PDDPlaywrightScraper

# 平台名 → Scraper 类 的映射
SCRAPER_REGISTRY: dict = {
    "tmall": TmallPlaywrightScraper,
    "taobao": TaobaoPlaywrightScraper,
    "jd_express": JDPlaywrightScraper,
    "taobao_flash": TaobaoFlashPlaywrightScraper,
    "meituan_flash": MeituanFlashPlaywrightScraper,
    "pinduoduo": PDDPlaywrightScraper,
}

def get_scraper(platform: str):
    """工厂函数：按平台名返回已实例化的 Playwright scraper"""
    cls = SCRAPER_REGISTRY.get(platform)
    if not cls:
        raise ValueError(f"No Playwright scraper registered for platform: {platform}")
    return cls()

__all__ = [
    "TmallPlaywrightScraper", "TaobaoPlaywrightScraper", "JDPlaywrightScraper",
    "TaobaoFlashPlaywrightScraper", "MeituanFlashPlaywrightScraper",
    "PDDPlaywrightScraper", "SCRAPER_REGISTRY", "get_scraper",
]
