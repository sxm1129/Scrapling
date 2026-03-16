# Task Log: cookie-automation

## Phase: RESEARCH
- Analyzed `AccountPool` in `price_monitor/account_pool.py`. It stores cookies in `accounts.json` with a specific schema.
- We have 4 supported platforms requiring cookie maintenance: `jd_express`, `taobao`, `tmall`, `taobao_flash`.
- Cookie expiration happens because the session tokens (e.g. `pt_key` for JD, `_tb_token_` for Taobao) expire if not actively used.

---

## Phase: INNOVATE

### Approach: Stealthy Keep-Alive Worker (`cookie_keeper.py`)
To prevent session drop-offs, we need a background script that acts as a "heartbeat" for all active accounts.
- **Mechanism**: 
  1. Load all `active` accounts from `AccountPool`.
  2. For each account, launch a headless `StealthyFetcher` context infused with its cookies.
  3. Navigate to a highly safe, common URL (e.g., `https://my.m.jd.com/` for JD, `https://main.m.taobao.com/` for Taobao).
  4. Wait for the page to load (simulating a user check-in).
  5. Extract the updated cookies from the browser context (which will contain renewed expiry dates or refreshed tokens from the server's `Set-Cookie` headers).
  6. Update the `AccountPool` and save to `accounts.json`.
- **Stealth Considerations**: Random delays between accounts, random interactions (scroll), and user-agent matching to avoid WAF triggering.

---

## Phase: PLAN

### IMPLEMENTATION CHECKLIST

#### 1: 账号池自动续包器设计 (Module: CookieKeeper)
- [x] Create a new script `price_monitor/cookie_keeper.py`.
- [x] Define the target "Heartbeat URL" for each supported platform:
  - JD Express: `https://my.m.jd.com/`
  - Taobao / Tmall / Taobao Flash: `https://main.m.taobao.com/`
- [x] Implement `refresh_account_cookies(pool: AccountPool, platform: str, account_id: str)`:
  - Extract existing cookies for the `account_id` from `AccountPool`.
  - Launch a stealth context using `StealthyFetcher.create_browser_context()`.
  - Add existing cookies to the context.
  - Navigate to the Heartbeat URL and wait for `domcontentloaded` + a random 5-15s idle time to simulate a human user.
  - Read back the refreshed cookies via `context.cookies()`.
  - Merge and update the new cookies back into the `AccountPool` via `add_account`.
  - Close the context gently.
- [x] Implement a loop `run_keeper()` to iterate through all active accounts via `pool._pool.items()`, processing them one by one.
- [x] Add exception handling for expired cookies (e.g. redirected to login page), marking them as invalid in `AccountPool`.
- [x] Provide CLI execution parameters so it can run via system `cron` (e.g., `python -m price_monitor.cookie_keeper`).
