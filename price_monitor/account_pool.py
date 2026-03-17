"""
Cookie / 账号池管理器
基于文件存储的轻量版本 (可扩展为 Redis)

Cookie 存储格式兼容 Playwright:
    cookies 字段是 list[dict], 每个 dict 包含:
    {"name": "...", "value": "...", "domain": "...", "path": "/", ...}

可通过 cookie_harvester.py 自动采集并写入
"""

import json
import logging
import random
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

log = logging.getLogger("price_monitor.account_pool")


class AccountPool:
    """管理多平台 Cookie 和账号

    存储格式 (JSON 文件):
    {
        "jd_express": [
            {
                "id": "account_1",
                "cookies": [
                    {"name": "pt_key", "value": "xxx", "domain": ".jd.com", "path": "/", ...},
                    ...
                ],
                "user_agent": "...",
                "status": "active",
                "last_used": "2026-03-12T10:00:00",
                "fail_count": 0,
                "harvested_at": "2026-03-12T09:00:00"
            }
        ]
    }
    """

    COOLDOWN_MINUTES = 10  # cooldown 状态自动恢复时间

    def __init__(self, pool_file: str = "./accounts.json"):
        self.pool_file = Path(pool_file)
        self._pool: dict[str, list[dict]] = {}
        self._load()

    def _load(self) -> None:
        """从文件加载账号池"""
        if self.pool_file.exists():
            try:
                self._pool = json.loads(self.pool_file.read_text(encoding="utf-8"))
                total = sum(len(v) for v in self._pool.values())
                log.info(f"Loaded {total} accounts from {self.pool_file}")
            except (json.JSONDecodeError, IOError) as e:
                log.warning(f"Failed to load account pool: {e}")
                self._pool = {}
        else:
            self._pool = {}

    def _sync_and_save(self, update_func):
        """获取锁 -> 重新加载最新状态 -> 执行修改函数 -> 原子化保存回磁盘"""
        import fcntl, os, tempfile
        self.pool_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.pool_file.exists():
            with open(self.pool_file, "w", encoding="utf-8") as f:
                f.write("{}")
        try:
            with open(self.pool_file, "r+", encoding="utf-8") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    f.seek(0)
                    content = f.read()
                    self._pool = json.loads(content) if content else {}
                    
                    ret = update_func()
                    
                    fd, tmp_path = tempfile.mkstemp(dir=self.pool_file.parent, prefix="acc_", suffix=".tmp")
                    with os.fdopen(fd, "w", encoding="utf-8") as tmp_f:
                        json.dump(self._pool, tmp_f, ensure_ascii=False, indent=2)
                        tmp_f.flush()
                        os.fsync(tmp_f.fileno())
                    os.replace(tmp_path, self.pool_file)
                    return ret
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except Exception as e:
            log.error(f"Failed to sync and save account pool: {e}")
            return None

    def _auto_recover_cooldown(self, platform: str) -> None:
        """自动恢复超时 cooldown 账号"""
        cutoff = datetime.now() - timedelta(minutes=self.COOLDOWN_MINUTES)
        for acc in self._pool.get(platform, []):
            if acc["status"] == "cooldown":
                last_used = acc.get("last_used", "")
                if last_used:
                    try:
                        used_time = datetime.fromisoformat(last_used)
                        if used_time < cutoff:
                            acc["status"] = "active"
                            log.info(f"Auto-recovered {acc['id']}@{platform} from cooldown")
                    except ValueError:
                        pass

    def add_account(
        self,
        platform: str,
        account_id: str,
        cookies,
        user_agent: str = "",
    ) -> None:
        """添加或更新账号

        :param cookies: Playwright 格式 list[dict] 或简单 dict
        """
        def _op():
            if platform not in self._pool:
                self._pool[platform] = []
            
            # 检查是否已存在
            for acc in self._pool[platform]:
                if acc["id"] == account_id:
                    acc["cookies"] = normalized
                    acc["user_agent"] = user_agent
                    acc["status"] = "active"
                    acc["fail_count"] = 0
                    acc["harvested_at"] = datetime.now().isoformat()
                    return

            self._pool[platform].append({
                "id": account_id,
                "cookies": normalized,
                "user_agent": user_agent,
                "status": "active",
                "last_used": "",
                "fail_count": 0,
                "harvested_at": datetime.now().isoformat(),
            })

        self._sync_and_save(_op)
        log.info(f"Added account {account_id} for {platform} ({len(normalized)} cookies)")

    def get_cookie(self, platform: str) -> Optional[dict]:
        """获取一个可用账号信息 (优先选择有强身份验证 Cookie 的账号)

        :return: {"id": ..., "cookies": [...], "user_agent": ...} 或 None
        """
        def _op():
            self._auto_recover_cooldown(platform)
            accounts = self._pool.get(platform, [])
            active = [a for a in accounts if a["status"] == "active"]
            if not active:
                log.warning(f"No active accounts for {platform}")
                return None
            
            AUTH_KEYS = {"pt_key", "pt_pin", "unb", "_tb_token_", "token", "sessionid",
                         "auth_token", "access_token", "COOKIE_LOGIN_USER", "mall_login_token"}
            
            def _auth_strength(acc: dict) -> int:
                cookies_ = acc.get("cookies", [])
                if isinstance(cookies_, list):
                    return sum(1 for c in cookies_ if c.get("name") in AUTH_KEYS)
                return 0
                
            active_sorted = sorted(active, key=_auth_strength, reverse=True)
            top = [a for a in active_sorted if _auth_strength(a) >= _auth_strength(active_sorted[0])]
            import random
            selected = random.choice(top)
            selected["last_used"] = datetime.now().isoformat()
            
            return {
                "id": selected["id"],
                "cookies": selected["cookies"],
                "user_agent": selected.get("user_agent", ""),
            }

        return self._sync_and_save(_op)

    def get_playwright_cookies(self, platform: str) -> Optional[list[dict]]:
        """获取 Playwright 格式的 Cookie 列表
        可直接传入 StealthyFetcher.async_fetch(cookies=...)

        :return: [{"name": ..., "value": ..., "domain": ..., "path": ...}, ...] 或 None
        """
        account = self.get_cookie(platform)
        if not account:
            return None

        cookies = account["cookies"]

        # 如果已经是 Playwright list[dict] 格式
        if isinstance(cookies, list):
            return cookies

        # 如果是简单 dict 格式 {name: value}, 转换为 Playwright 格式
        if isinstance(cookies, dict):
            return [
                {"name": k, "value": v, "domain": "", "path": "/"}
                for k, v in cookies.items()
            ]

        return None

    def get_cookie_header(self, platform: str) -> Optional[str]:
        """获取 Cookie 字符串 (用于 HTTP Fetcher 的 headers)
        格式: "name1=value1; name2=value2; ..."

        :return: Cookie header 字符串或 None
        """
        account = self.get_cookie(platform)
        if not account:
            return None

        cookies = account["cookies"]

        if isinstance(cookies, list):
            # Playwright 格式
            return "; ".join(f"{c['name']}={c['value']}" for c in cookies)
        elif isinstance(cookies, dict):
            return "; ".join(f"{k}={v}" for k, v in cookies.items())

        return None

    def mark_failed(self, platform: str, account_id: str, max_fails: int = 3) -> None:
        def _op():
            for acc in self._pool.get(platform, []):
                if acc["id"] == account_id:
                    acc["fail_count"] = acc.get("fail_count", 0) + 1
                    if acc["fail_count"] >= max_fails:
                        acc["status"] = "invalid"
                        log.warning(f"Account {account_id}@{platform} marked invalid after {max_fails} failures")
                    else:
                        acc["status"] = "cooldown"
                        acc["last_used"] = datetime.now().isoformat()
                    return
        self._sync_and_save(_op)

    def mark_active(self, platform: str, account_id: str) -> None:
        def _op():
            for acc in self._pool.get(platform, []):
                if acc["id"] == account_id:
                    acc["status"] = "active"
                    acc["fail_count"] = 0
                    return
        self._sync_and_save(_op)

    def get_stats(self) -> dict:
        """返回各平台账号池统计"""
        stats = {}
        for platform, accounts in self._pool.items():
            stats[platform] = {
                "total": len(accounts),
                "active": sum(1 for a in accounts if a["status"] == "active"),
                "cooldown": sum(1 for a in accounts if a["status"] == "cooldown"),
                "invalid": sum(1 for a in accounts if a["status"] == "invalid"),
            }
        return stats

    @staticmethod
    def _normalize_cookies(cookies) -> list[dict]:
        """将各种格式的 Cookie 统一为 Playwright list[dict] 格式"""
        if isinstance(cookies, list):
            # 已经是列表格式, 确保每项有最小字段
            result = []
            for c in cookies:
                if isinstance(c, dict) and "name" in c and "value" in c:
                    result.append(c)
            return result

        if isinstance(cookies, dict):
            # 简单 dict {name: value}, 转为 list
            return [
                {"name": k, "value": str(v), "domain": "", "path": "/"}
                for k, v in cookies.items()
            ]

        return []

