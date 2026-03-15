import asyncio
from price_monitor.collection_manager import CollectionManager
from price_monitor.db.session import init_db

async def main():
    init_db()
    cm = CollectionManager()
    print("Testing pipeline with a direct call to JD Express scrape_search...")
    
    # We will invoke cm._scrape_one directly for testing
    factory = __import__("price_monitor.db.session").db.session.get_session_factory()
    session = factory()
    
    try:
        offers = await cm._scrape_one("jd_express", "iPhone 15", session)
        print(f"Scrape finished. Found {len(offers)} offers.")
        for o in offers:
            print(f"Name: {o.product_name}")
            print(f"Price: ¥{o.final_price}")
            print(f"Screenshot Path: {o.screenshot_path}")
            print(f"Screenshot Hash: {o.screenshot_hash}")
            print("-" * 50)
    finally:
        session.close()

if __name__ == "__main__":
    asyncio.run(main())
