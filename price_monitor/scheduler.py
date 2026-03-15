"""
调度器 — 定时采集任务

轻量封装: 将定时触发委托给 CollectionManager
"""
import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

log = logging.getLogger(__name__)


async def run_scan_round():
    """执行一轮完整扫描 — 委托给 CollectionManager"""
    from price_monitor.collection_manager import CollectionManager

    log.info("=" * 60)
    log.info("Starting scheduled scan round...")
    log.info("=" * 60)

    try:
        manager = CollectionManager()
        job = await manager.start_full_scan(triggered_by="scheduler")
        log.info(f"Scheduled scan job created: id={job.id}")
    except Exception as e:
        log.error(f"Scheduled scan failed: {e}", exc_info=True)
