"""
Cookie 管理 API — RESTful 路由
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from price_monitor.db.session import get_db
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
async def validate_platform_cookie(platform: str, _=Depends(require_auth)):
    """验证单平台 Cookie 有效性"""
    manager = _get_manager()
    result = await manager.validate_cookie(platform)
    return result


@router.post("/validate-all")
async def validate_all_cookies(_=Depends(require_auth)):
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
def sync_cookies(_=Depends(require_auth)):
    """accounts.json → DB 同步"""
    manager = _get_manager()
    return manager.sync_pool_to_db()


@router.delete("/{platform}/{account_id}")
def delete_cookie_account(
    platform: str, account_id: str, _=Depends(require_auth),
):
    """删除指定账号"""
    manager = _get_manager()
    ok = manager.delete_account(platform, account_id)
    if not ok:
        raise HTTPException(404, "Account not found")
    return {"ok": True, "platform": platform, "account_id": account_id}


@router.put("/{platform}/{account_id}/status")
def update_cookie_status(
    platform: str, account_id: str, data: StatusUpdate,
    _=Depends(require_auth),
):
    """手动更新状态"""
    manager = _get_manager()
    ok = manager.refresh_status(platform, account_id, data.status)
    if not ok:
        raise HTTPException(400, f"Invalid status: {data.status}")
    return {"ok": True, "platform": platform, "account_id": account_id, "status": data.status}
