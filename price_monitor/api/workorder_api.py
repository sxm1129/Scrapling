"""
WorkOrder & 责任规则 API
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from price_monitor.db.session import get_session_factory
from price_monitor.db import crud
from price_monitor.engine.workorder_engine import (
    append_action, resolve_workorder, check_sla_escalations
)
from price_monitor.notify import feishu as feishu_notify

router = APIRouter(prefix="/api/v1")

def get_db():
    factory = get_session_factory()
    db = factory()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ─── Pydantic Schemas ───

class WorkOrderUpdateBody(BaseModel):
    status: Optional[str] = None
    note: Optional[str] = None
    owner_user_id: Optional[str] = None
    owner_name: Optional[str] = None

class WorkOrderActionBody(BaseModel):
    action_type: str
    note: str
    operator: Optional[str] = "user"
    attachment_evidence_id: Optional[int] = None

class WorkOrderResolveBody(BaseModel):
    note: str
    resolution_type: Optional[str] = "OTHER"
    operator: Optional[str] = "user"

class ResponsibilityRuleCreate(BaseModel):
    platform: Optional[str] = None
    shop_name_pattern: Optional[str] = None
    ship_from_city: Optional[str] = None
    dealer_name: str
    owner_user_id: str
    owner_name: str
    owner_feishu_id: Optional[str] = None
    priority: int = 0
    note: Optional[str] = None


# ─── WorkOrder Endpoints ───

def _wo_to_dict(wo) -> dict:
    # Use naive UTC for SLA comparison: MySQL DATETIME columns store naive UTC
    now_utc = datetime.utcnow()
    return {
        "id": wo.id,
        "violation_id": wo.violation_id,
        "owner_user_id": wo.owner_user_id,
        "owner_name": wo.owner_name,
        "dealer_name": wo.dealer_name,
        "status": wo.status,
        "severity": wo.severity,
        "platform": wo.platform,
        "product_name": wo.product_name,
        "violation_price": float(wo.violation_price) if wo.violation_price else None,
        "baseline_price": float(wo.baseline_price) if wo.baseline_price else None,
        "gap_percent": float(wo.gap_percent) if wo.gap_percent else None,
        "canonical_url": wo.canonical_url,
        "screenshot_path": wo.screenshot_path,
        "escalation_level": wo.escalation_level,
        "reoccur_count": wo.reoccur_count,
        "action_log": wo.action_log or [],
        "sla_due_at": wo.sla_due_at.isoformat() if wo.sla_due_at else None,
        "sla_overdue": (
            wo.sla_due_at is not None
            and wo.sla_due_at < now_utc  # both naive UTC
            and wo.status in ("OPEN", "IN_PROGRESS")
        ),
        "resolved_at": wo.resolved_at.isoformat() if wo.resolved_at else None,
        "resolution_note": wo.resolution_note,
        "resolution_type": wo.resolution_type,
        "created_at": wo.created_at.isoformat() if wo.created_at else None,
        "updated_at": wo.updated_at.isoformat() if wo.updated_at else None,
    }


@router.get("/workorders")
def list_workorders(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    owner_user_id: Optional[str] = None,
    platform: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    items, total = crud.list_workorders(
        db, status=status, severity=severity,
        owner_user_id=owner_user_id, platform=platform,
        page=page, page_size=page_size,
    )
    return {"workorders": [_wo_to_dict(w) for w in items], "total": total, "page": page, "page_size": page_size}


@router.get("/workorders/{wo_id}")
def get_workorder(wo_id: int, db: Session = Depends(get_db)):
    wo = crud.get_workorder(db, wo_id)
    if not wo:
        raise HTTPException(status_code=404, detail="WorkOrder not found")
    return _wo_to_dict(wo)


@router.patch("/workorders/{wo_id}")
def update_workorder(wo_id: int, body: WorkOrderUpdateBody, db: Session = Depends(get_db)):
    # Filter out None values but keep explicit status/owner updates
    updates = {k: v for k, v in body.model_dump().items() if v is not None and k != "note"}
    wo = crud.update_workorder(db, wo_id, updates)
    if not wo:
        raise HTTPException(status_code=404, detail="WorkOrder not found")
    if body.note:
        append_action(db, wo_id, "STATUS_UPDATE", body.note, "user")
    db.commit()
    return _wo_to_dict(wo)


@router.post("/workorders/{wo_id}/actions")
def add_action(wo_id: int, body: WorkOrderActionBody, db: Session = Depends(get_db)):
    wo = append_action(db, wo_id, body.action_type, body.note, body.operator or "user", body.attachment_evidence_id)
    if not wo:
        raise HTTPException(status_code=404, detail="WorkOrder not found")
    db.commit()
    return {"status": "ok", "action_count": len(wo.action_log or [])}


@router.post("/workorders/{wo_id}/resolve")
def resolve_wo(wo_id: int, body: WorkOrderResolveBody, db: Session = Depends(get_db)):
    wo = resolve_workorder(db, wo_id, body.note, body.resolution_type or "OTHER", body.operator or "user")
    if not wo:
        raise HTTPException(status_code=404, detail="WorkOrder not found")
    db.commit()
    return {"status": "RESOLVED", "wo_id": wo_id}


# ─── Responsibility Rules ───

@router.get("/responsibility-rules")
def list_rules(platform: Optional[str] = None, db: Session = Depends(get_db)):
    rules = crud.list_responsibility_rules(db, platform=platform)
    return [
        {
            "id": r.id, "platform": r.platform, "shop_name_pattern": r.shop_name_pattern,
            "ship_from_city": r.ship_from_city, "dealer_name": r.dealer_name,
            "owner_user_id": r.owner_user_id, "owner_name": r.owner_name,
            "owner_feishu_id": r.owner_feishu_id, "priority": r.priority,
            "is_active": r.is_active, "note": r.note,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rules
    ]


@router.post("/responsibility-rules")
def create_rule(body: ResponsibilityRuleCreate, db: Session = Depends(get_db)):
    rule = crud.create_responsibility_rule(db, body.model_dump())
    db.commit()
    return {"id": rule.id, "status": "created"}


@router.delete("/responsibility-rules/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    ok = crud.delete_responsibility_rule(db, rule_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.commit()
    return {"status": "deactivated"}
