"""
cookie_bridge.py — Cookie 双向桥梁
====================================
链接 Playwright 上下文 ↔ 现有 CookieAccount DB (cookie_keeper.py)

职责:
  - 从 DB 读取指定平台的有效 Cookie 列表
  - 将 Cookie 注入到 Playwright browser context
  - 将 Playwright 内捕获到的新 Cookie 写回 DB
  - Cookie 失效时标记账号
"""
import logging
from typing import Optional

from patchright.async_api import BrowserContext

from price_monitor.db.session import get_session_factory
from price_monitor.db import crud

log = logging.getLogger("price_monitor.playwright_engine.cookie_bridge")


class CookieBridge:
    """
    Cookie 桥接器，负责:
      1. 从数据库加载最新有效 Cookie
      2. 将 Cookie 注入 Playwright context
      3. 采集完成后将新 Cookie 写回 DB

    使用方法:
        bridge = CookieBridge("taobao")
        await bridge.inject_into_context(context)
        # ... do scraping ...
        await bridge.save_from_context(context)
    """

    def __init__(self, platform: str):
        self.platform = platform
        self._account_id: Optional[str] = None

    # ────────────────────────────────────────────
    # 1. 从 DB 读取 Cookie
    # ────────────────────────────────────────────

    def _load_raw_cookies(self) -> Optional[tuple[str, list[dict]]]:
        """
        返回 (account_id, cookies_list) 或 None（无可用 Cookie）
        """
        factory = get_session_factory()
        with factory() as session:
            account = crud.get_platform_cookies(session, self.platform)
            if not account:
                log.warning(f"[{self.platform}] No active cookie account found in DB")
                return None
            if not account.cookies or not isinstance(account.cookies, list):
                log.warning(f"[{self.platform}] Cookie account #{account.id} has empty/invalid cookies")
                return None
            log.info(f"[{self.platform}] Loaded {len(account.cookies)} cookies from account '{account.account_id}'")
            return account.account_id, list(account.cookies)

    # ────────────────────────────────────────────
    # 2. 注入 Cookie 到 Playwright Context
    # ────────────────────────────────────────────

    async def inject_into_context(self, context: BrowserContext) -> bool:
        """
        将 DB 中的 Cookie 注入到浏览器 context。
        返回 True 表示成功注入，False 表示无可用 Cookie。
        """
        result = self._load_raw_cookies()
        if not result:
            return False

        account_id, raw_cookies = result
        self._account_id = account_id

        # 转换为 Playwright 格式（确保有 domain、path、name、value）
        playwright_cookies = []
        for c in raw_cookies:
            if not c.get("name") or not c.get("value"):
                continue
            pc = {
                "name": c["name"],
                "value": c["value"],
                "domain": c.get("domain", ""),
                "path": c.get("path", "/"),
                "httpOnly": c.get("httpOnly", False),
                "secure": c.get("secure", False),
                "sameSite": c.get("sameSite", "Lax"),
            }
            if "expires" in c and c["expires"]:
                pc["expires"] = c["expires"]
            playwright_cookies.append(pc)

        if not playwright_cookies:
            log.warning(f"[{self.platform}] All cookies had invalid format, skipping injection")
            return False

        await context.add_cookies(playwright_cookies)
        log.info(f"[{self.platform}] Injected {len(playwright_cookies)} cookies into browser context")
        return True

    # ────────────────────────────────────────────
    # 3. 将新 Cookie 写回 DB
    # ────────────────────────────────────────────

    async def save_from_context(self, context: BrowserContext):
        """
        采集完成后，将浏览器 context 中的最新 Cookie 写回 DB。
        这样可以保持 Cookie 的"活跃态"（服务端续期的 session_id 等）。
        """
        if not self._account_id:
            log.warning(f"[{self.platform}] No account_id set, skipping cookie save")
            return

        try:
            new_cookies = await context.cookies()
            # 转为 DB 存储格式（list[dict]）
            raw = [
                {
                    "name": c["name"],
                    "value": c["value"],
                    "domain": c.get("domain", ""),
                    "path": c.get("path", "/"),
                    "httpOnly": c.get("httpOnly", False),
                    "secure": c.get("secure", False),
                    "expires": c.get("expires", -1),
                }
                for c in new_cookies
            ]
            factory = get_session_factory()
            with factory() as session:
                account = crud.get_platform_cookies(session, self.platform)
                if account:
                    account.cookies = raw
                    session.commit()
                    log.info(f"[{self.platform}] Saved {len(raw)} refreshed cookies to DB for account '{self._account_id}'")
        except Exception as e:
            log.error(f"[{self.platform}] Failed to save cookies back to DB: {e}")

    # ────────────────────────────────────────────
    # 4. 标记 Cookie 失效
    # ────────────────────────────────────────────

    def mark_expired(self):
        """
        当检测到当前 Cookie 已失效（被重定向至登录页等），
        调用此方法在 DB 中标记账号失效，防止下次继续使用。
        """
        if not self._account_id:
            return
        try:
            factory = get_session_factory()
            with factory() as session:
                from price_monitor.account_pool import AccountPool
                pool = AccountPool()
                pool.mark_failed(self.platform, self._account_id)
                log.warning(f"[{self.platform}] Account '{self._account_id}' marked as expired in DB")
        except Exception as e:
            log.error(f"[{self.platform}] Failed to mark account as expired: {e}")
