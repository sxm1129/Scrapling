"""
调度器 — 定时扫描任务
"""
import asyncio
import hashlib
import logging
import os
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from price_monitor.db.session import get_session_factory, init_db
from price_monitor.db.models import OfferSnapshot, SearchKeyword
from price_monitor.db import crud
from price_monitor.engine import process_offers
from price_monitor.notify import notify_violation, notify_scan_summary, notify_cookie_expired

log = logging.getLogger(__name__)

PLATFORMS = ["taobao", "tmall", "jd_express", "pinduoduo", "taobao_flash"]
PAGES_PER_PLATFORM = int(os.getenv("PAGES_PER_PLATFORM", "20"))


def _make_offer_hash(platform: str, product_name: str, shop_name: str) -> str:
    """生成 offer 幂等 hash"""
    now = datetime.now(timezone.utc)
    bucket = now.strftime("%Y%m%d%H")
    raw = f"{platform}|{product_name}|{shop_name}|{bucket}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


async def run_scan_round():
    """执行一轮完整扫描"""
    log.info("=" * 60)
    log.info("Starting scan round...")
    log.info("=" * 60)

    factory = get_session_factory()
    session = factory()

    try:
        keywords = crud.get_active_keywords(session)
        if not keywords:
            log.warning("No active keywords found")
            return

        total_offers = 0
        total_violations = 0
        total_p0 = 0
        total_p1 = 0
        start_time = time.time()

        for kw_obj in keywords:
            keyword = kw_obj.keyword
            log.info(f"\n--- Scanning keyword: {keyword} ---")

            kw_offers = []
            for platform in PLATFORMS:
                try:
                    offers = await _scrape_platform(platform, keyword, session)
                    kw_offers.extend(offers)
                    log.info(f"  [{platform}] {len(offers)} offers")
                except Exception as e:
                    log.error(f"  [{platform}] Scrape failed: {e}")

            if kw_offers:
                # 批量写入 DB (获取 offer IDs)
                session.add_all(kw_offers)
                session.commit()

                # 违规判定 (process_offers 内部有自己的 commit)
                violations = process_offers(session, kw_offers)
                total_offers += len(kw_offers)
                total_violations += len(violations)

                # 飞书通知违规 — 隔离通知失败，确保 notified 状态正确持久化
                notify_updates = False
                for v in violations:
                    if not v.is_whitelisted:
                        if v.severity == "P0":
                            total_p0 += 1
                        elif v.severity == "P1":
                            total_p1 += 1
                        try:
                            notify_violation(v)
                            v.notified = True
                            notify_updates = True
                        except Exception as e:
                            log.error(f"  Notify failed: {e}")
                if notify_updates:
                    try:
                        session.commit()
                    except Exception as e:
                        session.rollback()
                        log.error(f"  Notify status commit failed: {e}")

        duration = time.time() - start_time

        # 推送汇总
        try:
            notify_scan_summary(
                keyword=", ".join(k.keyword for k in keywords[:3]),
                total_offers=total_offers,
                new_violations=total_violations,
                p0_count=total_p0,
                p1_count=total_p1,
                duration_sec=duration,
            )
        except Exception as e:
            log.error(f"Summary notify failed: {e}")

        log.info(f"\nScan round complete: {total_offers} offers, {total_violations} violations ({total_p0} P0, {total_p1} P1) in {duration:.1f}s")

    except Exception as e:
        log.error(f"Scan round failed: {e}", exc_info=True)
        try:
            session.rollback()
        except Exception:
            pass
    finally:
        session.close()


async def _scrape_platform(platform: str, keyword: str, session) -> list[OfferSnapshot]:
    """单平台采集 (使用现有 scrapers)"""
    # TODO: 对接真实 scraper 翻页逻辑
    # 一期先用搜索 API 采集第一页数据作为 MVP 演示
    offers = []

    try:
        from scrapling.fetchers import StealthyFetcher
        from price_monitor.account_pool import AccountPool
        import re, json
        from urllib.parse import quote

        pool = AccountPool(pool_file=str(Path(__file__).resolve().parents[1] / "accounts.json"))

        kw_enc = quote(keyword)
        captured_at = datetime.now(timezone.utc)

        if platform == "taobao":
            cookie_platform = "taobao"
            url = f"https://s.taobao.com/search?q={kw_enc}"
            products = await _fetch_with_js(pool, cookie_platform, url, keyword)

        elif platform == "tmall":
            cookie_platform = "taobao"
            url = f"https://list.tmall.com/search_product.htm?q={kw_enc}"
            products = await _fetch_with_js(pool, cookie_platform, url, keyword)

        elif platform == "jd_express":
            cookie_platform = "jd_express"
            url = f"https://search.jd.com/Search?keyword={kw_enc}&enc=utf-8"
            products = await _fetch_with_js(pool, cookie_platform, url, keyword, init_url="https://www.jd.com/")

        elif platform == "pinduoduo":
            cookie_platform = "pinduoduo"
            url = f"https://mobile.yangkeduo.com/search_result.html?search_key={kw_enc}"
            products = await _fetch_with_js(pool, cookie_platform, url, keyword)

        elif platform == "taobao_flash":
            cookie_platform = "taobao"
            url = f"https://s.m.taobao.com/h5?q={kw_enc}&tab=sg"
            products = await _fetch_with_api(pool, cookie_platform, url, keyword)

        else:
            return []

        for p in products:
            raw_price_val = p.get("price", 0)
            try:
                price = Decimal(str(raw_price_val)) if raw_price_val else Decimal("0")
            except (InvalidOperation, ValueError):
                price = Decimal("0")
            if price <= 0:
                continue

            offer = OfferSnapshot(
                offer_hash=_make_offer_hash(platform, p.get("title", ""), p.get("shop", "")),
                platform=platform,
                keyword=keyword,
                canonical_url=p.get("url", url),
                product_name=p.get("title", "")[:300],
                shop_name=p.get("shop", "")[:100],
                ship_from_city=p.get("location", "")[:50],
                raw_price=price,
                final_price=price,
                sales_volume=p.get("sales", "")[:50],
                confidence="MED",
                parse_status="OK",
                captured_at=captured_at,
            )
            offers.append(offer)

    except Exception as e:
        log.error(f"  [{platform}] scrape error: {e}")

    return offers


async def _fetch_with_js(pool, cookie_platform, url, keyword, init_url=None):
    """通用 JS DOM 提取"""
    from scrapling.fetchers import StealthyFetcher
    import re

    cookies = pool.get_playwright_cookies(cookie_platform)
    products = []

    JS_EXTRACT = r"""() => {
        const result = [];
        let text = document.body ? document.body.innerText : '';
        text = text.replace(/[¥￥]\s*\n\s*(\d+)\s*\.\s*\n\s*(\d+)/g, '¥$1.$2');
        const lines = text.split('\n').map(l => l.trim()).filter(l => l.length > 0);
        const seen = new Set();
        for (let i = 0; i < lines.length; i++) {
            const match = lines[i].match(/[¥￥]\s*([\d]+\.?\d*)/);
            if (!match) continue;
            const price = parseFloat(match[1]);
            if (price <= 0 || price > 9999) continue;
            let title = '';
            for (let j = Math.max(0, i-5); j < i; j++) {
                const c = lines[j];
                if (c.length > 5 && c.length < 200 && !/^[¥￥\d\.\s]+$/.test(c)) title = c;
            }
            if (!title || title.length < 3) continue;
            const key = title.substring(0, 20);
            if (seen.has(key)) continue;
            seen.add(key);
            let shop = '', sales = '';
            for (let j = i+1; j < Math.min(lines.length, i+8); j++) {
                const n = lines[j];
                if (!shop && (n.includes('旗舰') || n.includes('专营') || n.includes('自营') || n.includes('超市'))) shop = n;
                if (!sales && (n.includes('人付款') || n.includes('已售') || n.includes('已拼') || n.includes('月销'))) sales = n;
            }
            result.push({title: title.substring(0,200), price, shop: shop.substring(0,60), sales: sales.substring(0,50)});
        }
        return JSON.stringify(result);
    }"""

    async def page_action(page):
        nonlocal products
        if cookies:
            await page.context.add_cookies(cookies)
        if init_url:
            try:
                await page.goto(init_url, wait_until="domcontentloaded", timeout=15000)
            except Exception as e:
                log.warning(f"init_url goto failed: {e}")
            await page.wait_for_timeout(2000)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        except Exception as e:
            log.warning(f"main url goto failed: {e}")
        await page.wait_for_timeout(5000)
        for _ in range(6):
            await page.evaluate("window.scrollBy(0, 500)")
            await page.wait_for_timeout(500)

        try:
            raw = await page.evaluate(JS_EXTRACT)
            import json
            products = json.loads(raw) if isinstance(raw, str) else raw
        except Exception as e:
            log.warning(f"JS extract failed: {e}")

    try:
        await StealthyFetcher.async_fetch(
            init_url or url, headless=True, network_idle=False,
            page_action=page_action, timeout=50000,
        )
    except Exception as e:
        log.error(f"StealthyFetcher error: {e}")

    return products


async def _fetch_with_api(pool, cookie_platform, url, keyword):
    """淘宝闪购 MTOP API 拦截"""
    from scrapling.fetchers import StealthyFetcher
    import re, json

    cookies = pool.get_playwright_cookies(cookie_platform)
    products = []

    async def page_action(page):
        nonlocal products

        async def handle_resp(response):
            if 'mtop.relationrecommend' in response.url:
                try:
                    body = await response.text()
                    if len(body) > 5000:
                        m = re.match(r'mtopjsonp\d+\((.+)\)$', body.strip(), re.DOTALL)
                        data = json.loads(m.group(1) if m else body)
                        for item in data.get("data", {}).get("itemsArray", []):
                            title = re.sub(r'<[^>]+>', '', item.get("title", "")).strip()
                            if not title: continue
                            shop_info = item.get("shopInfo") or {}
                            shop_list = shop_info.get("shopInfoList", []) if isinstance(shop_info, dict) else []
                            candidates = [s for s in shop_list if s and s not in ("进店", "关注")]
                            products.append({
                                "title": title[:200],
                                "price": float(item.get("price", 0) or 0),
                                "shop": (candidates[0] if candidates else "")[:60],
                                "sales": str(item.get("realSales", ""))[:50],
                                "location": item.get("procity", ""),
                            })
                except Exception as e:
                    log.warning(f"MTOP parse error: {e}")

        page.on("response", handle_resp)
        if cookies:
            await page.context.add_cookies(cookies)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        except Exception as e:
            log.warning(f"Flash goto failed: {e}")
        await page.wait_for_timeout(5000)

    try:
        await StealthyFetcher.async_fetch(
            url, headless=True, network_idle=False,
            page_action=page_action, timeout=40000,
        )
    except Exception as e:
        log.error(f"Flash API fetch error: {e}")

    return products
