"""
Antigravity 价格监测系统 — 主入口
启动 FastAPI + 定时调度器
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

# 确保项目根目录在 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("antigravity")


def main():
    """启动 FastAPI 服务器 + 定时采集"""
    import signal
    import uvicorn
    from apscheduler.schedulers.background import BackgroundScheduler
    from price_monitor.scheduler import run_scan_round

    api_port = int(os.getenv("API_PORT", "8000"))
    scan_interval = int(os.getenv("SCAN_INTERVAL_HOURS", "12"))

    # 定时调度器
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        lambda: asyncio.run(run_scan_round()),
        "interval",
        hours=scan_interval,
        id="scan_round",
        name=f"Full scan every {scan_interval}h",
        misfire_grace_time=3600,
    )
    
    # Cookie 保活调度器: 每一小时跑一次
    from price_monitor.scheduler import run_cookie_keeper
    scheduler.add_job(
        lambda: asyncio.run(run_cookie_keeper()),
        "interval",
        hours=1,
        id="cookie_keeper",
        name="Cookie Keeper heartbeat loop",
        misfire_grace_time=3600,
    )
    
    scheduler.start()
    log.info(f"Scheduler started: scan every {scan_interval}h, keep-alive every 1h")

    # 优雅关闭
    def shutdown_handler(signum, frame):
        log.info("Received shutdown signal, stopping scheduler...")
        scheduler.shutdown(wait=False)
        sys.exit(0)
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    # 启动 FastAPI
    log.info(f"Starting API server on port {api_port}...")
    try:
        uvicorn.run(
            "price_monitor.api.app:app",
            host="0.0.0.0",
            port=api_port,
            reload=False,
            log_level="info",
        )
    finally:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()
