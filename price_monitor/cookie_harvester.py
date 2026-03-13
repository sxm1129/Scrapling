"""
Cookie 采集器 — 打开可视化浏览器让用户手动登录, 然后自动抓取并保存 Cookie

使用方式:
    python -m price_monitor.cookie_harvester --platform jd_express
    python -m price_monitor.cookie_harvester --platform taobao
    python -m price_monitor.cookie_harvester --platform meituan_flash

流程:
    1. 打开一个可见的 Chrome 浏览器
    2. 导航到对应平台的登录页
    3. 用户手动完成登录 (扫码/密码)
    4. 程序检测到登录成功后自动抓取 Cookie
    5. 保存到 AccountPool (accounts.json)
"""

import asyncio
import argparse
import logging
import sys
import json
from datetime import datetime
from pathlib import Path

log = logging.getLogger("price_monitor.cookie_harvester")

# 各平台登录入口和登录成功检测
PLATFORM_LOGIN_CONFIG = {
    "jd_express": {
        "login_url": "https://plogin.m.jd.com/login/login?appid=300&returnurl=https%3A%2F%2Fm.jd.com%2F",
        "success_url_pattern": "m.jd.com",  # 登录成功后会跳转到这个域名
        "success_cookie": "pt_key",          # 登录成功后存在的 Cookie 名
        "domain_filter": [".jd.com", ".m.jd.com"],  # 只保存这些域名的 Cookie
        "display_name": "京东",
    },
    "taobao": {
        "login_url": "https://login.m.taobao.com/login.htm?redirectURL=https%3A%2F%2Fm.taobao.com%2F",
        "success_url_pattern": "m.taobao.com",
        "success_cookie": "unb",  # unb = user number, 登录后才出现
        "domain_filter": [".taobao.com", ".tmall.com", ".alicdn.com"],
        "display_name": "淘宝/天猫",
    },
    "tmall": {
        "login_url": "https://login.m.taobao.com/login.htm?redirectURL=https%3A%2F%2Fm.tmall.com%2F",
        "success_url_pattern": "tmall.com",
        "success_cookie": "unb",  # unb = user number, 登录后才出现
        "domain_filter": [".taobao.com", ".tmall.com"],
        "display_name": "天猫",
    },
    "meituan_flash": {
        "login_url": "https://passport.meituan.com/account/unitivelogin",
        "success_url_pattern": "meituan.com",
        "success_cookie": "token",
        "domain_filter": [".meituan.com", ".waimai.meituan.com"],
        "display_name": "美团",
    },
    "douyin": {
        "login_url": "https://www.douyin.com/",
        "success_url_pattern": "douyin.com",
        "success_cookie": "sessionid",
        "domain_filter": [".douyin.com"],
        "display_name": "抖音",
    },
    "xiaohongshu": {
        "login_url": "https://www.xiaohongshu.com/",
        "success_url_pattern": "xiaohongshu.com",
        "success_cookie": "web_session",
        "domain_filter": [".xiaohongshu.com"],
        "display_name": "小红书",
    },
    "pinduoduo": {
        "login_url": "https://mobile.yangkeduo.com/login.html",
        "success_url_pattern": "yangkeduo.com",
        "success_cookie": "PDDAccessToken",
        "domain_filter": [".yangkeduo.com", ".pinduoduo.com"],
        "display_name": "拼多多",
    },
    "taobao_flash": {
        "login_url": "https://login.m.taobao.com/login.htm",
        "success_url_pattern": "taobao.com",
        "success_cookie": "_m_h5_tk",
        "domain_filter": [".taobao.com", ".tmall.com"],
        "display_name": "淘宝闪购",
    },
    "pupu": {
        "login_url": "https://www.pupumall.com/",
        "success_url_pattern": "pupumall.com",
        "success_cookie": "session_id",
        "domain_filter": [".pupumall.com", ".pupu.com"],
        "display_name": "朴朴超市",
    },
    "xiaoxiang": {
        "login_url": "https://www.meituan.com/",
        "success_url_pattern": "meituan.com",
        "success_cookie": "token",
        "domain_filter": [".meituan.com"],
        "display_name": "小象超市",
    },
    "dingdong": {
        "login_url": "https://www.ddxq.mobi/",
        "success_url_pattern": "ddxq.mobi",
        "success_cookie": "DDXQSESSID",
        "domain_filter": [".ddxq.mobi", ".dingdongmaicai.com"],
        "display_name": "叮咚买菜",
    },
    "community_group": {
        "login_url": "https://mobile.yangkeduo.com/duo_cms_mall.html",
        "success_url_pattern": "yangkeduo.com",
        "success_cookie": "PDDAccessToken",
        "domain_filter": [".yangkeduo.com", ".pinduoduo.com", ".meituan.com"],
        "display_name": "社区团购",
    },
}

# 登录态检测 JS — 在页面中轮询检查是否完成登录
JS_CHECK_LOGIN = """() => {
    return {
        url: window.location.href,
        cookies: document.cookie,
        title: document.title,
    };
}"""


async def harvest_cookies(
    platform: str,
    account_id: str = "",
    pool_file: str = "./accounts.json",
    timeout: int = 300,
) -> bool:
    """打开浏览器让用户手动登录, 然后采集 Cookie

    :param platform: 平台标识 (如 jd_express)
    :param account_id: 账号 ID 标签
    :param pool_file: Cookie 池文件路径
    :param timeout: 等待登录的超时时间 (秒)
    :return: 是否成功
    """
    config = PLATFORM_LOGIN_CONFIG.get(platform)
    if not config:
        log.error(f"Unsupported platform: {platform}")
        log.info(f"Supported: {list(PLATFORM_LOGIN_CONFIG.keys())}")
        return False

    if not account_id:
        account_id = f"{platform}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    log.info(f"========================================")
    log.info(f"Cookie 采集: {config['display_name']}")
    log.info(f"账号标签: {account_id}")
    log.info(f"========================================")
    log.info(f"即将打开浏览器, 请在 {timeout} 秒内完成登录")
    log.info(f"登录成功后程序将自动采集 Cookie 并保存\n")

    try:
        from patchright.async_api import async_playwright
    except ImportError:
        log.error("缺少 patchright 依赖, 请运行: pip install patchright")
        return False

    async with async_playwright() as p:
        # 用可见模式启动浏览器
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--window-size=430,932",  # 手机尺寸
            ],
        )

        context = await browser.new_context(
            viewport={"width": 430, "height": 932},
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/17.0 Mobile/15E148 Safari/604.1"
            ),
            locale="zh-CN",
        )

        page = await context.new_page()
        await page.goto(config["login_url"], wait_until="domcontentloaded")

        log.info(f"浏览器已打开: {config['login_url']}")
        log.info("请在浏览器中完成登录 (扫码或输入密码)...")

        # 轮询检测登录状态
        success = False
        elapsed = 0
        check_interval = 2  # 每 2 秒检测一次

        while elapsed < timeout and not success:
            await asyncio.sleep(check_interval)
            elapsed += check_interval

            try:
                # 获取当前页面所有 Cookie
                cookies = await context.cookies()

                # 检查登录标志 Cookie
                cookie_names = {c["name"] for c in cookies}
                current_url = page.url

                # 两种检测方式:
                # 1. 特定 Cookie 出现
                has_login_cookie = config["success_cookie"] in cookie_names
                # 2. URL 跳转到成功页面 (排除登录页本身)
                url_matched = (
                    config["success_url_pattern"] in current_url
                    and "login" not in current_url.lower()
                    and "plogin" not in current_url.lower()
                )

                if has_login_cookie or url_matched:
                    log.info(f"\n✅ 检测到登录成功!")
                    log.info(f"   当前 URL: {current_url}")
                    log.info(f"   Cookie 数量: {len(cookies)}")

                    # ── 登录后 Cookie 增强: 多等一会, 并导航到主页面获取更多 Cookie ──
                    log.info("   等待 Cookie 稳定 (3s)...")
                    await asyncio.sleep(3)

                    # 尝试导航到主页面收集更多 Cookie
                    enrich_urls = {
                        "taobao": "https://m.taobao.com/",
                        "tmall": "https://m.tmall.com/",
                        "taobao_flash": "https://m.taobao.com/",
                    }
                    enrich_url = enrich_urls.get(platform)
                    if enrich_url:
                        log.info(f"   导航到主页面增强 Cookie: {enrich_url}")
                        try:
                            await page.goto(enrich_url, wait_until="domcontentloaded", timeout=15000)
                            await asyncio.sleep(3)
                        except Exception as nav_err:
                            log.debug(f"   增强导航失败 (非致命): {nav_err}")

                    # 重新收集 Cookie (登录后+导航后的完整 Cookie)
                    cookies = await context.cookies()
                    log.info(f"   增强后 Cookie 数量: {len(cookies)}")

                    # 过滤出平台相关的 Cookie
                    filtered = _filter_cookies(cookies, config["domain_filter"])

                    if not filtered:
                        filtered = cookies
                        log.warning("   域名过滤后 Cookie 为空, 保留全部")

                    log.info(f"   有效 Cookie: {len(filtered)} 条")

                    # 保存到账号池 (独立 try 块, 避免影响 break)
                    try:
                        ua = ""
                        try:
                            ua = context._options.get("user_agent", "")
                        except AttributeError:
                            pass
                        _save_to_pool(
                            pool_file=pool_file,
                            platform=platform,
                            account_id=account_id,
                            cookies=filtered,
                            user_agent=ua,
                        )
                    except Exception as save_err:
                        log.error(f"保存 Cookie 失败: {save_err}")

                    success = True
                    break

                # 进度提示
                if elapsed % 10 == 0:
                    log.info(f"   等待登录中... ({elapsed}/{timeout}s)")

            except Exception as e:
                log.debug(f"Check error: {e}")

        if not success:
            log.warning(f"\n⏳ 登录超时 ({timeout}s)")
            log.info("你可以重新运行此命令重试")

        await browser.close()

    return success


def _filter_cookies(cookies: list[dict], domain_patterns: list[str]) -> list[dict]:
    """按域名模式过滤 Cookie"""
    filtered = []
    for c in cookies:
        domain = c.get("domain", "")
        for pattern in domain_patterns:
            if domain.endswith(pattern.lstrip(".")):
                # 只保留 Playwright 格式的关键字段
                filtered.append({
                    "name": c["name"],
                    "value": c["value"],
                    "domain": c["domain"],
                    "path": c.get("path", "/"),
                    "secure": c.get("secure", False),
                    "httpOnly": c.get("httpOnly", False),
                    "sameSite": c.get("sameSite", "Lax"),
                })
                break
    return filtered


def _save_to_pool(
    pool_file: str,
    platform: str,
    account_id: str,
    cookies: list[dict],
    user_agent: str,
) -> None:
    """保存 Cookie 到账号池 JSON 文件"""
    path = Path(pool_file)
    pool: dict = {}

    if path.exists():
        try:
            pool = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            pool = {}

    if platform not in pool:
        pool[platform] = []

    # 更新或添加
    found = False
    for acc in pool[platform]:
        if acc["id"] == account_id:
            acc["cookies"] = cookies
            acc["user_agent"] = user_agent
            acc["status"] = "active"
            acc["fail_count"] = 0
            acc["harvested_at"] = datetime.now().isoformat()
            found = True
            break

    if not found:
        pool[platform].append({
            "id": account_id,
            "cookies": cookies,
            "user_agent": user_agent,
            "status": "active",
            "last_used": "",
            "fail_count": 0,
            "harvested_at": datetime.now().isoformat(),
        })

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pool, ensure_ascii=False, indent=2), encoding="utf-8")

    log.info(f"\n💾 Cookie 已保存到: {pool_file}")
    log.info(f"   平台: {platform}")
    log.info(f"   账号: {account_id}")
    log.info(f"   Cookie 数量: {len(cookies)}")

    # 显示关键 Cookie 名 (不显示值)
    key_names = [c["name"] for c in cookies[:10]]
    log.info(f"   关键 Cookie: {', '.join(key_names)}")


def main():
    parser = argparse.ArgumentParser(description="Cookie 采集器 — 手动登录后自动保存")
    parser.add_argument("--platform", "-p", required=True,
                        help=f"平台 ({', '.join(PLATFORM_LOGIN_CONFIG.keys())})")
    parser.add_argument("--account-id", "-a", default="",
                        help="账号标签 (默认自动生成)")
    parser.add_argument("--pool-file", "-f", default="./accounts.json",
                        help="Cookie 池文件路径")
    parser.add_argument("--timeout", "-t", type=int, default=300,
                        help="登录超时 (秒, 默认 300)")
    parser.add_argument("--list", action="store_true",
                        help="列出支持的平台")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.list:
        print("\n支持的平台:")
        for key, cfg in PLATFORM_LOGIN_CONFIG.items():
            print(f"  {key:20s} {cfg['display_name']}")
        return

    success = asyncio.run(harvest_cookies(
        platform=args.platform,
        account_id=args.account_id,
        pool_file=args.pool_file,
        timeout=args.timeout,
    ))

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
