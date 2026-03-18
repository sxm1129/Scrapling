"""
smoke_test_phase1.py — Phase 1 基础设施冒烟测试
================================================
测试内容:
  1. BrowserFactory: patchright 启动，真实浏览器打开 Baidu
  2. HumanActions: 贝塞尔鼠标移动 + 人类打字 + 滚动 + 阅读停顿
  3. Cookie Bridge: DB 连接正常 + 读取 taobao cookies（如有）
  4. 截图保存
  5. Playwright 指纹检测：访问 bot 检测页验证 webdriver=false

运行方式:
  export PLAYWRIGHT_HEADED=1  # 有头模式，看得到操作
  python3 -m price_monitor.playwright_engine.smoke_test_phase1
"""
import asyncio
import json
import logging
import sys
import os

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("smoke_test")
SCREENSHOT_DIR = "./data/screenshots/smoke"

# ─────────────────────────────────────────────
# Test 1: 浏览器启动 + 指纹检测
# ─────────────────────────────────────────────
async def test_browser_launch():
    log.info("=" * 50)
    log.info("TEST 1: Browser Launch & Fingerprint Check")
    log.info("=" * 50)

    from price_monitor.playwright_engine.browser import BrowserFactory

    results = {}

    async with BrowserFactory("taobao") as context:
        page = await context.new_page()

        # 访问 bot 检测页
        await page.goto("https://bot.sannysoft.com", timeout=30_000)
        await asyncio.sleep(3)

        # 检查 navigator.webdriver
        webdriver_val = await page.evaluate("navigator.webdriver")
        ua = await page.evaluate("navigator.userAgent")
        log.info(f"  navigator.webdriver = {webdriver_val}")
        log.info(f"  userAgent = {ua[:80]}")

        results["webdriver_flag"] = webdriver_val
        results["user_agent_ok"] = "Chrome" in ua and "Macintosh" in ua
        results["not_bot"] = (webdriver_val is None or webdriver_val == False)

        # 截图
        os.makedirs(SCREENSHOT_DIR, exist_ok=True)
        screenshot_path = os.path.join(SCREENSHOT_DIR, "smoke_bot_check.png")
        await page.screenshot(path=screenshot_path, full_page=True)
        log.info(f"  Screenshot saved: {screenshot_path}")
        results["screenshot"] = screenshot_path

        await page.close()

    status = "✅ PASS" if results.get("not_bot") and results.get("user_agent_ok") else "❌ FAIL"
    log.info(f"Test 1 Result: {status}")
    log.info(f"  webdriver={results.get('webdriver_flag')} | ua_ok={results.get('user_agent_ok')}")
    return results


# ─────────────────────────────────────────────
# Test 2: HumanActions 实战验证
# ─────────────────────────────────────────────
async def test_human_actions():
    log.info("=" * 50)
    log.info("TEST 2: HumanActions (Baidu Search)")
    log.info("=" * 50)

    from price_monitor.playwright_engine.browser import BrowserFactory
    from price_monitor.playwright_engine.human_actions import HumanActions

    results = {}

    async with BrowserFactory("taobao") as context:
        page = await context.new_page()
        human = HumanActions(page)

        # 访问百度
        await page.goto("https://www.baidu.com", timeout=30_000)
        await human.random_pause(1000, 2000)
        log.info("  Opened Baidu")

        # 用 human_type 打字到搜索框
        try:
            await human.human_type("#kw", "卡士酸奶 价格")
            log.info("  Typed search query into Baidu search box")
            results["type_ok"] = True
        except Exception as e:
            log.error(f"  human_type failed: {e}")
            results["type_ok"] = False

        # 按回车搜索
        await page.keyboard.press("Enter")
        await asyncio.sleep(2)
        log.info(f"  After search URL: {page.url[:80]}")

        # 模拟阅读
        await human.simulate_reading(3.0)
        log.info("  simulate_reading(3s) done")
        results["reading_ok"] = True

        # 截图
        screenshot_path = os.path.join(SCREENSHOT_DIR, "smoke_baidu_search.png")
        await page.screenshot(path=screenshot_path, full_page=False)
        log.info(f"  Screenshot: {screenshot_path}")
        results["screenshot"] = screenshot_path
        results["url_after_search"] = page.url

        await page.close()

    status = "✅ PASS" if results.get("type_ok") and results.get("reading_ok") else "❌ FAIL"
    log.info(f"Test 2 Result: {status}")
    return results


# ─────────────────────────────────────────────
# Test 3: Cookie Bridge
# ─────────────────────────────────────────────
async def test_cookie_bridge():
    log.info("=" * 50)
    log.info("TEST 3: Cookie Bridge (DB Read)")
    log.info("=" * 50)

    from price_monitor.playwright_engine.cookie_bridge import CookieBridge
    results = {}

    for platform in ["taobao", "tmall", "jd_express"]:
        bridge = CookieBridge(platform)
        raw = bridge._load_raw_cookies()
        if raw:
            account_id, cookies = raw
            log.info(f"  [{platform}] ✅ Found {len(cookies)} cookies for account '{account_id}'")
            results[platform] = {"count": len(cookies), "account": account_id}
        else:
            log.warning(f"  [{platform}] ⚠️  No cookies in DB (please upload cookies via /cookies API)")
            results[platform] = {"count": 0}

    return results


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
async def main():
    log.info("🚀 Phase 1 Smoke Test Starting...")
    log.info(f"   PLAYWRIGHT_HEADED = {os.getenv('PLAYWRIGHT_HEADED', '0')}")

    report = {}
    
    try:
        report["test1_browser"] = await test_browser_launch()
    except Exception as e:
        log.error(f"Test 1 FAILED with exception: {e}", exc_info=True)
        report["test1_browser"] = {"error": str(e)}

    try:
        report["test2_human_actions"] = await test_human_actions()
    except Exception as e:
        log.error(f"Test 2 FAILED with exception: {e}", exc_info=True)
        report["test2_human_actions"] = {"error": str(e)}

    try:
        report["test3_cookies"] = await test_cookie_bridge()
    except Exception as e:
        log.error(f"Test 3 FAILED with exception: {e}", exc_info=True)
        report["test3_cookies"] = {"error": str(e)}

    log.info("\n" + "=" * 50)
    log.info("SMOKE TEST SUMMARY")
    log.info("=" * 50)
    log.info(json.dumps(report, ensure_ascii=False, indent=2, default=str))

    # 判断整体 Pass/Fail
    t1_ok = "error" not in report.get("test1_browser", {}) and report.get("test1_browser", {}).get("not_bot")
    t2_ok = "error" not in report.get("test2_human_actions", {}) and report.get("test2_human_actions", {}).get("type_ok")
    t3_ok = "error" not in report.get("test3_cookies", {})

    all_pass = t1_ok and t2_ok and t3_ok
    log.info(f"\nOverall: {'✅ ALL PASS' if all_pass else '⚠️  SOME TESTS FAILED'}")
    log.info(f"  Test 1 (Browser): {'✅' if t1_ok else '❌'}")
    log.info(f"  Test 2 (HumanActions): {'✅' if t2_ok else '❌'}")
    log.info(f"  Test 3 (Cookie Bridge): {'✅' if t3_ok else '❌'}")

    return report


if __name__ == "__main__":
    asyncio.run(main())
