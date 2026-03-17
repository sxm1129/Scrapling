"""
采集管理器 — 数据采集调度核心

桥接调度器 / API → scraper registry → DB, 提供:
  - 全量扫描 (FULL_SCAN)
  - 单平台扫描 (PLATFORM_SCAN)
  - 单 URL 采集 (SINGLE_URL)
"""

import asyncio
import hashlib
import logging
import os
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

from price_monitor.db.session import get_session_factory
from price_monitor.db.models import OfferSnapshot, ScrapeJob
from price_monitor.db import crud
from price_monitor.engine import process_offers
from price_monitor.notify import notify_violation, notify_scan_summary
from price_monitor.models import ProductPrice, ScrapeTask, Platform
from price_monitor.config import Config
from price_monitor.screenshot import PriceScreenshot
from price_monitor.account_pool import AccountPool
from price_monitor.scrapers.registry import create_scraper, list_supported_platforms

log = logging.getLogger(__name__)

# 运行中任务 (内存跟踪, 用于取消)
_active_jobs: dict[int, bool] = {}  # job_id → cancelled flag

ACCOUNTS_FILE = str(Path(__file__).resolve().parents[1] / "accounts.json")


class CollectionManager:
    """采集调度核心服务"""

    def __init__(self):
        self.config = Config.from_env()
        self.screenshot = PriceScreenshot(
            output_dir=os.getenv("SCREENSHOT_DIR", "./data/screenshots"),
        )
        self.account_pool = AccountPool(pool_file=ACCOUNTS_FILE)

    # ── Public API ──

    async def start_full_scan(
        self,
        keyword: str = None,
        triggered_by: str = "manual",
    ) -> ScrapeJob:
        """启动全量扫描 (所有平台 × 所有关键词)"""
        factory = get_session_factory()
        session = factory()
        try:
            job = crud.create_job(session, {
                "job_type": "FULL_SCAN",
                "keyword": keyword,
                "triggered_by": triggered_by,
                "status": "PENDING",
            })
            session.commit()
            session.refresh(job)  # load server-default columns (created_at etc.)
            job_id = job.id
            session.expunge(job)  # detach before close
        finally:
            session.close()

        # 在后台协程中执行
        asyncio.ensure_future(self._run_full_scan(job_id, keyword))
        return job

    async def start_platform_scan(
        self,
        platform: str,
        keyword: str = None,
        triggered_by: str = "manual",
    ) -> ScrapeJob:
        """启动单平台扫描"""
        factory = get_session_factory()
        session = factory()
        try:
            job = crud.create_job(session, {
                "job_type": "PLATFORM_SCAN",
                "platform": platform,
                "keyword": keyword,
                "triggered_by": triggered_by,
                "status": "PENDING",
            })
            session.commit()
            session.refresh(job)
            job_id = job.id
            session.expunge(job)
        finally:
            session.close()

        asyncio.ensure_future(self._run_platform_scan(job_id, platform, keyword))
        return job

    async def start_single_scrape(
        self,
        platform: str,
        url: str,
        triggered_by: str = "manual",
    ) -> ScrapeJob:
        """启动单 URL 采集"""
        factory = get_session_factory()
        session = factory()
        try:
            job = crud.create_job(session, {
                "job_type": "SINGLE_URL",
                "platform": platform,
                "target_url": url,
                "triggered_by": triggered_by,
                "status": "PENDING",
            })
            session.commit()
            session.refresh(job)
            job_id = job.id
            session.expunge(job)
        finally:
            session.close()

        asyncio.ensure_future(self._run_single_scrape(job_id, platform, url))
        return job

    @staticmethod
    def cancel_job(job_id: int) -> bool:
        """取消运行中任务"""
        if job_id in _active_jobs:
            _active_jobs[job_id] = True  # set cancelled flag
            return True
        # 也尝试更新 DB 中的状态
        factory = get_session_factory()
        session = factory()
        try:
            job = crud.get_job(session, job_id)
            if job and job.status in ("PENDING", "RUNNING"):
                crud.update_job_status(session, job_id, "CANCELLED")
                session.commit()
                return True
            return False
        finally:
            session.close()

    @staticmethod
    def get_job_status(job_id: int) -> Optional[dict]:
        """获取单任务状态"""
        factory = get_session_factory()
        session = factory()
        try:
            job = crud.get_job(session, job_id)
            if not job:
                return None
            return _job_to_dict(job)
        finally:
            session.close()

    @staticmethod
    def list_platform_status() -> list[dict]:
        """每平台最近任务 + 成功率 (看板用)"""
        factory = get_session_factory()
        session = factory()
        try:
            registered = list_supported_platforms()
            latest_jobs = crud.get_latest_jobs_by_platform(session)
            job_map = {j.platform: j for j in latest_jobs}

            result = []
            for p in registered:
                job = job_map.get(p)
                result.append({
                    "platform": p,
                    "last_job": _job_to_dict(job) if job else None,
                    "registered": True,
                })
            return result
        finally:
            session.close()

    # ── Internal execution ──

    async def _run_full_scan(self, job_id: int, keyword: str = None):
        """执行全量扫描"""
        factory = get_session_factory()
        _active_jobs[job_id] = False  # not cancelled
        start_time = time.time()

        with factory() as session:
            try:
                # 标记开始
                crud.update_job_status(
                    session, job_id, "RUNNING",
                    started_at=datetime.utcnow(),
                )
                session.commit()

                # 获取关键词
                keywords_objs = crud.get_active_keywords(session)
                if keyword:
                    keywords_objs = [k for k in keywords_objs if k.keyword == keyword]
                if not keywords_objs:
                    crud.update_job_status(
                        session, job_id, "SUCCESS",
                        finished_at=datetime.utcnow(),
                        error_message="No active keywords found",
                    )
                    session.commit()
                    return
                keywords_list = [k.keyword for k in keywords_objs]
            except Exception as e:
                log.error(f"[Job:{job_id}] Init failed: {e}")
                return

        platforms = list_supported_platforms()
        total_steps = len(keywords_list) * len(platforms)
        step = 0
        total_offers = 0
        total_violations = 0
        total_fails = 0
        total_p0 = 0
        total_p1 = 0

        try:
            for kw in keywords_list:
                log.info(f"[Job:{job_id}] Scanning keyword: {kw}")
                kw_offers = []

                for plat in platforms:
                    with factory() as session:
                        job_record = crud.get_job(session, job_id)
                        if _active_jobs.get(job_id) or (job_record and job_record.status == "CANCELLED"):
                            raise asyncio.CancelledError("Job cancelled by user")

                    step += 1
                    progress = int(step / total_steps * 100)

                    try:
                        offers = await self._scrape_one(plat, kw)
                        kw_offers.extend(offers)
                        log.info(f"  [{plat}] {len(offers)} offers")
                    except Exception as e:
                        total_fails += 1
                        log.error(f"  [{plat}] Scrape failed: {e}")

                    # 更新进度
                    with factory() as session:
                        try:
                            crud.update_job_progress(
                                session, job_id,
                                progress=progress,
                                success_items=total_offers + len(kw_offers),
                                fail_items=total_fails,
                                total_items=total_steps,
                            )
                            session.commit()
                        except Exception as e:
                            log.error(f"  Failed to update progress: {e}")

                # 写入 DB + 违规判定
                if kw_offers:
                    with factory() as session:
                        try:
                            session.add_all(kw_offers)
                            session.commit()

                            violations = process_offers(session, kw_offers)
                            total_offers += len(kw_offers)
                            total_violations += len(violations)

                            # 通知
                            for v in violations:
                                if not v.is_whitelisted:
                                    if v.severity == "P0":
                                        total_p0 += 1
                                    elif v.severity == "P1":
                                        total_p1 += 1
                                    try:
                                        notify_violation(v)
                                        v.notified = True
                                    except Exception as e:
                                        log.error(f"  Notify failed: {e}")
                            session.commit()
                        except Exception as e:
                            session.rollback()
                            log.error(f"  [DB Save] Failed for keyword {kw}: {e}")
                            total_fails += len(kw_offers)

            duration = time.time() - start_time

            # 完成
            with factory() as session:
                crud.update_job_status(
                    session, job_id, "SUCCESS",
                    finished_at=datetime.utcnow(),
                    total_items=total_offers,
                    success_items=total_offers,
                    violations_found=total_violations,
                    progress=100,
                )
                session.commit()

            # 推送汇总
            try:
                notify_scan_summary(
                    keyword=", ".join(keywords_list[:3]),
                    total_offers=total_offers,
                    new_violations=total_violations,
                    p0_count=total_p0,
                    p1_count=total_p1,
                    duration_sec=duration,
                )
            except Exception as e:
                log.error(f"Summary notify failed: {e}")

            log.info(
                f"[Job:{job_id}] Full scan complete: "
                f"{total_offers} offers, {total_violations} violations in {duration:.1f}s"
            )

        except asyncio.CancelledError:
            with factory() as session:
                crud.update_job_status(
                    session, job_id, "CANCELLED",
                    finished_at=datetime.utcnow(),
                )
                session.commit()
            log.info(f"[Job:{job_id}] Cancelled")

        except Exception as e:
            log.error(f"[Job:{job_id}] Failed: {e}", exc_info=True)
            with factory() as session:
                try:
                    crud.update_job_status(
                        session, job_id, "FAILED",
                        error_message=str(e)[:2000],
                        finished_at=datetime.utcnow(),
                    )
                    session.commit()
                except Exception:
                    pass

        finally:
            _active_jobs.pop(job_id, None)

    async def _run_platform_scan(self, job_id: int, platform: str, keyword: str = None):
        """执行单平台扫描"""
        factory = get_session_factory()
        _active_jobs[job_id] = False
        start_time = time.time()

        with factory() as session:
            try:
                crud.update_job_status(
                    session, job_id, "RUNNING",
                    started_at=datetime.utcnow(),
                )
                session.commit()

                keywords_objs = crud.get_active_keywords(session)
                if keyword:
                    keywords_objs = [k for k in keywords_objs if k.keyword == keyword]
            
                keywords_list = [k.keyword for k in keywords_objs]
            except Exception as e:
                log.error(f"[Job:{job_id}] Init failed: {e}")
                return

        total_offers = 0
        total_violations = 0
        total_fails = 0
        total_steps = max(len(keywords_list), 1)

        try:
            for i, kw in enumerate(keywords_list):
                with factory() as session:
                    job_record = crud.get_job(session, job_id)
                    if _active_jobs.get(job_id) or (job_record and job_record.status == "CANCELLED"):
                        raise asyncio.CancelledError()

                try:
                    offers = await self._scrape_one(platform, kw)
                    if offers:
                        with factory() as session:
                            try:
                                session.add_all(offers)
                                session.commit()
                                violations = process_offers(session, offers)
                                total_offers += len(offers)
                                total_violations += len(violations)
                            except Exception as e:
                                session.rollback()
                                log.error(f"[DB Save] Failed for keyword {kw}: {e}")
                                total_fails += len(offers)
                except Exception as e:
                    total_fails += 1
                    log.error(f"[{platform}] keyword={kw} failed: {e}")

                with factory() as session:
                    try:
                        crud.update_job_progress(
                            session, job_id,
                            progress=int((i + 1) / total_steps * 100),
                            success_items=total_offers,
                            fail_items=total_fails,
                            total_items=total_steps,
                            violations_found=total_violations,
                        )
                        session.commit()
                    except Exception as e:
                        log.error(f"Failed to update progress: {e}")

            with factory() as session:
                crud.update_job_status(
                    session, job_id, "SUCCESS",
                    finished_at=datetime.utcnow(),
                    total_items=total_offers,
                    success_items=total_offers,
                    violations_found=total_violations,
                    progress=100,
                )
                session.commit()

        except asyncio.CancelledError:
            with factory() as session:
                crud.update_job_status(session, job_id, "CANCELLED",
                                       finished_at=datetime.utcnow())
                session.commit()
        except Exception as e:
            log.error(f"[Job:{job_id}] Failed: {e}", exc_info=True)
            with factory() as session:
                try:
                    crud.update_job_status(session, job_id, "FAILED",
                                           error_message=str(e)[:2000],
                                           finished_at=datetime.utcnow())
                    session.commit()
                except Exception:
                    pass
        finally:
            _active_jobs.pop(job_id, None)

    async def _run_single_scrape(self, job_id: int, platform: str, url: str):
        """执行单 URL 采集"""
        factory = get_session_factory()
        _active_jobs[job_id] = False

        with factory() as session:
            try:
                crud.update_job_status(
                    session, job_id, "RUNNING",
                    started_at=datetime.utcnow(),
                )
                session.commit()
            except Exception as e:
                log.error(f"[Job:{job_id}] Init failed: {e}")
                return

        try:
            # 使用注册表创建 scraper
            plat_enum = Platform(platform)
            scraper = create_scraper(
                plat_enum, self.config,
                self.screenshot, self.account_pool,
            )
            task = ScrapeTask(
                platform=plat_enum,
                product_url=url,
                keyword="",
            )
            result = await scraper.scrape_product(task)

            total_items = 0
            violations_count = 0

            if result:
                offer = self._product_to_offer(result, platform, "", url)
                with factory() as session:
                    session.add(offer)
                    session.commit()
                    total_items = 1

                    violations = process_offers(session, [offer])
                    violations_count = len(violations)
                    # For safety if there's any updates
                    session.commit()

            with factory() as session:
                crud.update_job_status(
                    session, job_id, "SUCCESS",
                    finished_at=datetime.utcnow(),
                    total_items=total_items,
                    success_items=total_items,
                    violations_found=violations_count,
                    progress=100,
                )
                session.commit()

        except Exception as e:
            log.error(f"[Job:{job_id}] Single scrape failed: {e}", exc_info=True)
            with factory() as session:
                try:
                    crud.update_job_status(session, job_id, "FAILED",
                                           error_message=str(e)[:2000],
                                           finished_at=datetime.utcnow())
                    session.commit()
                except Exception:
                    pass
        finally:
            _active_jobs.pop(job_id, None)

    async def _scrape_one(
        self, platform: str, keyword: str,
    ) -> list[OfferSnapshot]:
        """用注册表 scraper 采集单平台单关键词, 返回 OfferSnapshot 列表"""
        try:
            plat_enum = Platform(platform)
        except ValueError:
            log.warning(f"Unsupported platform: {platform}")
            return []

        try:
            scraper = create_scraper(
                plat_enum, self.config,
                self.screenshot, self.account_pool,
            )
        except ValueError as e:
            log.warning(f"Scraper not available: {e}")
            return []

        from urllib.parse import quote
        kw_enc = quote(keyword)
        search_urls = _get_search_urls(platform, kw_enc)

        offers = []

        # ── 优先路径: scrape_search() 返回多商品列表 ──
        if hasattr(scraper, "scrape_search"):
            try:
                products = await scraper.scrape_search(keyword, max_items=5)
                for product in products:
                    offer = self._product_to_offer(product, platform, keyword, product.product_url)
                    offers.append(offer)
                if offers:
                    log.info(f"[{platform}] scrape_search() returned {len(offers)} offers for '{keyword}'")
                    return offers
                else:
                    log.warning(f"[{platform}] scrape_search() returned 0 results, "
                                f"falling back to product page scraping (url count: {len(search_urls)})")
            except Exception as e:
                log.error(f"[{platform}] scrape_search() failed: {e}", exc_info=True)

        # ── 降级路径: 逐 URL 调用 scrape_product() ──
        for url in search_urls:
            task = ScrapeTask(platform=plat_enum, product_url=url, keyword=keyword)
            try:
                result = await scraper.scrape_product(task)
                if result:
                    offer = self._product_to_offer(result, platform, keyword, url)
                    offers.append(offer)
            except Exception as e:
                log.warning(f"  [{platform}] scrape error for {url[:60]}: {e}")

        return offers

    @staticmethod
    def _product_to_offer(
        product: ProductPrice, platform: str, keyword: str, url: str,
    ) -> OfferSnapshot:
        """将 scraper 返回的 ProductPrice 转换为 OfferSnapshot"""
        now = datetime.utcnow()
        # Include product_id or url to prevent false dedup when two products share the same name/shop/hour
        product_id_part = getattr(product, "product_id", None) or url or ""
        identifier = f"{product.product_name or ''}|{product.shop_name or ''}|{product_id_part[:80]}"
        offer_hash = crud.make_offer_hash(platform, identifier)

        raw_price = Decimal("0")
        try:
            raw_price = Decimal(str(product.current_price)) if product.current_price else Decimal("0")
        except (InvalidOperation, ValueError):
            pass

        final_price = Decimal("0")
        try:
            final_price = Decimal(str(product.final_price)) if product.final_price else raw_price
        except (InvalidOperation, ValueError):
            final_price = raw_price

        original_price = Decimal("0")
        try:
            original_price = Decimal(str(product.original_price)) if product.original_price else Decimal("0")
        except (InvalidOperation, ValueError):
            pass

        screenshot_path = product.screenshot_local
        screenshot_hash = None
        if screenshot_path and os.path.exists(screenshot_path):
            try:
                with open(screenshot_path, "rb") as f:
                    file_hash = hashlib.sha256(f.read()).hexdigest()
                screenshot_hash = file_hash
            except Exception as e:
                log.error(f"Failed to calculate hash for screenshot: {e}")

        return OfferSnapshot(
            offer_hash=offer_hash,
            platform=platform,
            keyword=(keyword or "")[:100],
            canonical_url=(product.product_url or url)[:500],
            product_name=(product.product_name or "")[:300],
            product_id=(product.product_id or "")[:100],
            shop_name=(product.shop_name or "")[:100],
            ship_from_city=(product.ship_from_city or "")[:50],
            raw_price=raw_price,
            final_price=final_price,
            original_price=original_price,
            coupon_info=[c.__dict__ for c in product.coupons] if product.coupons else None,
            sales_volume=(product.sales_volume or "")[:50],
            confidence="HIGH",
            parse_status="OK",
            captured_at=now,
            screenshot_path=(screenshot_path or "")[:500],
            screenshot_hash=screenshot_hash,
        )


def _get_search_urls(platform: str, kw_enc: str) -> list[str]:
    """各平台搜索 URL 映射

    使用移动端 URL，与 Cookie 采集时的域名保持一致（m.jd.com / m.taobao.com）。
    """
    mapping = {
        # ── 移动端搜索页，Cookie 域匹配 ──
        "jd_express": [f"https://so.m.jd.com/ware/search.action?keyword={kw_enc}"],
        "taobao": [f"https://s.m.taobao.com/search?q={kw_enc}"],
        "tmall": [f"https://s.m.taobao.com/search?q={kw_enc}&tab=tmall"],
        "pinduoduo": [f"https://mobile.yangkeduo.com/search_result.html?search_key={kw_enc}"],
        # ── 淘宝闪购：m 端搜索 + tab=sg，TaobaoFlashScraper 负责 API 拦截 ──
        "taobao_flash": [f"https://s.m.taobao.com/h5?q={kw_enc}&tab=sg"],
        # ── 其余平台 Cookie 未采集，使用 fallback 单品 URL ──
        "douyin": ["https://haohuo.douyin.com/pages/ecom_detail/index?page_id=356891"],
        "meituan_flash": ["https://h5.waimai.meituan.com/waimai/mindex/product?spuId=1230485"],
        "xiaohongshu": ["https://www.xiaohongshu.com/goods/64b5e8b0000000001500abc1"],
        "pupu": ["https://j1.pupumall.com/share/product?productId=100435"],
        "xiaoxiang": ["https://mall.meituan.com/product/58102"],
        "dingdong": ["https://maicai.api.ddxq.mobi/product/detail?product_id=89234"],
        "community_group": ["https://mobile.yangkeduo.com/goods.html?goods_id=452179836"],
    }
    return mapping.get(platform, [])


def _job_to_dict(job: ScrapeJob) -> dict:
    """ScrapeJob → API JSON"""
    return {
        "id": job.id,
        "job_type": job.job_type,
        "platform": job.platform,
        "keyword": job.keyword,
        "target_url": job.target_url,
        "status": job.status,
        "progress": job.progress,
        "total_items": job.total_items,
        "success_items": job.success_items,
        "fail_items": job.fail_items,
        "violations_found": job.violations_found,
        "error_message": job.error_message,
        "triggered_by": job.triggered_by,
        "started_at": job.started_at.isoformat() + "Z" if job.started_at else None,
        "finished_at": job.finished_at.isoformat() + "Z" if job.finished_at else None,
        "created_at": job.created_at.isoformat() + "Z" if job.created_at else None,
    }
