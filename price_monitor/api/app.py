"""
FastAPI 应用 — Antigravity 价格监测 API
"""
import os
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Optional

from price_monitor.db.session import init_db, get_db
from price_monitor.db import crud
from price_monitor.db.models import (
    OfferSnapshot, Violation, BaselinePrice,
    SearchKeyword, WhitelistRule, CookieAccount,
    ReportSchedule, O2OStockLink, ResponsibilityRule, WorkOrder
)

log = logging.getLogger(__name__)


# ── Pydantic 请求模型 ──

class BaselineCreate(BaseModel):
    product_pattern: str = Field(..., min_length=1, max_length=200)
    sku_name: Optional[str] = None
    baseline_price: float = Field(..., gt=0)
    tolerance_percent: Optional[float] = Field(None, ge=0.01, le=0.99, description="违规阈值(0.15=15%), 覆盖全局默认")
    channel: str = Field(default="ONLINE_DIRECT", pattern="^(ONLINE_DIRECT|DEALER|O2O)$")
    note: Optional[str] = None
    updated_by: Optional[str] = None

class KeywordCreate(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=100)
    priority: int = Field(default=0, ge=0, le=1)

class KeywordToggle(BaseModel):
    enabled: bool

class WhitelistCreate(BaseModel):
    rule_type: str = Field(..., pattern="^(SHOP|SKU|URL|PROJECT)$")
    match_pattern: str = Field(..., min_length=1, max_length=300)
    platform: Optional[str] = None
    reason: Optional[str] = None
    approved_by: Optional[str] = None

class CookieSave(BaseModel):
    platform: str = Field(..., min_length=1)
    account_id: str = Field(..., min_length=1)
    cookies: list

class ScheduleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    cron_expression: str = Field(..., min_length=5, max_length=100)
    report_type: str = Field(default="WEEKLY", pattern="^(DAILY|WEEKLY|MONTHLY|CUSTOM)$")
    webhook_url: str = Field(..., min_length=10, max_length=500)
    is_active: bool = True

class ScheduleUpdate(BaseModel):
    is_active: bool

class O2OStockLinkCreate(BaseModel):
    platform: str = Field(..., min_length=1, max_length=20)
    product_url: str = Field(..., min_length=10, max_length=500)
    product_name: Optional[str] = None
    city_context: Optional[dict] = None

class AttributionConfirmCreate(BaseModel):
    dealer_name: str = Field(..., min_length=1, max_length=100)
    owner_user_id: str = Field(..., min_length=1, max_length=100)
    owner_name: str = Field(..., min_length=1, max_length=100)
    platform: Optional[str] = None
    shop_name: Optional[str] = None
    ship_from_city: Optional[str] = None
    note: Optional[str] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化数据库"""
    log.info("Initializing database...")
    init_db()
    
    from price_monitor.db.session import get_session_factory
    from price_monitor.db import crud
    
    factory = get_session_factory()
    session = factory()
    try:
        count = crud.fail_stale_jobs(session)
        if count > 0:
            log.warning(f"Failed {count} stale jobs left from previous run.")
    except Exception as e:
        log.error(f"Failed to recover stale jobs: {e}")
    finally:
        session.close()
        
    log.info("Database ready.")
    yield


app = FastAPI(
    title="Antigravity 价格监测 API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — production should restrict origins via CORS_ORIGINS env var
_cors_origins = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 截图静态文件
screenshot_dir = os.getenv("SCREENSHOT_DIR", "./data/screenshots")
Path(screenshot_dir).mkdir(parents=True, exist_ok=True)
app.mount("/screenshots", StaticFiles(directory=screenshot_dir), name="screenshots")

# 采集管理路由
from price_monitor.api.collection_api import router as collection_router
app.include_router(collection_router)

# Cookie 管理路由
from price_monitor.api.cookie_api import router as cookie_router
app.include_router(cookie_router)

# 工单管理路由
from price_monitor.api.workorder_api import router as workorder_router
app.include_router(workorder_router)

# 报表路由
from price_monitor.api.reporting_api import router as reporting_router
app.include_router(reporting_router)

# 飞书双向回调路由 (A2)
from price_monitor.api.feishu_callback import router as feishu_router
app.include_router(feishu_router)

# ── 全局异常处理 ──

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


# ── 认证 (统一使用 auth.py) ──

from price_monitor.api.auth import require_auth


# ── Dashboard ──

@app.get("/api/dashboard")
def get_dashboard(db: Session = Depends(get_db)):
    stats = crud.get_dashboard_stats(db)
    return stats

# ── Global Search ──

@app.get("/api/search")
def global_search(q: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    results = []
    
    # 1. Search Keywords
    keywords = db.query(SearchKeyword).filter(SearchKeyword.keyword.ilike(f"%{q}%")).limit(5).all()
    for k in keywords:
        results.append({
            "type": "关键词", "title": k.keyword,
            "description": f"优先级: {'高' if k.priority else '普通'} | 状态: {'启用' if k.enabled else '禁用'}",
            "url": "/keywords"
        })
        
    # 2. Search Violations
    violations = db.query(Violation).filter(
        (Violation.product_name.ilike(f"%{q}%")) | (Violation.shop_name.ilike(f"%{q}%"))
    ).order_by(Violation.created_at.desc()).limit(10).all()
    for v in violations:
        results.append({
            "type": "违规记录", "title": v.product_name or "未知商品",
            "description": f"店铺: {v.shop_name} | 平台: {v.platform} | 价格: ¥{v.final_price}",
            "url": "/violations"
        })
        
    # 3. Search Offers (if not already matched heavily by violations)
    if len(results) < 15:
        offers = db.query(OfferSnapshot).filter(
            (OfferSnapshot.product_name.ilike(f"%{q}%")) | (OfferSnapshot.shop_name.ilike(f"%{q}%"))
        ).order_by(OfferSnapshot.created_at.desc()).limit(10).all()
        for o in offers:
            results.append({
                "type": "采集数据", "title": o.product_name or "未知商品",
                "description": f"店铺: {o.shop_name} | 平台: {o.platform} | 价格: ¥{o.final_price}",
                "url": "/offers"
            })
            
    # Deduplicate slightly by title if needed, or just return top 20
    return {"items": results[:20]}


# ── Offers ──

@app.get("/api/offers/trend")
def get_offers_trend(
    keyword: str = None,
    platform: str = None,
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
):
    """GET 价格趋势数据（按天聚合）"""
    data = crud.get_price_trend(db, keyword=keyword, platform=platform, days=days)
    return {"trend": data, "days": days, "keyword": keyword, "platform": platform}


@app.get("/api/offers")
def list_offers(
    platform: str = None,
    keyword: str = None,
    shop_name: str = None,
    city: str = None,
    sort_by: str = Query("time_desc", pattern="^(time_desc|price_asc|price_desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    items, total = crud.list_offers(
        db, platform=platform, keyword=keyword,
        shop_name=shop_name, city=city,
        sort_by=sort_by,
        page=page, page_size=page_size,
    )
    return {
        "items": [_offer_to_dict(o) for o in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@app.get("/api/offers/{offer_id}")
def get_offer(offer_id: int, db: Session = Depends(get_db)):
    offer = db.query(OfferSnapshot).filter(OfferSnapshot.id == offer_id).first()
    if not offer:
        raise HTTPException(404, "Offer not found")
    return _offer_to_dict(offer)


# ── Violations ──

@app.get("/api/violations")
def list_violations(
    platform: str = None,
    severity: str = None,
    is_whitelisted: bool = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    items, total = crud.list_violations(
        db, platform=platform, severity=severity,
        is_whitelisted=is_whitelisted,
        page=page, page_size=page_size,
    )
    return {
        "items": [_violation_to_dict(v) for v in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@app.get("/api/violations/{violation_id}")
def get_violation(violation_id: int, db: Session = Depends(get_db)):
    v = crud.get_violation_detail(db, violation_id)
    if not v:
        raise HTTPException(404, "Violation not found")
    return _violation_to_dict(v)


# ── Baselines ──

@app.get("/api/baselines")
def list_baselines(db: Session = Depends(get_db)):
    items = crud.get_baselines(db)
    return {"items": [_baseline_to_dict(b) for b in items]}


@app.post("/api/baselines")
def create_baseline(data: BaselineCreate, request: Request = None, db: Session = Depends(get_db), _=Depends(require_auth)):
    bp = crud.upsert_baseline(db, data.model_dump(exclude_none=True))
    db.commit()
    return _baseline_to_dict(bp)


@app.delete("/api/baselines/{baseline_id}")
def delete_baseline(baseline_id: int, db: Session = Depends(get_db), _=Depends(require_auth)):
    ok = crud.delete_baseline(db, baseline_id)
    if not ok:
        raise HTTPException(404, "Baseline not found")
    db.commit()
    return {"ok": True}


@app.get("/api/baselines/{baseline_id}/history")
def get_baseline_history_api(baseline_id: int, db: Session = Depends(get_db)):
    """GET 基准价变更历史"""
    bp = db.query(BaselinePrice).filter(BaselinePrice.id == baseline_id).first()
    if not bp:
        raise HTTPException(404, "Baseline not found")
    return {"baseline_id": baseline_id, "history": crud.get_baseline_history(db, baseline_id)}


# ── Keywords ──

@app.get("/api/keywords")
def list_keywords(db: Session = Depends(get_db)):
    items = db.query(SearchKeyword).order_by(SearchKeyword.id).all()
    return {"items": [_keyword_to_dict(k) for k in items]}


@app.post("/api/keywords")
def add_keyword(data: KeywordCreate, db: Session = Depends(get_db), _=Depends(require_auth)):
    kw = crud.add_keyword(db, data.keyword.strip(), data.priority)
    db.commit()
    return _keyword_to_dict(kw)


@app.put("/api/keywords/{keyword_id}")
def toggle_keyword(keyword_id: int, data: KeywordToggle, db: Session = Depends(get_db), _=Depends(require_auth)):
    ok = crud.toggle_keyword(db, keyword_id, data.enabled)
    if not ok:
        raise HTTPException(404, "Keyword not found")
    db.commit()
    return {"ok": True}


@app.delete("/api/keywords/{keyword_id}")
def delete_keyword(keyword_id: int, db: Session = Depends(get_db), _=Depends(require_auth)):
    kw = db.query(SearchKeyword).filter(SearchKeyword.id == keyword_id).first()
    if not kw:
        raise HTTPException(404, "Keyword not found")
    db.delete(kw)
    db.commit()
    return {"ok": True}


@app.post("/api/keywords/batch")
def batch_add_keywords(data: dict, db: Session = Depends(get_db), _=Depends(require_auth)):
    """Batch import keywords from a list of strings."""
    keywords = data.get("keywords", [])
    if not isinstance(keywords, list) or len(keywords) == 0:
        raise HTTPException(400, "keywords must be a non-empty list")
    added = 0
    for kw_str in keywords[:500]:  # cap at 500
        kw_str = str(kw_str).strip()
        if not kw_str or len(kw_str) > 100:
            continue
        existing = db.query(SearchKeyword).filter(SearchKeyword.keyword == kw_str).first()
        if existing:
            continue
        crud.add_keyword(db, kw_str, 0)
        added += 1
    db.commit()
    return {"added": added, "total": db.query(SearchKeyword).count()}


@app.get("/api/keywords/export")
def export_keywords(db: Session = Depends(get_db)):
    """Export all keywords as CSV."""
    from fastapi.responses import StreamingResponse
    import io
    items = db.query(SearchKeyword).order_by(SearchKeyword.id).all()
    output = io.StringIO()
    output.write("keyword,priority,enabled\n")
    for k in items:
        output.write(f"{k.keyword},{k.priority},{k.enabled}\n")
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=keywords.csv"}
    )


# ── Whitelist ──

@app.get("/api/whitelist")
def list_whitelist(db: Session = Depends(get_db)):
    items = db.query(WhitelistRule).order_by(WhitelistRule.id.desc()).all()
    return {"items": [_whitelist_to_dict(w) for w in items]}


@app.post("/api/whitelist")
def create_whitelist(data: WhitelistCreate, db: Session = Depends(get_db), _=Depends(require_auth)):
    rule = crud.create_whitelist(db, data.model_dump(exclude_none=True))
    db.commit()
    return _whitelist_to_dict(rule)


@app.delete("/api/whitelist/{rule_id}")
def revoke_whitelist(rule_id: int, db: Session = Depends(get_db), _=Depends(require_auth)):
    rule = db.query(WhitelistRule).filter(WhitelistRule.id == rule_id).first()
    if not rule:
        raise HTTPException(404, "Whitelist rule not found")
    rule.status = "REVOKED"
    db.commit()
    return {"ok": True}


@app.post("/api/whitelist/batch-approve")
def batch_approve_whitelist(data: dict, db: Session = Depends(get_db), _=Depends(require_auth)):
    ids = data.get("ids", [])
    if not isinstance(ids, list) or not ids:
        raise HTTPException(400, "ids must be a non-empty list")
    
    rules = db.query(WhitelistRule).filter(WhitelistRule.id.in_(ids)).all()
    count = 0
    for r in rules:
        if r.status != "ACTIVE":
            r.status = "ACTIVE"
            count += 1
    db.commit()
    return {"updated": count}


@app.post("/api/whitelist/batch-revoke")
def batch_revoke_whitelist(data: dict, db: Session = Depends(get_db), _=Depends(require_auth)):
    ids = data.get("ids", [])
    reason = data.get("reason")
    if not isinstance(ids, list) or not ids:
        raise HTTPException(400, "ids must be a non-empty list")
    
    rules = db.query(WhitelistRule).filter(WhitelistRule.id.in_(ids)).all()
    count = 0
    for r in rules:
        if r.status != "REVOKED":
            r.status = "REVOKED"
            if reason:
                r.reason = reason
            count += 1
    db.commit()
    return {"updated": count}


# ── Cookies ──

@app.get("/api/cookies")
def list_cookies(db: Session = Depends(get_db)):
    items = db.query(CookieAccount).order_by(CookieAccount.id).all()
    return {"items": [_cookie_to_dict(c) for c in items]}


@app.post("/api/cookies")
def save_cookies(data: CookieSave, db: Session = Depends(get_db), _=Depends(require_auth)):
    ca = crud.save_cookies(db, data.platform, data.account_id, data.cookies)
    db.commit()
    return _cookie_to_dict(ca)


# ── Export ──

EXPORT_MAX_ROWS = int(os.getenv("EXPORT_MAX_ROWS", "50000"))


@app.get("/api/export/violations")
def export_violations(
    platform: str = None,
    severity: str = None,
    page_size: int = Query(5000, ge=1, le=50000),
    db: Session = Depends(get_db),
):
    """导出违规数据为 JSON (Excel 导出在前端处理)"""
    capped_size = min(page_size, EXPORT_MAX_ROWS)
    items, total = crud.list_violations(
        db, platform=platform, severity=severity,
        page=1, page_size=capped_size,
    )
    return {
        "items": [_violation_to_dict(v) for v in items],
        "total": total,
        "exported": len(items),
        "capped": len(items) < total,
    }


# ── 采集健康统计 ──

@app.get("/api/collection/health-stats")
def get_collection_health(
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db),
):
    """GET 采集健康指标（成功率/失败原因分布）"""
    return crud.get_collection_health_stats(db, hours=hours)


# ── 手动触发采集 (委托给 CollectionManager) ──

@app.post("/api/scan/trigger")
async def trigger_scan(_=Depends(require_auth)):
    """手动触发一轮采集 — 委托给 /api/collection/trigger"""
    from price_monitor.api.collection_api import _get_manager
    manager = _get_manager()
    job = await manager.start_full_scan(triggered_by="manual")
    return {"status": "triggered", "job_id": job.id}


# ── 序列化工具 ──

def _offer_to_dict(o: OfferSnapshot) -> dict:
    return {
        "id": o.id,
        "platform": o.platform,
        "keyword": o.keyword,
        "canonical_url": o.canonical_url,
        "product_name": o.product_name,
        "product_id": o.product_id,
        "shop_name": o.shop_name,
        "ship_from_city": o.ship_from_city,
        "raw_price": float(o.raw_price or 0),
        "final_price": float(o.final_price or 0),
        "original_price": float(o.original_price or 0),
        "coupon_info": o.coupon_info,
        "confidence": o.confidence,
        "sales_volume": o.sales_volume,
        "screenshot_path": o.screenshot_path,
        "screenshot_hash": o.screenshot_hash,
        "parse_status": o.parse_status,
        "captured_at": o.captured_at.isoformat() + "Z" if o.captured_at else None,
        "created_at": o.created_at.isoformat() + "Z" if o.created_at else None,
    }


def _violation_to_dict(v: Violation) -> dict:
    return {
        "id": v.id,
        "offer_id": v.offer_id,
        "product_name": v.product_name,
        "platform": v.platform,
        "baseline_price": float(v.baseline_price or 0),
        "final_price": float(v.final_price or 0),
        "gap_value": float(v.gap_value or 0),
        "gap_percent": float(v.gap_percent or 0),
        "severity": v.severity,
        "is_whitelisted": v.is_whitelisted,
        "shop_name": v.shop_name,
        "ship_from_city": v.ship_from_city,
        "screenshot_path": v.screenshot_path,
        "canonical_url": v.canonical_url,
        "notified": v.notified,
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }


def _baseline_to_dict(b: BaselinePrice) -> dict:
    return {
        "id": b.id,
        "product_pattern": b.product_pattern,
        "sku_name": b.sku_name,
        "baseline_price": float(b.baseline_price or 0),
        "note": b.note,
        "updated_by": b.updated_by,
        "updated_at": b.updated_at.isoformat() + "Z" if b.updated_at else None,
    }


def _keyword_to_dict(k: SearchKeyword) -> dict:
    return {
        "id": k.id,
        "keyword": k.keyword,
        "enabled": k.enabled,
        "priority": k.priority,
        "created_at": k.created_at.isoformat() + "Z" if k.created_at else None,
    }


def _whitelist_to_dict(w: WhitelistRule) -> dict:
    return {
        "id": w.id,
        "rule_type": w.rule_type,
        "match_pattern": w.match_pattern,
        "platform": w.platform,
        "reason": w.reason,
        "approved_by": w.approved_by,
        "expires_at": w.expires_at.isoformat() + "Z" if w.expires_at else None,
        "status": w.status,
        "created_at": w.created_at.isoformat() + "Z" if w.created_at else None,
    }


def _cookie_to_dict(c: CookieAccount) -> dict:
    return {
        "id": c.id,
        "platform": c.platform,
        "account_id": c.account_id,
        "status": c.status,
        "cookie_count": len(c.cookies) if isinstance(c.cookies, list) else 0,
        "last_used": c.last_used.isoformat() + "Z" if c.last_used else None,
        "expired_at": c.expired_at.isoformat() + "Z" if c.expired_at else None,
        "created_at": c.created_at.isoformat() + "Z" if c.created_at else None,
    }


def _schedule_to_dict(s: ReportSchedule) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "cron_expression": s.cron_expression,
        "report_type": s.report_type,
        "webhook_url": s.webhook_url,
        "is_active": s.is_active,
        "created_at": s.created_at.isoformat() + "Z" if s.created_at else None,
        "updated_at": s.updated_at.isoformat() + "Z" if s.updated_at else None,
    }

def _o2o_link_to_dict(link: O2OStockLink) -> dict:
    return {
        "id": link.id,
        "platform": link.platform,
        "product_url": link.product_url,
        "product_name": link.product_name,
        "city_context": link.city_context,
        "is_active": link.is_active,
    }


# ── Schedules ──

@app.get("/api/schedules")
def list_schedules(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    items, total = crud.list_report_schedules(db, page=page, page_size=page_size)
    return {
        "items": [_schedule_to_dict(i) for i in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }

@app.post("/api/schedules")
def create_schedule(data: ScheduleCreate, db: Session = Depends(get_db), _=Depends(require_auth)):
    s = crud.create_report_schedule(db, data.model_dump())
    db.commit()
    return _schedule_to_dict(s)

@app.put("/api/schedules/{schedule_id}")
def update_schedule(schedule_id: int, data: ScheduleUpdate, db: Session = Depends(get_db), _=Depends(require_auth)):
    success = crud.toggle_report_schedule(db, schedule_id, data.is_active)
    if not success:
        raise HTTPException(status_code=404, detail="Schedule not found")
    db.commit()
    return {"status": "ok"}

@app.delete("/api/schedules/{schedule_id}")
def delete_schedule(schedule_id: int, db: Session = Depends(get_db), _=Depends(require_auth)):
    success = crud.delete_report_schedule(db, schedule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Schedule not found")
    db.commit()
    return {"status": "ok"}


# ── O2O Stock Links ──

@app.get("/api/o2o/links")
def list_o2o_links(platform: Optional[str] = None, db: Session = Depends(get_db), _=Depends(require_auth)):
    links = crud.list_active_o2o_links(db, platform=platform)
    return {"items": [_o2o_link_to_dict(link) for link in links]}

@app.post("/api/o2o/links")
def create_o2o_link(data: O2OStockLinkCreate, db: Session = Depends(get_db), _=Depends(require_auth)):
    link = crud.create_o2o_link(db, data.model_dump())
    db.commit()
    return _o2o_link_to_dict(link)

@app.delete("/api/o2o/links/{link_id}")
def delete_o2o_link(link_id: int, db: Session = Depends(get_db), _=Depends(require_auth)):
    if crud.delete_o2o_link(db, link_id):
        db.commit()
        return {"status": "ok"}
    raise HTTPException(status_code=404, detail="O2O link not found")


# ── Attribution & WorkOrders ──

@app.post("/api/workorders/{wo_id}/confirm-attribution")
def confirm_attribution(wo_id: int, data: AttributionConfirmCreate, db: Session = Depends(get_db), _=Depends(require_auth)):
    wo = db.query(WorkOrder).filter_by(id=wo_id).first()
    if not wo:
        raise HTTPException(status_code=404, detail="WorkOrder not found")
    
    # 1. Backwrite mapping to knowledge base (ResponsibilityRule)
    req = data.model_dump()
    db_data = {
        "platform": req.get("platform") or wo.platform,
        "shop_name_pattern": req.get("shop_name", "").strip() or None,
        "ship_from_city": req.get("ship_from_city", "").strip() or None,
        "dealer_name": req.get("dealer_name"),
        "owner_user_id": req.get("owner_user_id"),
        "owner_name": req.get("owner_name"),
        "priority": 100,  # Manual confirmations gain high priority
        "note": req.get("note", f"Manually confirmed from WO #{wo.id}")
    }
    crud.create_responsibility_rule(db, db_data)

    # 2. Update the WO itself and insert action log
    from price_monitor.engine.workorder_engine import append_action
    wo.owner_user_id = db_data["owner_user_id"]
    wo.owner_name = db_data["owner_name"]
    wo.dealer_name = db_data["dealer_name"]
    if wo.status == "OPEN":
        wo.status = "IN_PROGRESS"
    
    append_action(
        session=db,
        wo_id=wo_id,
        action_type="CONFIRM_ATTRIBUTION",
        note=f"Confirmed dealer: {db_data['dealer_name']} ({db_data['owner_name']})",
        operator="user"
    )

    db.commit()
    return {"status": "ok", "message": "Attribution confirmed and rule created"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("price_monitor.api.app:app", host="0.0.0.0", port=8000, reload=True)
