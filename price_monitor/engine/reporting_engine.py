"""
报表引擎 — 8 大 KPI 聚合计算
"""
import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_

from price_monitor.db.models import (
    OfferSnapshot, Violation, WorkOrder
)

log = logging.getLogger("price_monitor.reporting_engine")


def generate_kpis(session: Session, start: datetime, end: datetime) -> dict:
    """
    计算指定时间范围内的所有 8 大 KPI。
    Returns a structured dict ready to be served by the API or pushed to Feishu.
    """
    # ── KPI 1: 低价发现数（按平台/SKU）
    violations_q = session.query(Violation).filter(
        Violation.created_at >= start,
        Violation.created_at <= end,
    )
    violations_total = violations_q.count()

    violations_by_platform = dict(
        session.query(Violation.platform, func.count(Violation.id))
        .filter(Violation.created_at.between(start, end))
        .group_by(Violation.platform)
        .all()
    )

    # ── KPI 2: 违规/合规比（有违规的 offer / 总 offer）
    total_offers = session.query(OfferSnapshot).filter(
        OfferSnapshot.captured_at.between(start, end)
    ).count()
    violation_rate = violations_total / total_offers if total_offers > 0 else 0

    # ── KPI 3: 工单闭环率
    wo_q = session.query(WorkOrder).filter(WorkOrder.created_at.between(start, end))
    wo_total = wo_q.count()
    wo_resolved = wo_q.filter(WorkOrder.status == "RESOLVED").count()
    workorder_close_rate = wo_resolved / wo_total if wo_total > 0 else 0

    # ── KPI 4: 平均响应时长 / SLA 达成率
    resolved_wos = session.query(WorkOrder).filter(
        WorkOrder.created_at.between(start, end),
        WorkOrder.status == "RESOLVED",
        WorkOrder.resolved_at.isnot(None),
    ).all()

    total_response_hours = 0
    sla_hit = 0
    for wo in resolved_wos:
        if wo.sla_due_at and wo.resolved_at:
            resolved_naive = wo.resolved_at.replace(tzinfo=timezone.utc) if wo.resolved_at.tzinfo is None else wo.resolved_at
            created_naive = wo.created_at.replace(tzinfo=timezone.utc) if wo.created_at.tzinfo is None else wo.created_at
            hours = (resolved_naive - created_naive).total_seconds() / 3600
            total_response_hours += hours
            sla_naive = wo.sla_due_at.replace(tzinfo=timezone.utc) if wo.sla_due_at.tzinfo is None else wo.sla_due_at
            if resolved_naive <= sla_naive:
                sla_hit += 1

    avg_response_hours = total_response_hours / len(resolved_wos) if resolved_wos else None
    sla_achievement_rate = sla_hit / len(resolved_wos) if resolved_wos else None

    # ── KPI 5: 违规高发平台/店铺 TOP 排行
    top_shops = session.query(Violation.shop_name, func.count(Violation.id).label("cnt")).filter(
        Violation.created_at.between(start, end),
        Violation.shop_name.isnot(None),
    ).group_by(Violation.shop_name).order_by(desc("cnt")).limit(10).all()

    top_platform = max(violations_by_platform, key=violations_by_platform.get) if violations_by_platform else None

    # ── KPI 6: 平均价差（gap_percent）
    avg_gap_result = session.query(func.avg(Violation.gap_percent)).filter(
        Violation.created_at.between(start, end)
    ).scalar()
    avg_gap_percent = float(avg_gap_result) if avg_gap_result else None

    # ── KPI 7: 白名单命中率
    wl_hit = session.query(Violation).filter(
        Violation.created_at.between(start, end),
        Violation.is_whitelisted == True,
    ).count()
    whitelist_hit_rate = wl_hit / violations_total if violations_total > 0 else 0

    # ── KPI 8: 复发率（reoccur_count > 0 的工单百分比）
    reoccur = wo_q.filter(WorkOrder.reoccur_count > 0).count()
    reoccur_rate = reoccur / wo_total if wo_total > 0 else 0

    # ── 时序数据（日粒度违规趋势）
    daily_trend = session.query(
        func.date(Violation.created_at).label("day"),
        func.count(Violation.id).label("count"),
    ).filter(
        Violation.created_at.between(start, end)
    ).group_by("day").order_by("day").all()

    # Severity 分布
    severity_dist = dict(
        session.query(Violation.severity, func.count(Violation.id))
        .filter(Violation.created_at.between(start, end))
        .group_by(Violation.severity)
        .all()
    )

    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "kpi1_violations_total": violations_total,
        "kpi1_violations_by_platform": violations_by_platform,
        "kpi2_total_offers": total_offers,
        "kpi2_violation_rate": round(violation_rate, 4),
        "kpi3_workorder_total": wo_total,
        "kpi3_workorder_resolved": wo_resolved,
        "kpi3_workorder_close_rate": round(workorder_close_rate, 4),
        "kpi4_avg_response_hours": round(avg_response_hours, 2) if avg_response_hours else None,
        "kpi4_sla_achievement_rate": round(sla_achievement_rate, 4) if sla_achievement_rate is not None else None,
        "kpi5_top_shops": [{"shop": s, "count": c} for s, c in top_shops],
        "kpi5_top_platform": top_platform,
        "kpi6_avg_gap_percent": round(avg_gap_percent * 100, 2) if avg_gap_percent else None,
        "kpi7_whitelist_hit_count": wl_hit,
        "kpi7_whitelist_hit_rate": round(whitelist_hit_rate, 4),
        "kpi8_reoccur_count": reoccur,
        "kpi8_reoccur_rate": round(reoccur_rate, 4),
        "severity_distribution": severity_dist,
        "daily_trend": [{"day": str(r.day), "count": r.count} for r in daily_trend],
    }


def generate_trend(session: Session, start: datetime, end: datetime, metric: str = "violations") -> list[dict]:
    """生成指定指标的日粒度时间序列"""
    if metric == "violations":
        rows = session.query(
            func.date(Violation.created_at).label("day"),
            func.count(Violation.id).label("value"),
        ).filter(Violation.created_at.between(start, end)).group_by("day").order_by("day").all()
    elif metric == "workorders":
        rows = session.query(
            func.date(WorkOrder.created_at).label("day"),
            func.count(WorkOrder.id).label("value"),
        ).filter(WorkOrder.created_at.between(start, end)).group_by("day").order_by("day").all()
    else:
        rows = []
    return [{"day": str(r.day), "value": r.value} for r in rows]


def get_top_violators(session: Session, start: datetime, end: datetime, limit: int = 10) -> list[dict]:
    """TOP 违规商家/平台排行"""
    result = session.query(
        Violation.shop_name,
        Violation.platform,
        func.count(Violation.id).label("violation_count"),
        func.avg(Violation.gap_percent).label("avg_gap"),
    ).filter(
        Violation.created_at.between(start, end),
        Violation.shop_name.isnot(None),
    ).group_by(Violation.shop_name, Violation.platform
    ).order_by(desc("violation_count")).limit(limit).all()

    return [
        {
            "shop_name": r.shop_name,
            "platform": r.platform,
            "violation_count": r.violation_count,
            "avg_gap_percent": round(float(r.avg_gap) * 100, 2) if r.avg_gap else None,
        }
        for r in result
    ]
