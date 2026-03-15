"""
采集管理 API — RESTful 路由
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from price_monitor.db.session import get_db
from price_monitor.db import crud
from price_monitor.collection_manager import CollectionManager, _job_to_dict
from price_monitor.scrapers.registry import list_supported_platforms

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/collection", tags=["collection"])

# 全局 manager 实例 (延迟初始化)
_manager: Optional[CollectionManager] = None


def _get_manager() -> CollectionManager:
    global _manager
    if _manager is None:
        _manager = CollectionManager()
    return _manager


# ── Pydantic 请求模型 ──

class TriggerPlatformScan(BaseModel):
    keyword: Optional[str] = None

class TriggerSingleScrape(BaseModel):
    platform: str = Field(..., min_length=1, max_length=20)
    url: str = Field(..., min_length=10, max_length=500)


# ── 认证依赖 ──

def require_auth(request: Request):
    """复用主 app 的认证逻辑"""
    import os
    password = os.getenv("ADMIN_PASSWORD", "kashi2026")
    auth = request.headers.get("Authorization", "")
    token = request.query_params.get("token", "")
    if auth == f"Bearer {password}" or token == password:
        return True
    raise HTTPException(401, "Authentication required")


# ── Endpoints ──

@router.get("/status")
def get_collection_status(db: Session = Depends(get_db)):
    """实时采集总览 — 每平台最近任务状态"""
    manager = _get_manager()
    platforms = manager.list_platform_status()
    # 查询运行中的任务
    running_jobs, _ = crud.list_jobs(db, status="RUNNING", page_size=10)
    return {
        "platforms": platforms,
        "running_jobs": [_job_to_dict(j) for j in running_jobs],
    }


@router.get("/jobs")
def list_collection_jobs(
    platform: str = None,
    status: str = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """任务历史"""
    items, total = crud.list_jobs(db, platform=platform, status=status,
                                  page=page, page_size=page_size)
    return {
        "items": [_job_to_dict(j) for j in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/jobs/{job_id}")
def get_collection_job(job_id: int, db: Session = Depends(get_db)):
    """单任务详情"""
    job = crud.get_job(db, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return _job_to_dict(job)


@router.post("/trigger")
async def trigger_full_scan(
    keyword: str = None,
    _=Depends(require_auth),
):
    """触发全量扫描"""
    manager = _get_manager()
    job = await manager.start_full_scan(keyword=keyword, triggered_by="manual")
    return {"status": "triggered", "job": _job_to_dict(job)}


@router.post("/trigger/{platform}")
async def trigger_platform_scan(
    platform: str,
    data: TriggerPlatformScan = None,
    _=Depends(require_auth),
):
    """触发单平台扫描"""
    supported = list_supported_platforms()
    if platform not in supported:
        raise HTTPException(400, f"Unsupported platform: {platform}. Available: {supported}")
    manager = _get_manager()
    keyword = data.keyword if data else None
    job = await manager.start_platform_scan(platform, keyword=keyword, triggered_by="manual")
    return {"status": "triggered", "job": _job_to_dict(job)}


@router.post("/scrape-url")
async def trigger_single_scrape(
    data: TriggerSingleScrape,
    _=Depends(require_auth),
):
    """触发单 URL 采集"""
    supported = list_supported_platforms()
    if data.platform not in supported:
        raise HTTPException(400, f"Unsupported platform: {data.platform}")
    manager = _get_manager()
    job = await manager.start_single_scrape(data.platform, data.url, triggered_by="manual")
    return {"status": "triggered", "job": _job_to_dict(job)}


@router.delete("/jobs/{job_id}")
def cancel_collection_job(
    job_id: int,
    _=Depends(require_auth),
):
    """取消运行中任务"""
    ok = CollectionManager.cancel_job(job_id)
    if not ok:
        raise HTTPException(404, "Job not found or not cancellable")
    return {"ok": True, "job_id": job_id}


@router.get("/platforms")
def list_platforms():
    """已注册平台列表"""
    platforms = list_supported_platforms()
    return {"platforms": platforms, "total": len(platforms)}
