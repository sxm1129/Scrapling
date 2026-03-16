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
