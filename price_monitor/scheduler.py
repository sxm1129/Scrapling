"""
调度器 — 定时采集任务

轻量封装: 将定时触发委托给 CollectionManager
"""
import logging
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

log = logging.getLogger(__name__)


async def run_scan_round():
    """执行一轮完整扫描 — 直接 await 扫描逻辑 (不能用 ensure_future 因为 asyncio.run 会销毁事件循环)"""
    from price_monitor.collection_manager import CollectionManager

    log.info("=" * 60)
    log.info("Starting scheduled scan round...")
    log.info("=" * 60)

    try:
        manager = CollectionManager()
        # 创建 job 并直接 await 扫描 (而非 start_full_scan 中的 ensure_future)
        from price_monitor.db.session import get_session_factory
        from price_monitor.db import crud
        factory = get_session_factory()
        session = factory()
        try:
            job = crud.create_job(session, {
                "job_type": "FULL_SCAN",
                "triggered_by": "scheduler",
                "status": "PENDING",
            })
            session.commit()
            job_id = job.id
            session.expunge(job)
        finally:
            session.close()

        log.info(f"Scheduled scan job created: id={job_id}")
        # 直接 await, 不用 ensure_future
        await manager._run_full_scan(job_id)
    except Exception as e:
        log.error(f"Scheduled scan failed: {e}", exc_info=True)


async def run_cookie_keeper():
    """执行账号 Cookie 保活机制"""
    from price_monitor.cookie_keeper import CookieKeeper
    
    log.info("=" * 60)
    log.info("Starting scheduled CookieKeeper round...")
    log.info("=" * 60)
    
    try:
        keeper = CookieKeeper()
        await keeper.run_keeper()
    except Exception as e:
        log.error(f"Scheduled CookieKeeper failed: {e}", exc_info=True)


async def run_sla_check():
    """检查所有超期工单，触发升级 + 飞书通知"""
    from price_monitor.engine.workorder_engine import check_sla_escalations
    from price_monitor.db.session import get_session_factory
    from price_monitor.db import crud
    from price_monitor.notify import feishu as feishu_notify

    log.info("Starting SLA escalation check...")
    factory = get_session_factory()
    session = factory()
    escalated_ids: set = set()
    count = 0
    try:
        count, escalated_ids = check_sla_escalations(session)
        if count:
            log.warning(f"Escalated {count} overdue workorders: {escalated_ids}")
            # Send Feishu alerts ONLY for WOs escalated THIS round
            for wo_id in escalated_ids:
                wo = crud.get_workorder(session, wo_id)
                if wo:
                    wo_dict = {
                        "id": wo.id, "severity": wo.severity,
                        "owner_name": wo.owner_name, "product_name": wo.product_name,
                        "escalation_level": wo.escalation_level,
                    }
                    feishu_notify.send_sla_escalation(wo_dict)
    except Exception as e:
        log.error(f"SLA check failed: {e}", exc_info=True)
    finally:
        session.close()
    log.info(f"SLA check done, escalated: {count}")


async def run_periodic_report(report_type: str = "WEEKLY"):
    """生成周报并推送到飞书"""
    from datetime import datetime, timezone, timedelta
    from price_monitor.engine import reporting_engine
    from price_monitor.db.session import get_session_factory
    from price_monitor.db import crud
    from price_monitor.notify import feishu as feishu_notify
    import os

    log.info(f"Generating {report_type} report...")
    factory = get_session_factory()
    session = factory()
    try:
        now = datetime.utcnow()  # Naive UTC for MySQL DATETIME comparisons
        days = 7 if report_type == "WEEKLY" else 30
        start = now - timedelta(days=days)
        kpis = reporting_engine.generate_kpis(session, start, now)

        report_data = {
            "report_type": report_type,
            "start_date": start,
            "end_date": now,
            "status": "DONE",
            "kpi_snapshot": kpis,
            "triggered_by": "scheduler",
            "feishu_webhook_url": os.getenv("FEISHU_WEBHOOK_URL", ""),
        }
        report = crud.create_periodic_report(session, report_data)
        session.commit()

        # Push to Feishu
        webhook = os.getenv("FEISHU_WEBHOOK_URL", "")
        if webhook:
            feishu_notify.send_report_ready(
                report={"id": report.id, "start_date": start, "end_date": now},
                kpis=kpis,
                webhook_url=webhook,
            )
            crud.update_periodic_report(session, report.id, {"pushed_at": now})
            session.commit()
        log.info(f"Periodic report #{report.id} generated and pushed.")
    except Exception as e:
        log.error(f"Periodic report failed: {e}", exc_info=True)
    finally:
        session.close()
