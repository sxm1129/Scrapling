import asyncio
from price_monitor.collection_manager import CollectionManager
import logging

logging.basicConfig(level=logging.INFO)

async def run_e2e():
    print("=== STARTING E2E TEST ===")
    manager = CollectionManager()
    print("Manager initialized, starting full scan (limit to 1 keyword for speed)...")
    
    # We will trigger a full scan
    job = await manager.start_full_scan(keyword="卡士原态酪乳", triggered_by="e2e-test")
    print(f"Job {job.id} created. Waiting for completion...")
    
    # Manager runs it in background, we need to wait a bit
    from price_monitor.db.session import get_session_factory
    from price_monitor.db import crud
    
    factory = get_session_factory()
    session = factory()
    
    for _ in range(60):
        session.expire_all()
        j = crud.get_job(session, job.id)
        print(f"Job progress: {j.progress}% - Status: {j.status} - success: {j.success_items}")
        if j.status in ("SUCCESS", "FAILED", "CANCELLED"):
            print(f"Finished with status {j.status}")
            break
        await asyncio.sleep(5)
        
    print("=== TEST COMPLETED ===")

if __name__ == "__main__":
    asyncio.run(run_e2e())
