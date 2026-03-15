# Scraper Phase 1: Network JSON Interception Implementation Checklist

## Objective
Migrate priority scrapers from brittle DOM evaluation to robust Playwright Network Interception (`page.route` / `page.on("response")`) to extract raw JSON data streams, avoiding UI change breakage and price masks.

## Priority Platforms
1. **Douyin (抖音)**: Static SSR `__INIT_PROPS__` extraction.
2. **Taobao/Tmall (淘宝/天猫)**: Intercept `h5api.m.taobao.com` JSON responses.
3. **JD Express (京东秒送)**: Intercept specific XHR/Fetch API responses containing real SKUs and prices to bypass font masking.

## Module Checklist

- [ ] **MODULE 1: Douyin SSR JSON Extraction**
  - **Goal**: Stop using `document.body.innerText`.
  - **Plan**: 
    - In `DouyinScraper.scrape_product` and `DouyinScraper.scrape_search`, use `page.evaluate()` only to pull the `window.__INIT_PROPS__` or find the script tag containing the SSR JSON.
    - Parse the JSON directly to extract `product_name`, `price`, `shop_name`, etc.
    - Remove the complex DOM css selector logic.

- [ ] **MODULE 2: JD Express XHR Interception**
  - **Goal**: Bypass the `¥1??9` masked texts in DOM.
  - **Plan**:
    - During `StealthyFetcher` setup, inject `page.on('response', handler)` to capture API responses (e.g. from `api.m.jd.com` or endpoints returning merchandise info).
    - Parse the response JSON asynchronously and store it in a shared `nonlocal` variable.
    - If the JSON contains the true price, use it directly to build the `ProductPrice` result.
    - Fallback to DOM only if network interception misses (unlikely).

- [ ] **MODULE 3: Taobao/Tmall API Interception (mtop)**
  - **Goal**: Extract deep SKU price tree, bypassing complex CSS obfuscation in the Tmall APP contexts.
  - **Plan**:
    - Add a response listener for `h5api.m.taobao.com` containing the detail data (`mtop.taobao.detail.getdetail` or similar).
    - Capture the JSON body, which natively contains the `skuCore` and `price` maps.
    - Map the precise price directly from the response JSON.

- [ ] **MODULE 4: Universal Net-Intercept Helper**
  - **Goal**: Standardize the extraction of JSON from specific URLs within the Playwright fetching context.
  - **Plan**:
    - Extend or wrap `StealthyFetcher` or add a helper in `BaseScraper` to easily wait for and capture a specific regex URL's JSON response during page load.
