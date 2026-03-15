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
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Optional

from price_monitor.db.session import init_db, get_db, get_session_factory
from price_monitor.db import crud
from price_monitor.db.models import (
    OfferSnapshot, Violation, BaselinePrice,
    SearchKeyword, WhitelistRule, CookieAccount,
)

log = logging.getLogger(__name__)

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "kashi2026")


# ── Pydantic 请求模型 ──

class BaselineCreate(BaseModel):
    product_pattern: str = Field(..., min_length=1, max_length=200)
    sku_name: Optional[str] = None
    baseline_price: float = Field(..., gt=0)
    note: Optional[str] = None

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化数据库"""
    log.info("Initializing database...")
    init_db()
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


# ── 全局异常处理 ──

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


# ── 认证 ──

def verify_auth(request: Request):
    """密码认证 — 写入操作强制校验"""
    auth = request.headers.get("Authorization", "")
    token = request.query_params.get("token", "")
    if auth == f"Bearer {ADMIN_PASSWORD}" or token == ADMIN_PASSWORD:
        return True
    return False


def require_auth(request: Request):
    """写入端点的认证依赖 — 校验失败返回 401"""
    if not verify_auth(request):
        raise HTTPException(401, "Authentication required")


# ── Dashboard ──

@app.get("/api/dashboard")
def get_dashboard(db: Session = Depends(get_db)):
    stats = crud.get_dashboard_stats(db)
    return stats


# ── Offers ──

@app.get("/api/offers")
def list_offers(
    platform: str = None,
    keyword: str = None,
    shop_name: str = None,
    city: str = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    items, total = crud.list_offers(
        db, platform=platform, keyword=keyword,
        shop_name=shop_name, city=city,
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


# ── 手动触发采集 (可选) ──

@app.post("/api/scan/trigger")
async def trigger_scan(request: Request = None, _=Depends(require_auth)):
    """手动触发一轮采集"""
    import asyncio
    import threading
    from price_monitor.scheduler import run_scan_round
    # 在后台线程中运行, 避免 uvicorn event loop 冲突
    thread = threading.Thread(
        target=lambda: asyncio.run(run_scan_round()),
        daemon=True,
    )
    thread.start()
    return {"status": "triggered"}


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
        "captured_at": o.captured_at.isoformat() if o.captured_at else None,
        "created_at": o.created_at.isoformat() if o.created_at else None,
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
        "updated_at": b.updated_at.isoformat() if b.updated_at else None,
    }


def _keyword_to_dict(k: SearchKeyword) -> dict:
    return {
        "id": k.id,
        "keyword": k.keyword,
        "enabled": k.enabled,
        "priority": k.priority,
        "created_at": k.created_at.isoformat() if k.created_at else None,
    }


def _whitelist_to_dict(w: WhitelistRule) -> dict:
    return {
        "id": w.id,
        "rule_type": w.rule_type,
        "match_pattern": w.match_pattern,
        "platform": w.platform,
        "reason": w.reason,
        "approved_by": w.approved_by,
        "expires_at": w.expires_at.isoformat() if w.expires_at else None,
        "status": w.status,
        "created_at": w.created_at.isoformat() if w.created_at else None,
    }


def _cookie_to_dict(c: CookieAccount) -> dict:
    return {
        "id": c.id,
        "platform": c.platform,
        "account_id": c.account_id,
        "status": c.status,
        "cookie_count": len(c.cookies) if isinstance(c.cookies, list) else 0,
        "last_used": c.last_used.isoformat() if c.last_used else None,
        "expired_at": c.expired_at.isoformat() if c.expired_at else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }
