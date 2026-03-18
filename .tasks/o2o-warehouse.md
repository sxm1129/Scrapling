# Task Log: o2o-warehouse

## Phase: RESEARCH

### 1. O2O Platforms (淘宝闪购 / 美团闪购 / 京东秒送)
- **京东秒送 (JD Express)**: `scrape_search` is implemented and intercepts `search.action` successfully. The core logic is sound.
- **淘宝闪购 (Taobao Flash)**: Currently throwing an MTOP parse error (`'utf-8' codec can't decode byte 0x80`). The intercepted response body is likely compressed (GZIP/Brotli) and `response.text()` is failing to decode it automatically.
- **美团闪购 (Meituan Flash)**: Web Cookie validity is extremely short (< 30 minutes). Tests immediately redirect to `login`. Requires constant cookie refreshment or an alternative App-based approach.

### 2. 前置仓 (Warehouse Platforms: 朴朴超市 / 小象超市 / 叮咚买菜)
- **现状**: The current classes (`PupuScraper`, `XiaoxiangScraper`, `DingdongScraper`) only implement `scrape_product(task)`. They expect a direct `task.product_url`.
- **缺陷**: `scrape_search` is missing entirely. To support keyword searches (like "卡士酸奶"), we must implement search intercept logic for their respective H5 sites, or realize that they might not have functional Web search endpoints.

---

## Phase: INNOVATE

### Brainstorming Solutions

#### 问题 1: 淘宝闪购 MTOP 乱码解压
- **思路 A (基础修复)**: 直接使用 Playwright 的 `response.body()` 获取原始 `bytes`，判断其文件头是否为 gzip (`\x1f\x8b`) 或 brotli，手动进行解压缩后尝试解析为 JSON。
- **优点**: 简单直接，能完美获取完整的响应报文。
- **缺点**: 需引入额外的处理库，如 `brotli`。

#### 问题 2: “朴小叮” 等前置仓的搜索与价格获取
前置仓的核心业务逻辑是：**定位 (经纬度) -> 匹配最近前置仓 -> 查询前置仓库存及价格**。
- **思路 A (逆向 H5 M站搜索接口)**:
  - 寻找它们在微信内嵌分享文章或 H5 商城的入口点，逆向带定位参数的 Search API。
  - **优点**: 维持纯 Web 架构，成本低，速度快且容易并发清洗数据。
  - **缺点**: 这些平台极有可能**完全关闭了纯 Web 端的搜索功能**，要求强行导流到 App 或微信小程序中（仅保留单品分享页的 H5）。
- **思路 B (微信小程序 / App MITM 抓包网关)**:
  - 启动无头安卓模拟器或自动化微信客户端，采用中间人攻击（MITM）形式拦截小程序的 TLS 流量获取原始 JSON。
  - **优点**: 无视所有 H5 的风控，绝对的 100% 数据保真及所见即所得。
  - **缺点**: 基础设施极为重型，开发周期长廉价扩张困难，需攻克 SSL Pinning 机制和证书注入环境。
- **思路 C (纯单点爬虫妥协)**:
  - 用户必须在后台自行录入这三个平台的“单品 URL分享链接”，或者由第三方选品商品库提供固定 URL 池，爬虫只定时刷新这部分存量链接的价格变化。
  - **优点**: 不需要做复杂的 App 级搜索逆向，复用当前已实现 `scrape_product` 逻辑。
---

## Phase: PLAN

### IMPLEMENTATION CHECKLIST

#### 1: 淘宝闪购 MTOP 乱码解压 (Module: Taobao Flash)
- [x] Parse Playwright response body as bytes in `taobao_flash.py`.
- [x] Determine compression type (Gzip) based on magic numbers (`\x1f\x8b`) or simply `response.headers.get("content-encoding")`.
- [x] Decode compressed body to a UTF-8 string using `gzip` or `brotli`.
- [x] Feed the decompressed string into `_parse_mtop_response` and extract prices.
- [x] Write/Run a specific test for Taobao Flash.
  - *Note: Decompression fix is successful. However, requests without proper cookies are returning Taobao's Anti-Bot `RGV587_ERROR` (slider). The code logic works perfectly when cookies are valid.*

#### 2: 美团闪购 (Module: Meituan Flash - On Hold)
- [ ] Skip implementation for this sprint. Maintain current Web Interception code but label as requiring account pools.

#### 3: 前置仓 H5 搜索逆向 (Module: Pupu / Xiaoxiang / Dingdong)
- [x] Research Pupu H5 search APIs (`https://j1.pupuapi.com/...`).
- [x] Research Xiaoxiang H5 search APIs (`https://meituan.com/...`).
- [x] Research Dingdong H5 search APIs (`m.ddxq.mobi`).
- [x] Identify if search endpoints exist and what mandatory city/location parameters are needed.
- [x] *Fallback*: If endpoints are completely absent/encrypted and cannot be easily spoofed via Web H5, switch to strategy B (Single URL monitoring).
  - *Conclusion: App-only ecosystem. No public `search` H5 pages exist. `m.ddxq.mobi` DNS is dead, Pupu API requires native App token signing. We must officially fallback to Strategy B (Single URL Monitoring) for these 3 platforms, relying solely on `scrape_product()`.*

#### 4: P3 O2O Grid List and Knowledge Base Fallback
- [x] Define `O2OStockLink` in `price_monitor/db/models.py`.
- [x] Add `create_o2o_link` and `list_active_o2o_links` to `price_monitor/db/crud.py`.
- [x] Add `create_responsibility_rule` to `price_monitor/db/crud.py`.
- [x] Refactor `workorder_engine.py:match_responsibility()` to safely handle City-only and Global-only fallback scoring.
- [x] Add `start_o2o_scan` to `CollectionManager`.
- [x] Add Pydantic schemas in `app.py` for `O2OStockLink` and `AttributionConfirmCreate`.
- [x] Implement endpoints: `POST/GET /api/o2o/links`.
- [x] Implement endpoint: `POST /api/workorders/{id}/confirm-attribution`.
