"""
Cookie 生命周期管理器

统一管理 Cookie 的获取, 存储, 验证, 同步:
  - 有效性探测 (轻量 HTTP 请求验证登录态)
  - accounts.json ↔ CookieAccount DB 双向同步
  - 状态管理 (active / invalid / cooldown)
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

from price_monitor.account_pool import AccountPool
from price_monitor.db.session import get_session_factory
from price_monitor.db import crud
from price_monitor.cookie_harvester import PLATFORM_LOGIN_CONFIG

log = logging.getLogger(__name__)

ACCOUNTS_FILE = str(Path(__file__).resolve().parents[1] / "accounts.json")

# ── 有效性探测配置 ──
# 每个平台一个轻量 URL, 通过 HTTP 返回判断 Cookie 是否有效
VALIDATION_PROBES: dict[str, dict] = {
    "taobao": {
        "url": "https://h5api.m.taobao.com/h5/mtop.user.getusersimple/1.0/?data={}",
        "method": "GET",
        "success_check": lambda r: r.status_code == 200 and "nick" in r.text,
        "label": "获取用户昵称",
    },
    "tmall": {
        "url": "https://h5api.m.tmall.com/h5/mtop.user.getusersimple/1.0/?data={}",
        "method": "GET",
        "success_check": lambda r: r.status_code == 200 and "nick" in r.text,
        "label": "获取用户昵称",
    },
    "jd_express": {
        "url": "https://api.m.jd.com/client.action?functionId=newPing",
        "method": "GET",
        "success_check": lambda r: r.status_code == 200 and '"code":"3"' not in r.text,
        "label": "JD Ping",
    },
    "pinduoduo": {
        "url": "https://mobile.yangkeduo.com/proxy/api/api/einstein/homepage/queryHomepage",
        "method": "GET",
        "success_check": lambda r: r.status_code == 200 and "login" not in r.url,
        "label": "首页API",
    },
    "meituan_flash": {
        "url": "https://apimobile.meituan.com/group/v1/user/account/queryaccount",
        "method": "GET",
        "success_check": lambda r: r.status_code == 200,
        "label": "用户账号查询",
    },
    "douyin": {
        "url": "https://www.douyin.com/aweme/v1/web/im/user/info/",
        "method": "GET",
        "success_check": lambda r: r.status_code == 200 and '"status_code":0' in r.text,
        "label": "用户信息",
    },
    "xiaohongshu": {
        "url": "https://edith.xiaohongshu.com/api/sns/web/v1/user/selfinfo",
        "method": "GET",
        "success_check": lambda r: r.status_code == 200 and '"success":true' in r.text,
        "label": "用户自身信息",
    },
}

# 无专用探测 URL 的平台 — 退化为 Cookie 名存在性检查
COOKIE_EXISTENCE_PLATFORMS = {
    "taobao_flash": "_m_h5_tk",
    "pupu": "session_id",
    "xiaoxiang": "token",
    "dingdong": "DDXQSESSID",
    "community_group": "PDDAccessToken",
}


class CookieManager:
    """Cookie 生命周期统一管理"""

    def __init__(self, pool_file: str = None):
        self.pool_file = pool_file or ACCOUNTS_FILE
        self.pool = AccountPool(pool_file=self.pool_file)

    def get_all_status(self) -> list[dict]:
        """所有平台 Cookie 健康总览"""
        pool_stats = self.pool.get_stats()

        # 从 accounts.json 获取详细信息
        pool_data = self.pool._pool

        result = []
        for platform, config in PLATFORM_LOGIN_CONFIG.items():
            accounts = pool_data.get(platform, [])
            stats = pool_stats.get(platform, {})

            # 找最新的 harvested_at
            latest_harvest = None
            for acc in accounts:
                h = acc.get("harvested_at", "")
                if h and (latest_harvest is None or h > latest_harvest):
                    latest_harvest = h

            result.append({
                "platform": platform,
                "display_name": config["display_name"],
                "account_count": stats.get("total", 0),
                "active_count": stats.get("active", 0),
                "cooldown_count": stats.get("cooldown", 0),
                "invalid_count": stats.get("invalid", 0),
                "harvested_at": latest_harvest,
                "success_cookie": config["success_cookie"],
                "accounts": [
                    {
                        "id": acc["id"],
                        "status": acc.get("status", "unknown"),
                        "fail_count": acc.get("fail_count", 0),
                        "last_used": acc.get("last_used", ""),
                        "harvested_at": acc.get("harvested_at", ""),
                        "cookie_count": len(acc.get("cookies", [])),
                    }
                    for acc in accounts
                ],
            })

        return result

    async def validate_cookie(self, platform: str) -> dict:
        """验证指定平台的 Cookie 有效性"""
        result = {
            "platform": platform,
            "valid": False,
            "detail": "",
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

        # 获取 Cookie
        account = self.pool.get_cookie(platform)
        if not account:
            result["detail"] = "无可用账号"
            return result

        cookies = account["cookies"]
        account_id = account["id"]

        # 方式 1: HTTP 探测 URL
        probe = VALIDATION_PROBES.get(platform)
        if probe:
            try:
                cookie_str = self._cookies_to_header(cookies)
                headers = {
                    "Cookie": cookie_str,
                    "User-Agent": (
                        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                        "AppleWebKit/605.1.15 Mobile/15E148"
                    ),
                }
                resp = await asyncio.to_thread(
                    lambda: requests.get(
                        probe["url"], headers=headers, timeout=10,
                        allow_redirects=False,
                    )
                )
                is_valid = probe["success_check"](resp)
                result["valid"] = is_valid
                result["detail"] = (
                    f"{probe['label']}: {'有效' if is_valid else '无效'} "
                    f"(HTTP {resp.status_code})"
                )

                # 更新 pool 状态
                if not is_valid:
                    self.pool.mark_failed(platform, account_id)
                else:
                    self.pool.mark_active(platform, account_id)

            except Exception as e:
                result["detail"] = f"探测失败: {str(e)[:200]}"
                log.warning(f"Cookie validation probe failed for {platform}: {e}")

            return result

        # 方式 2: Cookie 名存在性检查
        expected_cookie = COOKIE_EXISTENCE_PLATFORMS.get(platform)
        if expected_cookie:
            cookie_names = set()
            if isinstance(cookies, list):
                cookie_names = {c.get("name", "") for c in cookies}
            elif isinstance(cookies, dict):
                cookie_names = set(cookies.keys())

            has_key = expected_cookie in cookie_names
            result["valid"] = has_key
            result["detail"] = (
                f"Cookie '{expected_cookie}': {'存在' if has_key else '缺失'}"
            )
            return result

        # 方式 3: 通用 — 至少有 Cookie 就算有效
        result["valid"] = bool(cookies)
        result["detail"] = f"Cookie 数量: {len(cookies) if isinstance(cookies, list) else 0}"
        return result

    async def validate_all(self) -> list[dict]:
        """批量验证所有平台"""
        results = []
        for platform in PLATFORM_LOGIN_CONFIG:
            try:
                r = await self.validate_cookie(platform)
                results.append(r)
            except Exception as e:
                results.append({
                    "platform": platform,
                    "valid": False,
                    "detail": f"验证异常: {str(e)[:200]}",
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                })
        return results

    def sync_pool_to_db(self) -> dict:
        """accounts.json → CookieAccount DB 同步"""
        factory = get_session_factory()
        session = factory()
        synced = 0

        try:
            pool_data = self.pool._pool
            for platform, accounts in pool_data.items():
                for acc in accounts:
                    cookies = acc.get("cookies", [])
                    account_id = acc.get("id", "")
                    if not account_id:
                        continue

                    status = acc.get("status", "active").upper()
                    if status == "ACTIVE":
                        db_status = "ACTIVE"
                    elif status == "INVALID":
                        db_status = "EXPIRED"
                    else:
                        db_status = status.upper()

                    crud.save_cookies(session, platform, account_id, cookies)
                    synced += 1

            session.commit()
            log.info(f"Synced {synced} accounts from JSON to DB")
            return {"synced": synced, "status": "ok"}

        except Exception as e:
            session.rollback()
            log.error(f"Sync failed: {e}")
            return {"synced": 0, "status": "error", "error": str(e)[:500]}
        finally:
            session.close()

    def delete_account(self, platform: str, account_id: str) -> bool:
        """从 JSON + DB 同时删除"""
        deleted = False

        # 从 accounts.json 删除
        accounts = self.pool._pool.get(platform, [])
        before = len(accounts)
        self.pool._pool[platform] = [
            a for a in accounts if a.get("id") != account_id
        ]
        if len(self.pool._pool[platform]) < before:
            self.pool._save()
            deleted = True

        # 从 DB 删除
        factory = get_session_factory()
        session = factory()
        try:
            from price_monitor.db.models import CookieAccount
            ca = session.query(CookieAccount).filter(
                CookieAccount.platform == platform,
                CookieAccount.account_id == account_id,
            ).first()
            if ca:
                session.delete(ca)
                session.commit()
                deleted = True
        except Exception as e:
            session.rollback()
            log.error(f"DB delete failed: {e}")
        finally:
            session.close()

        return deleted

    def refresh_status(self, platform: str, account_id: str, status: str) -> bool:
        """手动更新状态"""
        if status == "active":
            self.pool.mark_active(platform, account_id)
            return True
        elif status == "invalid":
            self.pool.mark_failed(platform, account_id, max_fails=1)
            return True
        return False

    @staticmethod
    def _cookies_to_header(cookies) -> str:
        """Cookie 列表 → HTTP header 字符串"""
        if isinstance(cookies, list):
            return "; ".join(f"{c['name']}={c['value']}" for c in cookies if "name" in c)
        if isinstance(cookies, dict):
            return "; ".join(f"{k}={v}" for k, v in cookies.items())
        return ""
