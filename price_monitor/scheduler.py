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
                try:
                    wo = crud.get_workorder(session, wo_id)
                    if wo:
                        wo_dict = {
                            "id": wo.id, "severity": wo.severity,
                            "owner_name": wo.owner_name, "product_name": wo.product_name,
                            "escalation_level": wo.escalation_level,
                        }
                        feishu_notify.send_sla_escalation(wo_dict)
                except Exception as notify_e:
                    log.error(f"Failed to send SLA config for WO {wo_id}: {notify_e}")
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


async def run_playwright_scan(
    platforms=None,   # type: Optional[list]
    keywords=None,    # type: Optional[list]
):
    """
    Playwright 行为仿真采集轮次（独立方案，不影响现有体系）
    
    - 当现有 StealthyFetcher 采集失败时作为 fallback 兜底
    - 采集结果通过 ProductDetail.to_product_price_dict() 转为兼容格式存库
    - 采集失败时推送飞书告警

    参数:
        platforms: 要采集的平台列表，默认从 SCRAPER_REGISTRY 取所有平台
        keywords:  要搜索的关键词列表，默认从 DB 的 BaselinePrice 表取
    """
    import os
    from price_monitor.playwright_engine.scrapers import SCRAPER_REGISTRY, get_scraper
    from price_monitor.playwright_engine.fallback import PlaywrightFallbackEngine
    from price_monitor.db.session import get_session_factory
    from price_monitor.db import crud

    log.info("=" * 60)
    log.info("Starting Playwright behavioral scrape round...")
    log.info("=" * 60)

    # 确定要采集的平台
    active_platforms = platforms or list(SCRAPER_REGISTRY.keys())

    # 确定关键词（从 SearchKeyword 表取，或使用传入参数）
    if not keywords:
        factory = get_session_factory()
        with factory() as session:
            kw_objs = crud.get_active_keywords(session)
            keywords = [k.keyword for k in kw_objs if k.keyword]
        # fallback: 从 BaselinePrice 表取
        if not keywords:
            factory = get_session_factory()
            with factory() as session:
                baselines = crud.get_baselines(session)
                keywords = list({b.keyword for b in baselines if getattr(b, 'keyword', None)})
        if not keywords:
            log.warning("[playwright_scan] No keywords found in DB, skipping")
            return


    log.info(f"[playwright_scan] Platforms: {active_platforms}")
    log.info(f"[playwright_scan] Keywords: {keywords}")

    engine = PlaywrightFallbackEngine()
    total_success = 0
    total_fail = 0

    for platform in active_platforms:
        try:
            scraper = get_scraper(platform)
        except ValueError as e:
            log.warning(f"[playwright_scan] No scraper for {platform}: {e}")
            continue

        for keyword in keywords:
            log.info(f"[playwright_scan] {platform} / '{keyword}'")
            try:
                results = await engine.scrape_by_keyword(
                    platform=platform,
                    keyword=keyword,
                    scraper=scraper,
                    limit=5,
                )
                if results:
                    # 存入数据库（暂以 JSON 日志形式记录，完整 DB 入库在后续迭代中完成）
                    import json
                    log_dir = os.path.join("data", "playwright_results")
                    os.makedirs(log_dir, exist_ok=True)
                    import time
                    log_path = os.path.join(log_dir, f"{platform}_{keyword}_{int(time.time())}.json")
                    with open(log_path, "w", encoding="utf-8") as f:
                        json.dump(
                            [r.to_product_price_dict() for r in results],
                            f, ensure_ascii=False, indent=2, default=str
                        )
                    total_success += len(results)
                    log.info(f"[playwright_scan] ✅ {platform}/{keyword}: {len(results)} results saved to {log_path}")
                else:
                    total_fail += 1
            except Exception as e:
                log.error(f"[playwright_scan] Error {platform}/{keyword}: {e}", exc_info=True)
                total_fail += 1

            # 平台间间隔（防止频率过高）
            import asyncio
            import random
            await asyncio.sleep(random.uniform(5, 15))

    log.info(f"[playwright_scan] Round complete. Success={total_success} | Fail={total_fail}")

