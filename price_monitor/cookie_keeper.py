import asyncio
import logging
import random
from typing import Optional
from price_monitor.account_pool import AccountPool
from scrapling.fetchers.stealth_chrome import StealthyFetcher

log = logging.getLogger("price_monitor.cookie_keeper")

class CookieKeeper:
    def __init__(self, pool_file: str = "./accounts.json"):
        self.pool = AccountPool(pool_file)
        # Platforms that we officially support and need to keep their session alive
        self.supported_platforms = ["jd_express", "taobao", "tmall", "taobao_flash"]
        
        self.heartbeat_urls = {
            "jd_express": "https://my.m.jd.com/",
            "taobao": "https://main.m.taobao.com/",
            "tmall": "https://main.m.taobao.com/",
            "taobao_flash": "https://main.m.taobao.com/",
        }

    async def refresh_account_cookies(self, platform: str, account_id: str, old_cookies: list[dict]) -> bool:
        """
        Spawns a headless browser with the old cookies, visits the heartbeat URL,
        simulates some activity, and saves the newly issued Set-Cookies.
        """
        heartbeat_url = self.heartbeat_urls.get(platform)
        if not heartbeat_url:
            log.warning(f"No heartbeat URL defined for {platform}")
            return False

        log.info(f"[{platform}] Refreshing account '{account_id}' at {heartbeat_url}")
        
        new_cookies = []
        is_success = False
        
        async def page_action(page):
            nonlocal new_cookies, is_success
            # Wait for main content to load
            await page.wait_for_timeout(3000)
            
            # Check if redirected to login explicitly
            current_url = page.url
            if "login" in current_url.lower():
                log.warning(f"[{platform}] Account '{account_id}' was redirected to login: {current_url}. Marking as invalid.")
                self.pool.mark_failed(platform, account_id, max_fails=1) # Immediately invalid
                return
            
            log.info(f"[{platform}] Successfully loaded {current_url}. Simulating human interaction.")
            # Random scroll interactions to appear human
            for _ in range(random.randint(2, 5)):
                await page.evaluate("window.scrollBy(0, 300)")
                await page.wait_for_timeout(random.randint(1000, 3000))
            
            # Grab updated cookies from browser context
            new_cookies = await page.context.cookies()
            is_success = True

        try:
            await StealthyFetcher.async_fetch(
                url=heartbeat_url,
                headless=True,
                network_idle=False,
                page_action=page_action,
                timeout=30000,
                cookies=old_cookies
            )
            
            if is_success and new_cookies:
                # Override the old cookies with the newly grabbed ones
                self.pool.add_account(platform=platform, account_id=account_id, cookies=new_cookies)
                log.info(f"[{platform}] Successfully refreshed {len(new_cookies)} cookies for '{account_id}'.")
                return True
                
        except Exception as e:
            log.error(f"[{platform}] Cookie refresh sequence failed for '{account_id}': {e}")
            
        return False

    async def run_keeper(self):
        """
        Iterates over all active accounts across supported platforms and refreshes them sequentially.
        """
        log.info("Starting CookieKeeper routine...")
        self.pool._load()  # Make sure we have the latest external modifications
        
        stats = self.pool.get_stats()
        log.info(f"Current pool stats: {stats}")
        
        for platform in self.supported_platforms:
            accounts = self.pool._pool.get(platform, [])
            active_accounts = [acc for acc in accounts if acc.get("status") == "active"]
            
            if not active_accounts:
                continue
                
            log.info(f"Found {len(active_accounts)} active accounts for {platform}.")
            
            for acc in active_accounts:
                acc_id = acc["id"]
                old_cookies = acc.get("cookies", [])
                
                if not old_cookies:
                    continue
                    
                success = await self.refresh_account_cookies(platform, acc_id, old_cookies)
                
                # Sleep between accounts to avoid aggressive bot detection
                sleep_time = random.randint(10, 25)
                log.info(f"Sleeping for {sleep_time}s to avoid ratelimits...")
                await asyncio.sleep(sleep_time)
                
        log.info("CookieKeeper routine finished.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    keeper = CookieKeeper()
    asyncio.run(keeper.run_keeper())
