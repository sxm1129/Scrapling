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
from price_monitor.db.models import PeriodicReport
from price_monitor.engine import reporting_engine

router = APIRouter(prefix="/api/v1/reports")


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


def _parse_dates(start_dt: Optional[datetime], end_dt: Optional[datetime], default_days: int = 7):
    now = datetime.utcnow()  # Naive UTC for MySQL DATETIME comparisons
    end = end_dt.replace(tzinfo=None) if end_dt else now
    start = start_dt.replace(tzinfo=None) if start_dt else now - timedelta(days=default_days)
    return start, end


# ─── GET KPIs ───

@router.get("/kpi")
def get_kpis(
    start: Optional[datetime] = Query(None, description="ISO datetime"),
    end: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
):
    s, e = _parse_dates(start, end)
    return reporting_engine.generate_kpis(db, s, e)


# ─── GET Trends ───

@router.get("/trends")
def get_trends(
    metric: str = Query("violations", enum=["violations", "workorders"]),
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    s, e = _parse_dates(start, end, default_days=days)
    return {"metric": metric, "data": reporting_engine.generate_trend(db, s, e, metric)}


# ─── GET Top Violators ───

@router.get("/top-violators")
def get_top_violators(
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    s, e = _parse_dates(start, end)
    return {"violators": reporting_engine.get_top_violators(db, s, e, limit)}


# ─── POST Generate Report ───

class GenerateReportBody(BaseModel):
    start: datetime
    end: datetime
    report_type: str = "CUSTOM"
    feishu_webhook_url: Optional[str] = None
    push_to_feishu: bool = False


@router.post("/generate")
def generate_report(body: GenerateReportBody, db: Session = Depends(get_db)):
    start = body.start.replace(tzinfo=None)
    end = body.end.replace(tzinfo=None)

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
            crud.update_periodic_report(db, report.id, {"pushed_at": datetime.utcnow()})
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
    report = db.query(PeriodicReport).filter(PeriodicReport.id == report_id).first()
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
