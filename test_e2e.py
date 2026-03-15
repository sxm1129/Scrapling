import asyncio
import time
from price_monitor.collection_manager import CollectionManager
from price_monitor.db.session import init_db

async def test_run():
    init_db()
    cm = CollectionManager()
    print("Testing e2e scrape with jd_express...")
    
    # We will trigger a platform scan to run naturally
    job = await cm.start_platform_scan("jd_express", keyword="iPhone 15", triggered_by="e2e_test")
    print(f"Job started: {job.id}")
    
    for _ in range(30):
        time.sleep(2)
        status = cm.get_job_status(job.id)
        print(f"[{status['status']}] progress: {status['progress']}% | violations: {status['violations_found']}")
        if status['status'] in ('SUCCESS', 'FAILED', 'CANCELLED'):
            break

if __name__ == "__main__":
    asyncio.run(test_run())
