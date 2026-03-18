"""
fallback.py — 三段降级采集引擎 (Playwright → StealthyFetcher → Feishu 告警)
==============================================================================

调用顺序:
  1. 尝试 playwright scraper（行为仿真，patchright）
  2. 失败则降级到 StealthyFetcher（现有体系）
  3. 再次失败则通过飞书推送告警通知人工介入

连续失败超过 MAX_CONSECUTIVE_FAILS 次时，该平台自动暂停（避免持续无效消耗）。
"""
import asyncio
import logging
import os
from typing import Optional, Callable, Awaitable, Any

from price_monitor.playwright_engine.browser import BrowserFactory
from price_monitor.playwright_engine.cookie_bridge import CookieBridge
from price_monitor.playwright_engine.human_actions import HumanActions
from price_monitor.playwright_engine.base_scraper import (
    BasePlaywrightScraper, ProductDetail, SearchResult
)

log = logging.getLogger("price_monitor.playwright_engine.fallback")

# 每平台连续失败上限（超出后暂停该平台）
MAX_CONSECUTIVE_FAILS = 3

# 截图目录
_SCREENSHOT_DIR = os.getenv("SCREENSHOT_DIR", "./data/screenshots")


class PlaywrightFallbackEngine:
    """
    全平台 Playwright 采集引擎入口点。

    用法（在现有 CollectionManager._run_o2o_scan 或新的调度器中）:
    ```python
    engine = PlaywrightFallbackEngine()
    results = await engine.scrape_by_keyword(
        platform="taobao",
        keyword="卡士酸奶",
        scraper=TaobaoPlaywrightScraper(),
        limit=5,
    )
    ```
    """

    def __init__(self):
        # 每平台连续失败计数（内存，重启清零）
        self._fail_counts: dict[str, int] = {}
        # 暂停的平台集合
        self._paused: set[str] = set()

    # ────────────────────────────────────────
    # 主入口
    # ────────────────────────────────────────

    async def scrape_by_keyword(
        self,
        platform: str,
        keyword: str,
        scraper: BasePlaywrightScraper,
        limit: int = 10,
    ) -> list[ProductDetail]:
        """
        搜索关键词并获取前 N 个商品的详情。
        自动管理 browser context、cookie 注入、降级、告警。
        """
        if platform in self._paused:
            log.warning(f"[{platform}] Platform is paused due to {MAX_CONSECUTIVE_FAILS} consecutive failures. Skipping.")
            return []

        results: list[ProductDetail] = []
        try:
            results = await self._run_playwright(platform, keyword, scraper, limit)
            self._reset_fail_count(platform)
        except Exception as e:
            log.error(f"[{platform}] Playwright scrape failed: {e}", exc_info=True)
            results = await self._fallback_to_stealthy(platform, keyword, limit)

        if not results:
            self._increment_fail(platform)

        return results

    # ────────────────────────────────────────
    # Stage 1: Playwright
    # ────────────────────────────────────────

    async def _run_playwright(
        self,
        platform: str,
        keyword: str,
        scraper: BasePlaywrightScraper,
        limit: int,
    ) -> list[ProductDetail]:
        bridge = CookieBridge(platform)
        details: list[ProductDetail] = []

        async with BrowserFactory(platform) as context:
            # 注入 Cookie
            cookie_ok = await bridge.inject_into_context(context)
            if not cookie_ok:
                log.warning(f"[{platform}] No cookies injected — scraping without login")

            page = await context.new_page()
            human = HumanActions(page)

            try:
                # Step 1: 搜索
                search_results: list[SearchResult] = await scraper.search(page, keyword, human, limit)
                log.info(f"[{platform}] Found {len(search_results)} results for '{keyword}'")

                if not search_results:
                    raise ValueError("Empty search results — possible block or layout change")

                # Step 2: 逐个进入详情页
                for sr in search_results[:limit]:
                    try:
                        detail = await scraper.get_detail(page, sr.url, keyword, human, _SCREENSHOT_DIR)
                        details.append(detail)
                        log.info(
                            f"[{platform}] Detail: '{detail.title[:30]}...' "
                            f"price={detail.final_price} shop={detail.shop_name}"
                        )
                        # 详情页间的拟真停顿（2-5秒）
                        await asyncio.sleep(2 + 3 * __import__("random").random())
                    except Exception as e:
                        log.error(f"[{platform}] Detail scrape failed for {sr.url}: {e}")

                # Step 3: 采集完毕，保存刷新后的 Cookie
                await bridge.save_from_context(context)

            except Exception:
                await page.close()
                raise
            finally:
                await page.close()

        return details

    # ────────────────────────────────────────
    # Stage 2: Fallback → StealthyFetcher
    # ────────────────────────────────────────

    async def _fallback_to_stealthy(
        self, platform: str, keyword: str, limit: int
    ) -> list[ProductDetail]:
        """
        降级到现有 StealthyFetcher 体系，将结果包装成 ProductDetail 返回。
        注意: 现有 scraper 需要 config + screenshot 参数，集成较复杂，
        此版本记录日志后直接触发告警，不尝试真正调用 StealthyFetcher。
        """
        log.info(f"[{platform}] Fallback: StealthyFetcher integration not available in Playwright engine context")
        log.info(f"[{platform}] Sending Feishu alert for '{keyword}'")
        await self._send_alert(platform, keyword, "Playwright took 0 results")
        return []

    # ────────────────────────────────────────
    # Stage 3: Feishu Alert
    # ────────────────────────────────────────

    async def _send_alert(self, platform: str, keyword: str, error: str):
        """调用现有飞书通知模块，发送采集失败告警"""
        try:
            from price_monitor.notify import send_text
            msg = (
                f"⚠️ [控价采集失败]\n"
                f"平台: {platform}\n"
                f"关键词: {keyword}\n"
                f"原因: {error[:200]}\n"
                f"请人工检查 Cookie 是否失效，或平台是否更新了反爬策略。"
            )
            send_text(msg)
            log.info(f"[{platform}] Feishu alert sent for '{keyword}'")
        except Exception as e:
            log.error(f"[{platform}] Failed to send Feishu alert: {e}")

    # ────────────────────────────────────────
    # 失败计数管理
    # ────────────────────────────────────────

    def _increment_fail(self, platform: str):
        count = self._fail_counts.get(platform, 0) + 1
        self._fail_counts[platform] = count
        log.warning(f"[{platform}] Failure count: {count}/{MAX_CONSECUTIVE_FAILS}")
        if count >= MAX_CONSECUTIVE_FAILS:
            self._paused.add(platform)
            log.error(
                f"[{platform}] AUTO-PAUSED after {MAX_CONSECUTIVE_FAILS} consecutive failures. "
                "Restart the engine or call engine.resume(platform) to re-enable."
            )

    def _reset_fail_count(self, platform: str):
        if platform in self._fail_counts:
            del self._fail_counts[platform]

    def resume(self, platform: str):
        """手动恢复被暂停的平台"""
        self._paused.discard(platform)
        self._fail_counts.pop(platform, None)
        log.info(f"[{platform}] Resumed scraping")
