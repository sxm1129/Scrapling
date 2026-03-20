"""
capture_cookies.py — 手动登录 Cookie 抓取工具
===============================================
使用方式:
  python3 -m price_monitor.playwright_engine.capture_cookies [platform]

例:
  python3 -m price_monitor.playwright_engine.capture_cookies jd_express
  python3 -m price_monitor.playwright_engine.capture_cookies taobao
  python3 -m price_monitor.playwright_engine.capture_cookies tmall
  python3 -m price_monitor.playwright_engine.capture_cookies meituan_flash
  python3 -m price_monitor.playwright_engine.capture_cookies pinduoduo
  python3 -m price_monitor.playwright_engine.capture_cookies taobao_flash

流程:
  1. 打开有头浏览器，导航到对应平台登录页
  2. 终端提示"请在浏览器中手动登录，登录完成后回到终端按 Enter"
  3. 按 Enter 后，自动从浏览器 context 抓取所有 Cookie
  4. 将 Cookie 写入数据库 CookieAccount 表（已有账号则更新）
  5. 输出 Cookie 数量确认
"""
import asyncio
import json
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("capture_cookies")

# 各平台登录入口 URL
LOGIN_URLS = {
    "jd_express":    "https://plogin.m.jd.com/login/login",
    "taobao":        "https://login.taobao.com/",
    "tmall":         "https://login.taobao.com/",          # 天猫共用淘宝账号
    "taobao_flash":  "https://login.taobao.com/",
    "meituan_flash": "https://passport.meituan.com/account/unitivelogin",
    "pinduoduo":     "https://mobile.yangkeduo.com/login.html",  # C 端消费者入口
}

# 各平台验证"已登录"的 URL/特征
LOGIN_SUCCESS_INDICATORS = {
    "jd_express":    ["my.m.jd.com", "home.m.jd.com"],
    "taobao":        ["my.taobao.com", "taobao.com/my_taobao"],
    "tmall":         ["my.taobao.com", "my.tmall.com"],
    "taobao_flash":  ["my.taobao.com"],
    "meituan_flash": ["meituan.com"],
    "pinduoduo":     ["pinduoduo.com/personal"],
}


async def capture_platform(platform: str):
    from price_monitor.playwright_engine.browser import BrowserFactory
    from price_monitor.playwright_engine.cookie_bridge import CookieBridge
    from price_monitor.db.session import get_session_factory
    from price_monitor.db import crud

    login_url = LOGIN_URLS.get(platform)
    if not login_url:
        log.error(f"Unknown platform: {platform}. Available: {list(LOGIN_URLS.keys())}")
        return

    log.info(f"[{platform}] Opening browser at: {login_url}")

    import os
    os.environ["PLAYWRIGHT_HEADED"] = "1"  # 强制有头

    async with BrowserFactory(platform) as context:
        page = await context.new_page()
        await page.goto(login_url, timeout=30_000)

        print(f"\n{'='*60}")
        print(f"  平台: {platform}")
        print(f"  浏览器已打开登录页。")
        print(f"  请在浏览器中完成登录（手机扫码 / 输入密码均可）")
        print(f"  登录完成后，回到此终端按 ENTER 键继续...")
        print(f"{'='*60}\n")
        input("  >>> 已登录完成，按 ENTER 抓取 Cookie: ")

        # 抓取当前 context 的所有 Cookie
        cookies = await context.cookies()
        if not cookies:
            log.error("No cookies captured! Please make sure you are logged in.")
            return

        log.info(f"[{platform}] Captured {len(cookies)} cookies from browser")

        # 转换为存储格式
        raw_cookies = [
            {
                "name": c["name"],
                "value": c["value"],
                "domain": c.get("domain", ""),
                "path": c.get("path", "/"),
                "httpOnly": c.get("httpOnly", False),
                "secure": c.get("secure", False),
                "expires": c.get("expires", -1),
            }
            for c in cookies
        ]

        # 写入 DB
        factory = get_session_factory()
        with factory() as session:
            account = crud.get_platform_cookies(session, platform)
            if account:
                account.cookies = raw_cookies
                session.commit()
                log.info(f"[{platform}] Updated existing account '{account.account_id}' with {len(raw_cookies)} cookies")
            else:
                import time
                account_id = f"{platform}_{int(time.time())}"
                crud.save_cookies(session, platform, account_id, raw_cookies)
                session.commit()
                log.info(f"[{platform}] Created new account '{account_id}' with {len(raw_cookies)} cookies")

        # 简要输出 Cookie 预览
        key_cookies = [c for c in cookies if any(
            k in c["name"].lower() for k in ["tok", "sid", "session", "uid", "pin", "auth"]
        )]
        print(f"\n✅ Cookie 已保存到数据库！")
        print(f"   总计: {len(cookies)} 个")
        print(f"   关键认证 Cookie: {[c['name'] for c in key_cookies[:5]]}")

        await page.close()


async def main():
    if len(sys.argv) < 2:
        print("用法: python3 -m price_monitor.playwright_engine.capture_cookies <platform>")
        print(f"可用平台: {list(LOGIN_URLS.keys())}")
        return

    platform = sys.argv[1]
    await capture_platform(platform)


if __name__ == "__main__":
    asyncio.run(main())
