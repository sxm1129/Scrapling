"""
CRUD 操作 — 数据库读写封装
"""
import hashlib
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from price_monitor.db.models import (
    OfferSnapshot, Violation, BaselinePrice,
    SearchKeyword, WhitelistRule, CookieAccount, ScrapeJob,
    WorkOrder, ResponsibilityRule, PeriodicReport,
)


# ── OfferSnapshot ──


def make_offer_hash(platform: str, url: str, time_bucket_min: int = 60) -> str:
    """生成 offer 幂等 hash: hash(platform + url + time_bucket)"""
    now = datetime.utcnow()  # Naive UTC for consistent hashing
    # bucket = YYYYMMDDHH + bucket_index (e.g., 60min → one bucket per hour)
    bucket_idx = (now.hour * 60 + now.minute) // time_bucket_min
    bucket = now.strftime("%Y%m%d") + f"_{bucket_idx}"
    raw = f"{platform}|{url}|{bucket}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def upsert_offer(session: Session, data: dict) -> OfferSnapshot:
    """插入报价快照 (每次都存, 通过 offer_hash 可查重)"""
    offer = OfferSnapshot(**data)
    session.add(offer)
    session.flush()
    return offer


def bulk_insert_offers(session: Session, offers: list[dict]) -> int:
    """批量插入报价快照"""
    objects = [OfferSnapshot(**d) for d in offers]
    session.add_all(objects)
    session.flush()
    return len(objects)


def list_offers(
    session: Session,
    platform: str = None,
    keyword: str = None,
    shop_name: str = None,
    city: str = None,
    start_time: datetime = None,
    end_time: datetime = None,
    sort_by: str = "time_desc",
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[OfferSnapshot], int]:
    """查询报价快照列表 + 总数"""
    q = session.query(OfferSnapshot)
    if platform:
        q = q.filter(OfferSnapshot.platform == platform)
    if keyword:
        q = q.filter(OfferSnapshot.keyword.contains(keyword))
    if shop_name:
        q = q.filter(OfferSnapshot.shop_name.contains(shop_name))
    if city:
        q = q.filter(OfferSnapshot.ship_from_city.contains(city))
    if start_time:
        q = q.filter(OfferSnapshot.captured_at >= start_time)
    if end_time:
        q = q.filter(OfferSnapshot.captured_at <= end_time)

    total = q.count()

    if sort_by == "price_asc":
        q = q.order_by(OfferSnapshot.final_price.asc(), desc(OfferSnapshot.id))
    elif sort_by == "price_desc":
        q = q.order_by(OfferSnapshot.final_price.desc(), desc(OfferSnapshot.id))
    else:
        # Default: time_desc
        q = q.order_by(desc(OfferSnapshot.captured_at), desc(OfferSnapshot.id))

    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return items, total


# ── Violation ──


def create_violation(session: Session, data: dict) -> Violation:
    """创建违规记录"""
    v = Violation(**data)
    session.add(v)
    session.flush()
    return v


def list_violations(
    session: Session,
    platform: str = None,
    severity: str = None,
    is_whitelisted: bool = None,
    start_time: datetime = None,
    end_time: datetime = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[Violation], int]:
    """查询违规列表"""
    q = session.query(Violation)
    if platform:
        q = q.filter(Violation.platform == platform)
    if severity:
        q = q.filter(Violation.severity == severity)
    if is_whitelisted is not None:
        q = q.filter(Violation.is_whitelisted == is_whitelisted)
    if start_time:
        q = q.filter(Violation.created_at >= start_time)
    if end_time:
        q = q.filter(Violation.created_at <= end_time)

    total = q.count()
    items = q.order_by(desc(Violation.created_at)).offset((page - 1) * page_size).limit(page_size).all()
    return items, total


def get_violation_detail(session: Session, violation_id: int) -> Optional[Violation]:
    """获取违规详情"""
    return session.query(Violation).filter(Violation.id == violation_id).first()


# ── BaselinePrice ──


def get_baselines(session: Session) -> list[BaselinePrice]:
    """获取所有基准价"""
    return session.query(BaselinePrice).order_by(BaselinePrice.id).all()


def upsert_baseline(session: Session, data: dict) -> BaselinePrice:
    """创建或更新基准价"""
    existing = session.query(BaselinePrice).filter(
        BaselinePrice.product_pattern == data["product_pattern"]
    ).first()
    if existing:
        for k, v in data.items():
            setattr(existing, k, v)
        session.flush()
        return existing
    bp = BaselinePrice(**data)
    session.add(bp)
    session.flush()
    return bp


def delete_baseline(session: Session, baseline_id: int) -> bool:
    """删除基准价"""
    bp = session.query(BaselinePrice).filter(BaselinePrice.id == baseline_id).first()
    if bp:
        session.delete(bp)
        return True
    return False


# ── SearchKeyword ──


def get_active_keywords(session: Session) -> list[SearchKeyword]:
    """获取已启用关键词"""
    return session.query(SearchKeyword).filter(SearchKeyword.enabled == True).order_by(
        desc(SearchKeyword.priority), SearchKeyword.id
    ).all()


def add_keyword(session: Session, keyword: str, priority: int = 0) -> SearchKeyword:
    """添加关键词"""
    existing = session.query(SearchKeyword).filter(SearchKeyword.keyword == keyword).first()
    if existing:
        existing.enabled = True
        existing.priority = priority
        session.flush()
        return existing
    kw = SearchKeyword(keyword=keyword, priority=priority)
    session.add(kw)
    session.flush()
    return kw


def toggle_keyword(session: Session, keyword_id: int, enabled: bool) -> bool:
    """启用/禁用关键词"""
    kw = session.query(SearchKeyword).filter(SearchKeyword.id == keyword_id).first()
    if kw:
        kw.enabled = enabled
        return True
    return False


# ── WhitelistRule ──


def get_active_whitelist(session: Session) -> list[WhitelistRule]:
    """获取有效白名单（使用 naive UTC 与 MySQL DATETIME 比较）"""
    now = datetime.utcnow()  # MySQL DATETIME is naive UTC
    return session.query(WhitelistRule).filter(
        WhitelistRule.status == "ACTIVE",
        (WhitelistRule.expires_at.is_(None)) | (WhitelistRule.expires_at > now),
    ).all()


def create_whitelist(session: Session, data: dict) -> WhitelistRule:
    """创建白名单规则"""
    rule = WhitelistRule(**data)
    session.add(rule)
    session.flush()
    return rule


# ── CookieAccount ──


def get_platform_cookies(session: Session, platform: str) -> Optional[CookieAccount]:
    """获取平台的活跃 Cookie"""
    return session.query(CookieAccount).filter(
        CookieAccount.platform == platform,
        CookieAccount.status == "ACTIVE",
    ).order_by(desc(CookieAccount.last_used)).first()


def save_cookies(session: Session, platform: str, account_id: str, cookies: list[dict]) -> CookieAccount:
    """保存/更新 Cookie"""
    existing = session.query(CookieAccount).filter(
        CookieAccount.platform == platform,
        CookieAccount.account_id == account_id,
    ).first()
    if existing:
        existing.cookies = cookies
        existing.status = "ACTIVE"
        existing.expired_at = None
        session.flush()
        return existing
    ca = CookieAccount(platform=platform, account_id=account_id, cookies=cookies)
    session.add(ca)
    session.flush()
    return ca


# ── Dashboard 聚合 ──


def get_dashboard_stats(session: Session) -> dict:
    """看板统计（使用 naive UTC 与 MySQL DATETIME 比较）"""
    now = datetime.utcnow()  # MySQL DATETIME is naive UTC
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    total_offers = session.query(func.count(OfferSnapshot.id)).scalar()
    today_offers = session.query(func.count(OfferSnapshot.id)).filter(
        OfferSnapshot.captured_at >= today_start
    ).scalar()
    total_violations = session.query(func.count(Violation.id)).filter(
        Violation.is_whitelisted == False
    ).scalar()
    today_violations = session.query(func.count(Violation.id)).filter(
        Violation.created_at >= today_start,
        Violation.is_whitelisted == False,
    ).scalar()

    # 按平台分布
    platform_dist = session.query(
        Violation.platform,
        func.count(Violation.id),
    ).filter(Violation.is_whitelisted == False).group_by(Violation.platform).all()

    # 按严重度分布
    severity_dist = session.query(
        Violation.severity,
        func.count(Violation.id),
    ).filter(Violation.is_whitelisted == False).group_by(Violation.severity).all()

    return {
        "total_offers": total_offers or 0,
        "today_offers": today_offers or 0,
        "total_violations": total_violations or 0,
        "today_violations": today_violations or 0,
        "platform_distribution": {p: c for p, c in platform_dist},
        "severity_distribution": {s: c for s, c in severity_dist},
    }


# ── ScrapeJob ──


def create_job(session: Session, data: dict) -> ScrapeJob:
    """创建采集任务"""
    job = ScrapeJob(**data)
    session.add(job)
    session.flush()
    return job


def update_job_status(
    session: Session, job_id: int, status: str, **kwargs,
) -> Optional[ScrapeJob]:
    """更新任务状态 (可附带 error_message, finished_at 等)"""
    job = session.query(ScrapeJob).filter(ScrapeJob.id == job_id).first()
    if not job:
        return None
    job.status = status
    for k, v in kwargs.items():
        if hasattr(job, k):
            setattr(job, k, v)
    session.flush()
    return job


def update_job_progress(
    session: Session, job_id: int,
    progress: int, success_items: int, fail_items: int,
    total_items: int = None, violations_found: int = None,
) -> None:
    """更新任务进度 (高频调用, 只更新必要字段)"""
    updates = {
        "progress": progress,
        "success_items": success_items,
        "fail_items": fail_items,
    }
    if total_items is not None:
        updates["total_items"] = total_items
    if violations_found is not None:
        updates["violations_found"] = violations_found
    session.query(ScrapeJob).filter(ScrapeJob.id == job_id).update(updates)


def list_jobs(
    session: Session,
    platform: str = None,
    status: str = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[ScrapeJob], int]:
    """查询任务列表"""
    q = session.query(ScrapeJob)
    if platform:
        q = q.filter(ScrapeJob.platform == platform)
    if status:
        q = q.filter(ScrapeJob.status == status)
    total = q.count()
    items = q.order_by(desc(ScrapeJob.created_at)).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    return items, total


def fail_stale_jobs(session: Session) -> int:
    """清理异常中断的僵尸任务 (服务器重启时调用)"""
    stale_jobs = session.query(ScrapeJob).filter(
        ScrapeJob.status.in_(["PENDING", "RUNNING"])
    ).all()
    
    count = 0
    now = datetime.utcnow()  # MySQL DATETIME is naive UTC
    for j in stale_jobs:
        j.status = "FAILED"
        j.error_message = "Server restarted abruptly"
        j.finished_at = now
        count += 1
        
    if count > 0:
        session.commit()
    return count


def get_job(session: Session, job_id: int) -> Optional[ScrapeJob]:
    """获取单个任务"""
    return session.query(ScrapeJob).filter(ScrapeJob.id == job_id).first()


def get_latest_jobs_by_platform(session: Session) -> list[ScrapeJob]:
    """获取每个平台最近一次任务 (用于看板)"""
    subq = session.query(
        ScrapeJob.platform,
        func.max(ScrapeJob.id).label("max_id"),
    ).filter(ScrapeJob.platform.isnot(None)).group_by(ScrapeJob.platform).subquery()

    return session.query(ScrapeJob).join(
        subq, ScrapeJob.id == subq.c.max_id,
    ).all()


# ── WorkOrder ──

def create_workorder(session: Session, data: dict) -> WorkOrder:
    """创建工单"""
    wo = WorkOrder(**data)
    if wo.action_log is None:
        wo.action_log = []
    session.add(wo)
    session.flush()
    return wo


def get_workorder(session: Session, wo_id: int) -> Optional[WorkOrder]:
    return session.query(WorkOrder).filter(WorkOrder.id == wo_id).first()


def list_workorders(
    session: Session,
    status: str = None,
    severity: str = None,
    owner_user_id: str = None,
    platform: str = None,
    sla_due_before: datetime = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[WorkOrder], int]:
    q = session.query(WorkOrder)
    if status:
        q = q.filter(WorkOrder.status == status)
    if severity:
        q = q.filter(WorkOrder.severity == severity)
    if owner_user_id:
        q = q.filter(WorkOrder.owner_user_id == owner_user_id)
    if platform:
        q = q.filter(WorkOrder.platform == platform)
    if sla_due_before:
        q = q.filter(WorkOrder.sla_due_at <= sla_due_before)
    total = q.count()
    items = q.order_by(desc(WorkOrder.created_at)).offset((page - 1) * page_size).limit(page_size).all()
    return items, total


def update_workorder(session: Session, wo_id: int, updates: dict) -> Optional[WorkOrder]:
    wo = get_workorder(session, wo_id)
    if not wo:
        return None
    for k, v in updates.items():
        setattr(wo, k, v)
    wo.updated_at = datetime.utcnow()  # Naive UTC for MySQL DATETIME
    session.flush()
    return wo


def append_workorder_action(session: Session, wo_id: int, action: dict) -> Optional[WorkOrder]:
    """追加操作日志（不可变审计）"""
    wo = get_workorder(session, wo_id)
    if not wo:
        return None
    log = list(wo.action_log or [])
    action.setdefault("at", datetime.utcnow().isoformat())  # Naive UTC isoformat for JSON display
    log.append(action)
    wo.action_log = log
    wo.updated_at = datetime.utcnow()  # Naive UTC for MySQL DATETIME
    session.flush()
    return wo


def list_open_workorders_overdue(session: Session) -> list[WorkOrder]:
    """查询所有已超 SLA 的开放工单（使用 naive UTC 与 MySQL DATETIME 比较）"""
    now_utc = datetime.utcnow()  # MySQL DATETIME stores naive UTC
    return session.query(WorkOrder).filter(
        WorkOrder.status.in_(["OPEN", "IN_PROGRESS"]),
        WorkOrder.sla_due_at <= now_utc,
    ).all()


# ── ResponsibilityRule ──

def list_responsibility_rules(session: Session, platform: str = None, active_only: bool = True) -> list[ResponsibilityRule]:
    q = session.query(ResponsibilityRule)
    if active_only:
        q = q.filter(ResponsibilityRule.is_active == True)
    if platform:
        q = q.filter((ResponsibilityRule.platform == platform) | (ResponsibilityRule.platform == None))
    return q.order_by(desc(ResponsibilityRule.priority)).all()


def create_responsibility_rule(session: Session, data: dict) -> ResponsibilityRule:
    rule = ResponsibilityRule(**data)
    session.add(rule)
    session.flush()
    return rule


def delete_responsibility_rule(session: Session, rule_id: int) -> bool:
    rule = session.query(ResponsibilityRule).filter(ResponsibilityRule.id == rule_id).first()
    if rule:
        rule.is_active = False
        session.flush()
        return True
    return False


# ── PeriodicReport ──

def create_periodic_report(session: Session, data: dict) -> PeriodicReport:
    report = PeriodicReport(**data)
    session.add(report)
    session.flush()
    return report


def update_periodic_report(session: Session, report_id: int, updates: dict) -> Optional[PeriodicReport]:
    report = session.query(PeriodicReport).filter(PeriodicReport.id == report_id).first()
    if report:
        for k, v in updates.items():
            setattr(report, k, v)
        session.flush()
    return report


def list_periodic_reports(session: Session, page: int = 1, page_size: int = 20) -> tuple[list[PeriodicReport], int]:
    q = session.query(PeriodicReport).order_by(desc(PeriodicReport.created_at))
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return items, total
