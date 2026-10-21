# Quant AutoResearch dashboard — performance-first UI (2026-10-21 KST)

## User intent

Prioritize trading-strategy research results visually above system operations. Show the evolution of measured strategy performance across generations in continuously refreshed charts. Hide connection/infrastructure details until the user explicitly presses a **연결 상태** button.

## Implementation

- Preserves the preexisting original `dashboard/static/index.html`, `styles.css`, `app.js` and the existing `/backtest` page unchanged.
- `scripts/fresh_original_dashboard.py` inserts three opt-in fresh-research assets only into the authenticated academic dashboard root (not the old general dashboard endpoint):
  - `dashboard/static/fresh-performance.html`: a top performance overview, full-generation graph, risk graph, research progress, and accessible connection-status dialog.
  - `dashboard/static/fresh-performance.css`: neutral spacious responsive 4-KPI layout (2 columns on mobile), collapsible original ops panels, accessible dialog.
  - `dashboard/static/fresh-performance.js`: real generation history from the read-only `/api/status` endpoint, **5-second polling**. Only browser read operations. Native inline SVG plots need no third-party CDN/chart script.
- Top KPI: highest measured eligible development candidate, QQQ price-only same-period buy-and-hold, gap in percentage points, MDD of best candidate. Additional 100-generation progress, positive generation count, average MDD, latest measured return.
- Main interactive chart: X=research generation; gray=each generation's **separate** costed total return; blue=best eligible return achieved *by then* (historical running maximum); dashed gray=QQQ price-only hold return for the same sample. Display entire history or latest 30/50/100 generations without changing stored data. SVG circle titles identify G, return and drawdown. Not a portfolio NAV or time-series equity curve.
- Second chart: per-generation maximum drawdown (MDD) vs generation. Statistics, plots and best strategy recalculate on every polling response, showing further generations as they are genuinely committed. A **COMPLETED** session remains stable and is not falsely labelled RUNNING.
- Original runtime/Frontier/KIS/auth/system sections collapsed under an optional `운영 정보...` disclosure below the charts; connection-specific details accessed in the top **연결 상태** dialog, with explicit gateway/GPT/OOS limitations and replayable read-only status refresh. Hidden footer API diagnostics.
- Original backtest page and original source assets are kept intact; same Basic Auth policy under local `http://127.0.0.1:2999/academic/` and HTTPS `https://project-moon.taild689f9.ts.net/quant-research/`. The secure nginx route continues to deny write methods. No new credentials, broker orders, or research-state writes.

## Grounding (existing G152 cohort)

Highest development candidate **G99 +73.03% total return**, MDD **27.91%**, closed trades **103**. Development sample QQQ price-only buy-and-hold **+187.77%**: return gap **−114.74 percentage points**. This is NOT a strategy outperforming the benchmark. The new generation cohort G53–G152 completed 100/100; entire new lineage 152/152, immutable Evidence chain PASS, actual gateway S7 152. Same research dataset used repeatedly, PIT/OOS not independently verified; no per-generation autonomous GPT calls verified. Do not interpret model chart as a compounded investment portfolio.

## Test and operations

- `node tests/dashboard/original_ui_browser_smoke.cjs`: executes original shipped JS and new chart JS in a mock DOM with **real buffered localhost HTTP API data**, asserting exact 73.03 / 187.77 / −114.74%p values; chart SVG paths; G152 cohort status; filter control; modal open/close; old refresh. Uses buffered Node HTTP rather than flaky undici fetch. This is NOT a physical Windows browser screenshot.
- `pytest` scoped dashboard/governance tests (22 passed) and targeted Ruff/mypy validations PASS.
- The original static HTML is served within a controlled injected opt-in performance view without modifying old static HTML/JS/CSS source files. Static CSP allows self-hosted JS/CSS with no unauthenticated data endpoint.
- After restarting scoped `fresh-quant-original-ui` only, verify both secured URLs return the first-screen performance markup, new .css and .js with HTTP 200, API status 152/152 and original backtest page still working. External anonymous request must return 401; POST remains denied.
- No guarantee of broker, Quant MCP/OAuth or actual ongoing research model availability. A further genuine committed generation will be plotted within the next poll; when none is running the page must not invent progress.
