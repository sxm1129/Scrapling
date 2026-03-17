"""
WorkOrder 工单引擎
- 责任归因匹配（店铺/城市 → 经销商 → 责任人）
- 工单自动创建（Violation → WorkOrder）
- SLA 超时升级检测
- 工单关闭/复核触发
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy.orm import Session

from price_monitor.db import crud
from price_monitor.db.models import Violation, WorkOrder, ResponsibilityRule

log = logging.getLogger("price_monitor.workorder_engine")

# SLA 配置（小时）
SLA_HOURS = {
    "P0": 2,
    "P1": 48,
    "P2": 120,
}


def match_responsibility(
    session: Session,
    platform: str,
    shop_name: str,
    ship_from_city: str,
) -> Optional[ResponsibilityRule]:
    """
    按优先级匹配责任规则：
    1. platform + shop_name_pattern + city (最精准)
    2. platform + shop_name_pattern
    3. platform + city
    4. 任意规则兜底（city 或 shop）
    返回最高优先级匹配的规则，否则返回 None
    """
    rules = crud.list_responsibility_rules(session, platform=platform, active_only=True)
    best: Optional[ResponsibilityRule] = None
    best_score = -1

    for rule in rules:
        score = 0
        # 平台匹配
        if rule.platform and rule.platform != platform:
            continue
        if rule.platform == platform:
            score += 4

        # 店铺名匹配
        if rule.shop_name_pattern and shop_name:
            keywords = rule.shop_name_pattern.lower().split()
            if all(kw in shop_name.lower() for kw in keywords):
                score += 2
            else:
                continue  # 有 pattern 但不匹配 → 跳过

        # 城市匹配
        if rule.ship_from_city and ship_from_city:
            if rule.ship_from_city == ship_from_city:
                score += 1
            else:
                continue  # 有城市约束但不匹配 → 跳过

        # 用优先级加权
        score += rule.priority * 10

        if score > best_score:
            best_score = score
            best = rule

    return best


def create_workorder_from_violation(
    session: Session,
    violation: Violation,
    offer_data: dict,
) -> WorkOrder:
    """
    从一条违规判定中自动创建工单:
    1. 匹配责任人
    2. 计算 SLA 截止时间
    3. 持久化工单
    """
    shop_name = offer_data.get("shop_name", "")
    ship_city = offer_data.get("ship_from_city", "")
    platform = violation.platform or ""

    rule = match_responsibility(session, platform, shop_name, ship_city)

    sla_hours = SLA_HOURS.get(violation.severity, 48)
    sla_due = datetime.utcnow() + timedelta(hours=sla_hours)  # Naive UTC for MySQL DATETIME

    wo_data = {
        "violation_id": violation.id,
        "owner_user_id": rule.owner_user_id if rule else None,
        "owner_name": rule.owner_name if rule else "未分配",
        "dealer_name": rule.dealer_name if rule else None,
        "status": "OPEN",
        "severity": violation.severity or "P1",
        "platform": platform,
        "product_name": violation.product_name,
        "violation_price": violation.final_price,
        "baseline_price": violation.baseline_price,
        "gap_percent": violation.gap_percent,
        "canonical_url": violation.canonical_url,
        "screenshot_path": violation.screenshot_path,
        "sla_due_at": sla_due,
        "action_log": [{
            "type": "CREATED",
            "at": datetime.now(timezone.utc).isoformat(),
            "note": f"系统自动创建，已指派责任人: {rule.owner_name if rule else '待认领'}",
        }],
    }

    wo = crud.create_workorder(session, wo_data)
    log.info(f"WorkOrder #{wo.id} created for violation #{violation.id} ({violation.severity}), owner: {wo.owner_name}")
    return wo


def append_action(
    session: Session,
    wo_id: int,
    action_type: str,
    note: str,
    operator: str = "system",
    attachment_evidence_id: Optional[int] = None,
) -> Optional[WorkOrder]:
    """追加操作记录到工单 action_log"""
    action = {
        "type": action_type,
        "at": datetime.now(timezone.utc).isoformat(),
        "by": operator,
        "note": note,
    }
    if attachment_evidence_id:
        action["evidence_id"] = attachment_evidence_id
    return crud.append_workorder_action(session, wo_id, action)


def resolve_workorder(
    session: Session,
    wo_id: int,
    note: str,
    resolution_type: str = "OTHER",
    operator: str = "user",
) -> Optional[WorkOrder]:
    """关闭工单，并追加复核调度标记"""
    updates = {
        "status": "RESOLVED",
        "resolved_at": datetime.now(timezone.utc),
        "resolution_note": note,
        "resolution_type": resolution_type,
    }
    wo = crud.update_workorder(session, wo_id, updates)
    if wo:
        append_action(session, wo_id, "RESOLVED", note, operator)
        log.info(f"WorkOrder #{wo_id} resolved by {operator}: {resolution_type}")
    return wo


def check_sla_escalations(session: Session) -> tuple[int, set]:
    """
    轮询所有超期工单，执行升级动作：
    - escalation_level += 1
    - sla_due_at 顺延一个升级间隔（防止同一工单每轮触发）
    - 推送飞书通知（在 caller 中处理，事件驱动）
    返回 (升级数量, 升级的工单ID集合)
    """
    # Escalation SLA extension: each level adds the same hours as the re-check interval + buffer
    ESCALATION_EXTENSION_HOURS = 24  # After escalation, give 24h before next escalation

    overdue = crud.list_open_workorders_overdue(session)
    count = 0
    escalated_ids: set = set()
    for wo in overdue:
        old_level = wo.escalation_level
        new_sla_due = datetime.utcnow() + timedelta(hours=ESCALATION_EXTENSION_HOURS)  # Naive UTC for MySQL
        updates = {
            "escalation_level": old_level + 1,
            "sla_due_at": new_sla_due,  # BUG-5 fix: prevent re-escalation next round
        }
        crud.update_workorder(session, wo.id, updates)
        append_action(
            session, wo.id,
            action_type="ESCALATED",
            note=f"SLA 超时，升级至 Level {old_level + 1}，下次 SLA 截止至 {new_sla_due.strftime('%Y-%m-%d %H:%M UTC')}",
            operator="system",
        )
        escalated_ids.add(wo.id)
        count += 1
        log.warning(f"WorkOrder #{wo.id} escalated to Level {old_level + 1} (overdue SLA), next SLA: {new_sla_due}")

    if count:
        session.commit()
    return count, escalated_ids
