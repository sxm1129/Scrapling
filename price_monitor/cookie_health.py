"""
cookie_health.py — Cookie 有效性探针
======================================
每小时自动探测各平台 Cookie 是否仍有效：
  - 用轻量 HEAD/GET 请求访问用户主页
  - 失效时标记 CookieAccount.status = EXPIRED
  - 调用 notify_cookie_expired() 推送飞书告警

使用方式:
  由 scheduler.py 每小时调用一次 run_health_check()
  或独立运行: python -m price_monitor.cookie_health
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

log = logging.getLogger(__name__)

# 各平台 Cookie 有效性探测 URL（访问后检查是否被重定向至登录页）
_PROBE_URLS: dict[str, str] = {
    "jd_express":    "https://home.m.jd.com/myJd/home.action",
    "taobao":        "https://my.taobao.com/",
    "tmall":         "https://my.taobao.com/",
    "taobao_flash":  "https://my.taobao.com/",
    "meituan_flash": "https://i.meituan.com/",
    "pinduoduo":     "https://mobile.yangkeduo.com/personal_v2.html",
}

# 各平台登录态判定：URL 中出现以下字符串 → 认为已过期
_LOGIN_INDICATORS: dict[str, list[str]] = {
    "jd_express":    ["plogin", "passport.jd.com", "login"],
    "taobao":        ["login.taobao.com", "login.m.taobao.com"],
    "tmall":         ["login.taobao.com"],
    "taobao_flash":  ["login.taobao.com"],
    "meituan_flash": ["passport.meituan.com", "account/login"],
    "pinduoduo":     ["login.html", "pinduoduo.com/login"],
}


async def _probe_platform(platform: str, cookies: list[dict]) -> bool:
    """
    探测平台 Cookie 是否有效。
    返回 True = 有效，False = 已过期。
    """
    probe_url = _PROBE_URLS.get(platform)
    if not probe_url:
        log.debug(f"[cookie_health] No probe URL for {platform}, skip")
        return True  # 未配置探测 URL，默认认为有效

    try:
        import httpx
        # 构建 cookie dict
        cookie_dict = {c["name"]: c["value"] for c in cookies if c.get("name") and c.get("value")}

        async with httpx.AsyncClient(
            timeout=10,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"},
            cookies=cookie_dict,
        ) as client:
            resp = await client.get(probe_url)
            final_url = str(resp.url)

        indicators = _LOGIN_INDICATORS.get(platform, ["login"])
        for ind in indicators:
            if ind in final_url.lower():
                log.warning(f"[cookie_health] {platform} cookie EXPIRED (redirected to {final_url[:80]})")
                return False

        log.info(f"[cookie_health] {platform} cookie OK (final_url={final_url[:60]})")
        return True

    except ImportError:
        log.warning("[cookie_health] httpx not installed, skipping probe (pip install httpx)")
        return True
    except Exception as e:
        log.error(f"[cookie_health] {platform} probe error: {e}")
        return True  # 探测异常时保守处理，不触发过期标记


async def run_health_check():
    """
    运行一次全平台 Cookie 健康检查。
    由 scheduler.py 定时调用。
    """
    from price_monitor.db.session import get_session_factory
    from price_monitor.db import crud
    from price_monitor.notify import notify_cookie_expired

    factory = get_session_factory()
    with factory() as session:
        from price_monitor.db.models import CookieAccount
        accounts = session.query(CookieAccount).filter(
            CookieAccount.status == "ACTIVE"
        ).all()

    log.info(f"[cookie_health] Checking {len(accounts)} active cookie accounts")

    for account in accounts:
        platform = account.platform
        cookies = account.cookies if isinstance(account.cookies, list) else []

        is_valid = await _probe_platform(platform, cookies)

        with factory() as session:
            acc = session.query(
                __import__("price_monitor.db.models", fromlist=["CookieAccount"]).CookieAccount
            ).filter_by(id=account.id).first()
            if acc:
                if not is_valid:
                    acc.status = "EXPIRED"
                    acc.expired_at = datetime.utcnow()
                    session.commit()
                    # 发送飞书告警
                    try:
                        notify_cookie_expired(platform, account.account_id)
                    except Exception as e:
                        log.error(f"[cookie_health] notify failed: {e}")
                else:
                    # 更新 last_used 探针时间
                    acc.last_used = datetime.utcnow()
                    session.commit()


def get_cookie_health_status() -> list[dict]:
    """
    获取所有 cookie 账号的健康状态（供 API 调用，同步版本）。
    返回每个账号的健康状态、创建时间、预估有效期。
    """
    from price_monitor.db.session import get_session_factory
    from price_monitor.db.models import CookieAccount

    factory = get_session_factory()
    with factory() as session:
        accounts = session.query(CookieAccount).order_by(CookieAccount.platform).all()

    now = datetime.utcnow()
    result = []
    for acc in accounts:
        # 基于 harvested_at 估算有效期（经验值：JD ~7天，淘宝 ~14天）
        created = acc.created_at or now
        age_days = (now - created).days
        health_score = max(0, 100 - age_days * 10)  # 每天降 10 分
        status_color = "green" if health_score >= 60 else ("yellow" if health_score >= 30 else "red")

        result.append({
            "id": acc.id,
            "platform": acc.platform,
            "account_id": acc.account_id,
            "status": acc.status,
            "cookie_count": len(acc.cookies) if isinstance(acc.cookies, list) else 0,
            "age_days": age_days,
            "health_score": health_score,
            "health_color": status_color,
            "last_used": acc.last_used.isoformat() if acc.last_used else None,
            "expired_at": acc.expired_at.isoformat() if acc.expired_at else None,
            "created_at": acc.created_at.isoformat() if acc.created_at else None,
        })

    return result
