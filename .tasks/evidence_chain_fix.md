# Evidence Chain & Pricing Gap Analysis
  
## 1. 原型 DRD 要求回顾
根据 `docs/kashi/Antigravity_DRD_v2.md` 的要求：
- **FR-301~304 证据链（截图）**：必须输出主页面/券弹窗截图，且需带有“时间/平台/url短码/城市点位/任务id”的水印，同时生成 `integrity_hash` （防篡改哈希）。
- **FR-201~202 价格计算**：需要包含 `discount_breakdown` (券叠加细则) 和规范的 `coupon_list`，做到可解释“低在哪里”。

## 2. 现状代码分析
经过对 `collection_manager.py` 和全体 scraper 的审计，得出以下结论：
1. **截图功能被“架空” (The Screenshot Evidence Gap)**
   - **发生机制**：目前每个 scraper 虽然都在各自的逻辑里执行了 `await page.screenshot(path=...)` 并给 `ProductPrice` 的 `screenshot_local` 赋了值，但在 `collection_manager.py` 的数据打平组装函数 `_product_to_offer()` 内部，**完全丢弃了关于截图的所有字段**（`screenshot_local` 未向 `OfferSnapshot.screenshot_path` 映射）。
   - **后果**：数据库里的 `screenshot_path` 永远为空，UI 无法展示取证图片。
2. **水印与防篡改哈希从未调用**
   - **发生机制**：`price_monitor.screenshot` 里虽然写了 `add_timestamp_watermark` 方法，但全局代码里没有任何一个 scraper 去调用它。同样，也没有任何地方计算过真正的图片 `integrity_hash`。

## 3. IMPLEMENTATION CHECKLIST

1. **改造截图引擎 (price_monitor/screenshot.py)**
   - 修改 `PriceScreenshot.capture_full_page` 和 `capture_element` 方法，在内部执行 `page.screenshot()` 之前，统一切面注入 `await self.add_timestamp_watermark(page)` 生成水印。
2. **统一所有 Scraper 的截图调用 (price_monitor/scrapers/*.py)**
   - 遍历 12 个爬虫文件（如 `jd_express.py`, `taobao.py`, `douyin.py` 等），将原生的 `await page.screenshot(path=...)` 替换为调用封装好的 `await self.screenshot.capture_full_page(page, filename=...)` 方法，实现底层逻辑的彻底解耦和收拢。
3. **补齐数据库入库映射与防篡改 Hash 计算 (price_monitor/collection_manager.py)**
   - 在 `CollectionManager._product_to_offer` 中，提取 `product.screenshot_local`。
   - 增加文件读取逻辑，使用 `hashlib.sha256` 即时计算文件的完整性哈希。
   - 将路径映射至 `OfferSnapshot.screenshot_path`，哈希映射至 `OfferSnapshot.screenshot_hash`，真正打通持久化。
4. **开放静态资源路由 (price_monitor/api/app.py)**
   - 在 FastAPI 顶层使用 `StaticFiles` 挂载 `./data/screenshots` 或者对应的 `SCREENSHOT_DIR` 目录到 `/screenshots` HTTP 路由，使得前端可以通过 URL 访问到截图证据。
5. **升级 API 中间层映射 (price_monitor/api/crud.py / app.py)**
   - 确保 `list_offers` 或前端请求的 JSON 返回体中正确携带并暴露出 `screenshot_path` 字段。
6. **前端证据链闭环渲染 (web/src/app/offers/page.tsx)**
   - 在原本的价格详情弹窗（Modal）中，新增一个专属的“取证截图（Evidence）”图片展示区域。如果 `screenshot_path` 存在，则按挂载的 HTTP 静态路径直接渲染包含水印的取证图。
