"""
Reporting API — KPI、趋势、TOP排行、周报生成
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from price_monitor.db.session import get_session_factory
from price_monitor.db import crud
from price_monitor.engine import reporting_engine

router = APIRouter(prefix="/v1/reports")


def get_db():
    factory = get_session_factory()
    db = factory()
    try:
        yield db
    finally:
        db.close()


def _parse_dates(start_str: Optional[str], end_str: Optional[str], default_days: int = 7):
    now = datetime.now(timezone.utc)
    end = datetime.fromisoformat(end_str) if end_str else now
    start = datetime.fromisoformat(start_str) if start_str else now - timedelta(days=default_days)
    return start, end


# ─── GET KPIs ───

@router.get("/kpi")
def get_kpis(
    start: Optional[str] = Query(None, description="ISO datetime"),
    end: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    s, e = _parse_dates(start, end)
    return reporting_engine.generate_kpis(db, s, e)


# ─── GET Trends ───

@router.get("/trends")
def get_trends(
    metric: str = Query("violations", enum=["violations", "workorders"]),
    start: Optional[str] = None,
    end: Optional[str] = None,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    s, e = _parse_dates(start, end, default_days=days)
    return {"metric": metric, "data": reporting_engine.generate_trend(db, s, e, metric)}


# ─── GET Top Violators ───

@router.get("/top-violators")
def get_top_violators(
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    s, e = _parse_dates(start, end)
    return {"violators": reporting_engine.get_top_violators(db, s, e, limit)}


# ─── POST Generate Report ───

class GenerateReportBody(BaseModel):
    start: str
    end: str
    report_type: str = "CUSTOM"
    feishu_webhook_url: Optional[str] = None
    push_to_feishu: bool = False


@router.post("/generate")
def generate_report(body: GenerateReportBody, db: Session = Depends(get_db)):
    start = datetime.fromisoformat(body.start)
    end = datetime.fromisoformat(body.end)

    # Create report record
    report_data = {
        "report_type": body.report_type,
        "start_date": start,
        "end_date": end,
        "feishu_webhook_url": body.feishu_webhook_url,
        "triggered_by": "api",
        "status": "PENDING",
    }
    report = crud.create_periodic_report(db, report_data)
    db.commit()

    # Generate KPIs
    try:
        kpis = reporting_engine.generate_kpis(db, start, end)
        crud.update_periodic_report(db, report.id, {"status": "DONE", "kpi_snapshot": kpis})
        db.commit()

        # Optionally push to Feishu
        if body.push_to_feishu and body.feishu_webhook_url:
            from price_monitor.notify import feishu as feishu_notify
            feishu_notify.send_report_ready(
                report={"id": report.id, "start_date": start, "end_date": end},
                kpis=kpis,
                webhook_url=body.feishu_webhook_url,
            )
            crud.update_periodic_report(db, report.id, {"pushed_at": datetime.now(timezone.utc)})
            db.commit()

        return {"report_id": report.id, "status": "DONE", "kpis": kpis}

    except Exception as e:
        crud.update_periodic_report(db, report.id, {"status": "FAILED"})
        db.commit()
        raise HTTPException(status_code=500, detail=str(e))


# ─── GET Report History ───

@router.get("")
def list_reports(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    items, total = crud.list_periodic_reports(db, page, page_size)
    return {
        "total": total,
        "reports": [
            {
                "id": r.id,
                "report_type": r.report_type,
                "start_date": r.start_date.isoformat(),
                "end_date": r.end_date.isoformat(),
                "status": r.status,
                "pushed_at": r.pushed_at.isoformat() if r.pushed_at else None,
                "triggered_by": r.triggered_by,
                "created_at": r.created_at.isoformat(),
            }
            for r in items
        ],
    }


# ─── GET Report Detail ───

@router.get("/{report_id}")
def get_report(report_id: int, db: Session = Depends(get_db)):
    reports, _ = crud.list_periodic_reports(db, page=1, page_size=1)
    report = db.query(crud.PeriodicReport).filter(crud.PeriodicReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return {
        "id": report.id,
        "report_type": report.report_type,
        "start_date": report.start_date.isoformat(),
        "end_date": report.end_date.isoformat(),
        "status": report.status,
        "kpi_snapshot": report.kpi_snapshot,
        "pushed_at": report.pushed_at.isoformat() if report.pushed_at else None,
    }
