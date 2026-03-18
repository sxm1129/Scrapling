# Task Log: p3-p4-features

## Phase: RESEARCH

### 1. P3: Regional O2O & Front Warehouse Grid Scraping
- **Innovate**: Since Pupup, Dingdong, Xiaoxiang have no open Web search APIs, developing a new model `O2OStockLink` table to store manually captured product share links and their associated `city_context`.
- **Logic**: Modify `collection_manager.py`'s `_run_full_scan` or add `_run_o2o_scan`. It queries `O2OStockLink`, loops through them, and dispatches them as `SINGLE_URL` scrape jobs with priority to the respective crawler class.

### 2. P3: Attribution Fallback (Grid-based / Region-based) & Knowledge Base
- **Innovate**: Add mapping for "City -> Region -> Region Owner". When `match_responsibility` fails to find an exact shop or matched city, we fall back to a region owner if `ship_from_city` is known.
- If completely unknown (e.g. PDD / JD subsidies hide city), fallback to a global "Unknown Platform Dealer Pool" owner.
- To handle manual attribution, we've seen `POST /v1/workorders/{wo_id}:confirmAttribution` in DRD v2. This will write a new `ResponsibilityRule` into the DB.

### 3. P4: EDA Architecture (Event-Driven)
- Skip for now, focusing solely on P3 implementation to show progress.

### 4. P4: Deep Evidence & Integrity Hash
- Skip for now.
