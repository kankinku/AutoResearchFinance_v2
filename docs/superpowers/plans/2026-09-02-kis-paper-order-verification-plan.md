# KIS Paper Order Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement and verify a one-shot KIS paper buy/fill/sell/flat workflow for QQQ without exposing live or research order capability.

**Architecture:** Keep `integrations/kis/client.py` read-only and add a separate paper-order client that composes it. The CLI owns the explicit smoke-test workflow and never enables persistent orders, changes the selected mode, or adds an MCP order tool.

**Tech Stack:** Python 3.10+, pytest, urllib transport already used by the repository, Ruff, mypy, KIS overseas-stock REST API.

---

### Task 1: Lock the paper-order contract with tests

**Files:**
- Create: `tests/integrations/test_paper_orders.py`
- Modify: `integrations/kis/client.py` only if a test requires a small typed response helper

- [ ] **Step 1: Write failing tests**

Test a fake transport sequence containing token response, buy response, execution response with a filled quantity, sell response, and a flat final execution/holding response. Assert the client sends `POST /uapi/overseas-stock/v1/trading/order` with `VTTT1002U` for buy and `VTTT1006U` for sell, uppercase market-order fields, `ORD_QTY='1'`, and `OVRS_ORD_UNPR='0'`. Add a test that a live base URL or `mode='live'` raises before transport calls, and a test that no sell is created when filled quantity is zero.

- [ ] **Step 2: Run the focused tests and confirm RED**

Run: `python -m pytest tests/integrations/test_paper_orders.py -q`

Expected: FAIL because `KISPaperOrderClient` and the one-shot workflow do not exist.

### Task 2: Implement the isolated paper order client

**Files:**
- Create: `integrations/kis/paper_orders.py`
- Modify: `integrations/kis/__init__.py` only if the package needs an explicit public export

- [ ] **Step 1: Add the minimal paper-only client**

Implement `KISPaperOrderClient(config, transport=None, clock=None)` by composing `KISPaperClient`. Add `place_market_order(symbol, side, quantity, exchange='NASD')`, validate whole-share positive quantity and US exchange, reject non-paper mode/base URL, split the configured account using the existing helper, and call the official endpoint with:

```python
{
    'CANO': cano,
    'ACNT_PRDT_CD': product,
    'OVRS_EXCG_CD': 'NASD',
    'PDNO': 'QQQ',
    'ORD_DVSN': '01',
    'ORD_QTY': '1',
    'OVRS_ORD_UNPR': '0',
    'SLL_TYPE': '' if side == 'buy' else '00',
    'ORD_SVR_DVSN_CD': '0',
}
```

Use `VTTT1002U` for buy and `VTTT1006U` for sell. Return a receipt containing only symbol, side, requested quantity, paper exchange, order ID, and sanitized KIS codes.

- [ ] **Step 2: Add execution lookup**

Implement `filled_quantity(symbol, start_date, end_date)` using `GET /uapi/overseas-stock/v1/trading/inquire-ccnl`, TR ID `VTTS3035R`, with paper-required whole-account query values (`PDNO=''`, `SLL_BUY_DVSN='00'`, `CCLD_NCCS_DVSN='00'`, `OVRS_EXCG_CD=''`, `SORT_SQN='DS'`, and empty continuation fields). Sum only records matching the symbol and parse the filled quantity fields used by KIS (`ft_ccld_qty`, `ft_ccld_qty2`, `ccld_qty`, or `filled_quantity`).

- [ ] **Step 3: Add the bounded buy-then-sell workflow**

Implement `run_buy_then_sell(symbol='QQQ', quantity=1, timeout_seconds=30, poll_seconds=1)` that places one buy, polls filled quantity, returns `BUY_NOT_FILLED` without placing a sell when quantity is zero, otherwise places exactly one sell for the filled quantity and returns both receipts. Do not retry order submissions.

- [ ] **Step 4: Run focused tests and confirm GREEN**

Run: `python -m pytest tests/integrations/test_paper_orders.py -q`

Expected: all focused tests pass.

### Task 3: Add an explicit CLI smoke command

**Files:**
- Modify: `cli.py`
- Create: `tests/cli/test_paper_order_smoke.py`
- Modify: `README.md`

- [ ] **Step 1: Write failing CLI tests**

Assert parser defaults are QQQ/one share/paper, the command requires an explicit `--confirm-paper-order` flag, and the handler reports `PAPER_ONLY` without changing `state/mode.json`. Inject the client in the test so no network call occurs.

- [ ] **Step 2: Implement the command**

Add `paper-order-smoke --env-file .env --symbol QQQ --quantity 1 --confirm-paper-order`, load config, require `mode == 'paper'`, execute the bounded workflow, print sanitized JSON, and return nonzero on a non-flat result. Never expose this command through Codex MCP or autoresearch.

- [ ] **Step 3: Run focused CLI tests**

Run: `python -m pytest tests/cli/test_paper_order_smoke.py -q`

Expected: all focused CLI tests pass.

### Task 4: Full verification and one controlled live-paper attempt

**Files:**
- No source changes expected after Task 3

- [ ] **Step 1: Run repository checks**

Run:

```powershell
python -m pytest -q
ruff check .
python -m mypy .
git diff --check
```

Expected: all commands pass.

- [ ] **Step 2: Re-read mode and env presence without printing secrets**

Confirm `state/mode.json` says `selected_mode: paper` and `orders_enabled: false`; confirm only the names of required paper env variables are present.

- [ ] **Step 3: Execute exactly one KIS paper smoke run**

Run:

```powershell
python cli.py paper-order-smoke --env-file .env --symbol QQQ --quantity 1 --confirm-paper-order
```

Expected: sanitized output identifies paper mode, buy receipt, filled quantity, sell receipt, and final flat status. If the API rejects the request or the market is closed, do not resubmit; report the exact phase and whether an order was accepted.

- [ ] **Step 4: Verify no live or persistent state change**

Re-read `state/mode.json`, confirm no new MCP order tool, and report `git status --short` while preserving all pre-existing user changes.

- [ ] **Step 5: Commit the implementation atomically**

```powershell
git add integrations/kis/paper_orders.py tests/integrations/test_paper_orders.py cli.py tests/cli/test_paper_order_smoke.py README.md docs/superpowers/specs/2026-09-02-kis-paper-order-verification-design.md docs/superpowers/plans/2026-09-02-kis-paper-order-verification-plan.md
git commit -m "feat: verify KIS paper buy and sell flow"
```
