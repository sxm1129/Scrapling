"""
jd.py — 京东/京东秒送 Playwright 行为仿真采集器
==================================================
策略:
  so.m.jd.com (移动版搜索) → item.m.jd.com (移动版详情页)
  Cookie 注入后可获取真实到手价（否则部分价格掩码 ¥1??9）
"""
import asyncio
import logging
import re
from decimal import Decimal
from urllib.parse import quote
from typing import Optional

from price_monitor.playwright_engine.base_scraper import (
    BasePlaywrightScraper, ProductDetail, SearchResult, CouponDetail
)

log = logging.getLogger("price_monitor.playwright_engine.scrapers.jd")

_SEARCH_URL = "https://so.m.jd.com/ware/search.action?keyword={keyword}"

JS_JD_LIST = """() => {
    // ─── 策略1：从页面 JS 全局对象里提取 SKU 列表 ───
    const skuIds = [];
    const skuPattern = /"skuId"\\s*:\\s*"?(\\d{5,})/g;
    const scriptEls = Array.from(document.querySelectorAll('script'));
    for (const s of scriptEls) {
        const text = s.textContent || '';
        if (!text || text.length < 50) continue;
        let m;
        skuPattern.lastIndex = 0;
        while ((m = skuPattern.exec(text)) !== null && skuIds.length < 30) {
            const id = m[1];
            if (!skuIds.includes(id)) skuIds.push(id);
        }
    }

    // ─── 策略2：解析 body.innerText 文本块 ───
    const bodyText = document.body.innerText || '';
    const lines = bodyText.split('\\n').map(l => l.trim()).filter(l => l.length > 0);

    const items = [];
    const seenTitles = new Set();
    let i = 0;
    while (i < lines.length && items.length < 15) {
        const line = lines[i];
        // 价格行特征：¥ 12.3 或 到手价 ¥ 45.6
        const priceM = line.match(/(?:到手价|政府补贴价|¥|￥|\\?)\\s*([\\d,]+\\.?\\d*)/);
        if (priceM && !line.includes('?')) { // 过滤掉掩码价格 ¥1??9
            const price = priceM[1].replace(',', '');
            
            // 往前找标题：找最近的、长于 10 字符、包含中文的非价格行
            let title = '';
            for (let j = i - 1; j >= Math.max(0, i - 10); j--) {
                const tl = lines[j];
                if (/[\\u4e00-\\u9fa5]{4,}/.test(tl) && tl.length > 10 && !/[¥￥]/.test(tl)) {
                    title = tl;
                    break;
                }
            }
            
            // 往后找店铺名
            let shop = '';
            for (let j = i + 1; j < Math.min(i + 8, lines.length); j++) {
                const sl = lines[j];
                if (sl.includes('旗舰店') || sl.includes('自营') || sl.includes('专卖店') || sl.includes('超市')) {
                    shop = sl;
                    break;
                }
            }

            if (title && price && !seenTitles.has(title.slice(0, 30))) {
                seenTitles.add(title.slice(0, 30));
                items.push({ 
                    title: title.slice(0, 150), 
                    price, 
                    shop: shop.slice(0, 80),
                    skuId: ''
                });
            }
        }
        i++;
    }

    // ─── 关联 SKU ID ───
    // 很多时候 body.innerText 中的商品顺序与脚本中的 skuId 顺序一致
    for (let j = 0; j < items.length && j < skuIds.length; j++) {
        items[j].skuId = skuIds[j];
        items[j].url = `https://item.m.jd.com/product/${skuIds[j]}.html`;
    }

    // 格式化输出
    const result = items.map(it => ({
        url: it.url || '',
        sku_id: it.skuId || '',
        price: it.price,
        title: it.title,
        shop: it.shop
    }));

    return {
        items: result,
        is_login: window.location.href.includes('passport.jd.com') || window.location.href.includes('plogin'),
        url: window.location.href,
        debug: {
            skuIdsFound: skuIds.length,
            itemsFound: items.length,
            bodyLen: bodyText.length
        }
    };
}"""


JS_JD_DETAIL = """() => {
    const result = {};
    // window._itemOnly (SSR 数据)
    try {
        const content = document.documentElement.innerHTML;
        const m = content.match(/window\._itemOnly\\s*=\\s*(\\{.+?\\});/s);
        if (m) {
            const d = JSON.parse(m[1]);
            result.sku_name = d.item?.skuName || '';
            result.brand_name = d.item?.brandName || '';
        }
    } catch(e) {}

    result.price_elements = [];
    const seen = new Set();
    for (const sel of ["[class*='price']", "[class*='Price']", "[class*='jdPrice']", "span[class*='yuan']"]) {
        for (const el of document.querySelectorAll(sel)) {
            const t = (el.innerText || '').trim();
            if (t && /\\d/.test(t) && !t.includes('??') && t.length < 50 && !seen.has(t)) {
                seen.add(t);
                result.price_elements.push({ cls: el.className.slice(0, 60), text: t });
            }
        }
    }
    result.has_masked = (document.body.innerText || '').includes('??');
    result.title = (document.querySelector('h1, [class*="goodsName"], .fn_goods_name')?.innerText || result.sku_name || '').trim().slice(0, 200);
    const shopEl = document.querySelector('[class*="shop"], [class*="seller"]');
    result.shop_name = shopEl ? shopEl.innerText.trim().slice(0, 80) : (result.brand_name || '');
    result.coupons = [];
    document.querySelectorAll('[class*="coupon"], [class*="promo"], [class*="quan"]').forEach(el => {
        const t = (el.innerText || '').trim();
        if (t && t.length > 2 && t.length < 100) result.coupons.push(t);
    });
    const addrEl = document.querySelector('[class*="addr"], [class*="deliver"]');
    result.ship_city = addrEl ? addrEl.innerText.trim().slice(0, 30) : '';
    result.price_lines = (document.body.innerText || '').split('\\n').filter(
        l => (l.includes('¥') || l.includes('￥')) && !l.includes('??') && l.length < 80
    ).slice(0, 15);
    result.is_login = window.location.href.includes('plogin') || window.location.href.includes('passport.jd.com');
    return result;
}"""


class JDPlaywrightScraper(BasePlaywrightScraper):
    platform = "jd_express"
    search_result_selector = "ul.m-goods-list > li"
    login_page_indicators = ["plogin.m.jd.com", "passport.jd.com", "login"]

    async def search(self, page, keyword: str, human, limit: int = 10) -> list[SearchResult]:
        import os  # Used for screenshot folder
        url = _SEARCH_URL.format(keyword=quote(keyword))
        log.info(f"[jd] Searching: {url}")

        # 等待 networkidle 让 JS 渲染完成
        try:
            await page.goto(url, timeout=35_000, wait_until="networkidle")
        except Exception:
            log.warning("[jd] networkidle timeout, trying to extract anyway")

        final_url = page.url
        # 检测风控验证页
        if "risk_handler" in final_url or "京东验证" in await page.title():
            log.warning(f"[jd] Risk verification page detected at: {final_url}")
            log.warning("[jd] Cookie may be valid but IP risk triggered — waiting 5s for JS redirect")
            await asyncio.sleep(5)
            final_url = page.url

        if "risk_handler" in final_url:
            log.error("[jd] Still on risk page after wait — aborting")
            return []

        # 注入 CSS 隐藏所有可能的弹窗/遮罩，避免干扰提取
        try:
            await page.evaluate("""() => {
                const style = document.createElement('style');
                style.innerHTML = `
                    [class*="modal"], [class*="mask"], [class*="dialog"], 
                    [class*="popup"], [class*="toast"], [class*="qr"],
                    .mod_alert, .mod_loading { 
                        display: none !important; 
                        visibility: hidden !important; 
                        pointer-events: none !important; 
                        opacity: 0 !important;
                    }
                `;
                document.head.appendChild(style);
                
                // 尝试点击一些关闭按钮
                document.querySelectorAll('[class*="close"], .close-btn').forEach(btn => {
                    if (btn.offsetParent !== null) { // visible
                        try { btn.click(); } catch(e) {}
                    }
                });
            }""")
        except Exception:
            pass

        await asyncio.sleep(3)
        
        # 等待 body 渲染
        try:
            await page.wait_for_function(
                "() => (document.body.innerText || '').length > 500",
                timeout=10_000
            )
        except Exception:
            log.warning("[jd] Body content wait timeout")

        data = await page.evaluate(JS_JD_LIST)
        
        if data.get("is_login"):
            log.warning("[jd] Redirected to login during search")
            return []

        items = data.get("items", [])
        debug_info = data.get("debug", {})
        log.info(f"[jd] Found {len(items)} results (skuIds: {debug_info.get('skuIdsFound')}, textItems: {debug_info.get('itemsFound')})")

        if not items:
            # 抓个失败现场截图
            try:
                os.makedirs("data/screenshots/debug", exist_ok=True)
                path = f"data/screenshots/debug/jd_search_fail_{int(asyncio.get_event_loop().time())}.png"
                await page.screenshot(path=path)
                log.error(f"[jd] Zero results. Debug info: {debug_info}. Saved screenshot to {path}")
            except Exception as e:
                log.error(f"[jd] Failed to capture debug screenshot: {e}")

        results = []
        for item in items[:limit]:
            price_str = item.get("price", "")
            price = Decimal(price_str) if price_str else None
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                display_price=price,
                shop_name=item.get("shop", ""),
            ))
        return results

    async def get_detail(self, page, url: str, keyword: str, human, screenshot_dir: str = "./data/screenshots") -> ProductDetail:
        log.info(f"[jd] Getting detail: {url}")
        await page.goto(url, timeout=30_000, wait_until="domcontentloaded")
        try:
            await page.wait_for_selector("[class*='price'], .fn_goods_name", timeout=15_000)
        except Exception:
            log.warning("[jd] Price selector timeout on detail page")

        await human.simulate_reading(3)

        if self.is_login_page(page.url):
            log.warning(f"[jd] Redirected to login: {page.url}")
            return ProductDetail(platform=self.platform, keyword=keyword, url=url, error="login_required")

        data = await page.evaluate(JS_JD_DETAIL)
        screenshot_path = await self.take_screenshot(page, screenshot_dir, "detail")
        display_price = self._extract_price(data)

        coupons = [CouponDetail("UNKNOWN", None, Decimal("0"), raw_text=t)
                   for t in data.get("coupons", [])[:5] if t]

        return ProductDetail(
            platform=self.platform, keyword=keyword, url=url,
            title=data.get("title", ""),
            display_price=display_price, final_price=display_price,
            is_login_required_for_price=data.get("has_masked", False),
            coupons=coupons,
            shop_name=data.get("shop_name", ""),
            ship_from_city=self._extract_city(data.get("ship_city", "")),
            screenshot_path=screenshot_path,
        )

    def _extract_price(self, data: dict) -> Optional[Decimal]:
        for pe in data.get("price_elements", []):
            try:
                m = re.search(r"(\d+\.?\d*)", pe["text"].replace(",", ""))
                if m:
                    v = Decimal(m.group(1))
                    if Decimal("1") < v < Decimal("99999"):
                        return v
            except Exception:
                pass
        for line in data.get("price_lines", []):
            m = re.search(r"[¥￥](\d+\.?\d*)", line)
            if m:
                try:
                    return Decimal(m.group(1))
                except Exception:
                    pass
        return None

    @staticmethod
    def _extract_city(text: str) -> str:
        m = re.search(r"([\u4e00-\u9fa5]{2,4}(?:市|区|仓|省))", text)
        return m.group(1) if m else text.strip()[:10]

