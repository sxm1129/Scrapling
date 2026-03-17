"""
Cookie 管理 API — RESTful 路由
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from price_monitor.cookie_manager import CookieManager
from price_monitor.api.auth import require_auth

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/cookie-mgmt", tags=["cookie-mgmt"])

_manager: Optional[CookieManager] = None


def _get_manager() -> CookieManager:
    global _manager
    if _manager is None:
        _manager = CookieManager()
    return _manager


# ── Pydantic ──

class StatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(active|invalid|cooldown)$")


# ── Endpoints ──

@router.get("/status")
def get_cookie_status():
    """所有平台 Cookie 健康总览"""
    manager = _get_manager()
    return {"platforms": manager.get_all_status()}


@router.post("/validate/{platform}")
async def validate_platform_cookie(platform: str):
    """验证单平台 Cookie 有效性"""
    manager = _get_manager()
    result = await manager.validate_cookie(platform)
    return result


@router.post("/validate-all")
async def validate_all_cookies():
    """批量验证所有平台"""
    manager = _get_manager()
    results = await manager.validate_all()
    valid_count = sum(1 for r in results if r["valid"])
    return {
        "results": results,
        "summary": {
            "total": len(results),
            "valid": valid_count,
            "invalid": len(results) - valid_count,
        },
    }


@router.post("/sync")
def sync_cookies():
    """accounts.json → DB 同步"""
    manager = _get_manager()
    return manager.sync_pool_to_db()


@router.delete("/{platform}/{account_id}")
def delete_cookie_account(platform: str, account_id: str):
    """删除指定账号"""
    manager = _get_manager()
    ok = manager.delete_account(platform, account_id)
    if not ok:
        raise HTTPException(404, "Account not found")
    return {"ok": True, "platform": platform, "account_id": account_id}


@router.put("/{platform}/{account_id}/status")
def update_cookie_status(platform: str, account_id: str, data: StatusUpdate):
    """手动更新状态"""
    manager = _get_manager()
    ok = manager.refresh_status(platform, account_id, data.status)
    if not ok:
        raise HTTPException(400, f"Invalid status: {data.status}")
    return {"ok": True, "platform": platform, "account_id": account_id, "status": data.status}


@router.post("/harvest/{platform}")
def harvest_cookie(platform: str):
    """在后台(或新终端)启动 Cookie 采集器"""
    import subprocess
    import os
    import re
    
    if not re.match(r"^[a-zA-Z0-9_]+$", platform):
        raise HTTPException(400, "Invalid platform format")
        
    # 获取项目根目录 (假设 API 跑在 price_monitor/api 下, 返回两层)
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    
    # 构建命令
    cmd = f"cd {base_dir} && python3 -m price_monitor.cookie_harvester --platform {platform} --timeout 120"
    
    try:
        # 因为用户在 Mac 上，直接弹出一个全新的 Terminal 窗口运行体验最好
        apple_script = f'''
        tell application "Terminal"
            activate
            do script "{cmd}"
        end tell
        '''
        subprocess.Popen(["osascript", "-e", apple_script])
        return {"ok": True, "message": f"Cookie Harvester started for {platform} in a new Terminal window."}
    except Exception as e:
        log.error(f"Failed to launch harvester: {e}")
        raise HTTPException(500, f"Failed to open harvester terminal: {str(e)}")
