# Quant Autoresearch dashboard redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the Streamlit dashboard as an overview-first, user-friendly research operations surface with progressive detail, trustworthy empty states, and safe CLI guidance.

**Architecture:** Keep `dashboard.py` as the Streamlit entry point and add `dashboard_model.py` for pure parsing, formatting, readiness, alert, and Frontier-row logic. The UI reads the five existing JSON state files through cached loaders, renders a compact safety/attention/readiness overview, and places Champion, Frontier, memory, freshness, and raw state behind progressive-detail sections. The dashboard remains read-only and never changes Paper/Live or places orders.

**Tech Stack:** Python 3.10, Streamlit, pandas, Altair, pytest, Streamlit `AppTest`, Ruff, mypy.

---

## File map

- Create: `dashboard_model.py` — pure, defensive view-model functions; no Streamlit imports and no file writes.
- Modify: `dashboard.py` — Streamlit page shell and UI components; use `dashboard_model.py` for all state interpretation.
- Create: `tests/test_dashboard_model.py` — unit tests for state parsing, formatting, readiness, alerts, and Frontier rows.
- Create: `tests/test_dashboard_app.py` — `AppTest` coverage for initial empty state, readiness filter, Frontier search/sort, refresh, and uncaught exceptions.
- Modify: `.gitignore` only if needed to exclude the local visual brainstorming session directory; do not remove existing ignore rules.

Do not modify protected paths (`core/data`, `core/backtest`, `core/evaluator`, `core/validation`, `core/costs`, `core/integrity`) or trading/generation implementation modules.

### Task 1: Add failing pure-logic tests

**Files:**
- Create: `tests/test_dashboard_model.py`

- [ ] **Step 1: Write the failing test**

Create fixtures with the current empty state and a populated Frontier/Champion state. Assert the public model functions below; the import should fail before implementation.

```python
from dashboard_model import (
    build_alerts,
    build_frontier_rows,
    build_readiness,
    format_percent,
    summarize_state,
)


def test_empty_paper_state_is_safe_but_needs_research_input() -> None:
    summary = summarize_state(
        mode={"selected_mode": "paper", "orders_enabled": False},
        champion={"status": "EMPTY", "champion": None},
        frontier={"families": {}},
        knowledge={"known_good": [], "known_bad": [], "unexplored": [], "interactions": []},
        rescue={"entries": []},
    )

    assert summary.safety_label == "SAFE"
    assert summary.champion_status == "EMPTY"
    assert summary.frontier_count == 0
    assert summary.knowledge_count == 0
    assert summary.rescue_count == 0
    assert summary.readiness_status == "attention"


def test_readiness_marks_live_without_orders_as_attention_and_keeps_paper_safe() -> None:
    items = build_readiness(
        mode={"selected_mode": "live", "orders_enabled": False},
        champion={"status": "CHAMPION", "champion": {"champion_hash": "h1"}},
        frontier={"families": {"trend": [{"strategy_id": "s1"}]}},
    )

    assert any(item.key == "mode" and item.status == "attention" for item in items)
    assert any(item.key == "champion" and item.status == "ready" for item in items)


def test_alerts_are_prioritized_and_do_not_claim_performance_for_empty_champion() -> None:
    alerts = build_alerts(
        mode={"selected_mode": "paper", "orders_enabled": False},
        champion={"status": "EMPTY", "champion": None},
        frontier={"families": {}},
        knowledge={"known_good": []},
    )

    assert alerts[0].severity == "critical"
    assert "Champion" in alerts[0].title
    assert all("improv" not in alert.title.lower() for alert in alerts)


def test_frontier_rows_are_flat_and_preserve_available_metrics() -> None:
    rows = build_frontier_rows(
        {
            "families": {
                "trend": [
                    {
                        "strategy_id": "s1",
                        "status": "FRONTIER",
                        "score": 0.74,
                        "metrics": {"sharpe": 1.2, "cagr": 0.18, "max_drawdown": -0.1, "trade_count": 42},
                    }
                ]
            }
        }
    )

    assert rows == [
        {
            "family": "trend",
            "strategy_id": "s1",
            "status": "FRONTIER",
            "score": 0.74,
            "sharpe": 1.2,
            "cagr": 0.18,
            "max_drawdown": -0.1,
            "trade_count": 42,
        }
    ]


def test_format_percent_handles_missing_values_and_units() -> None:
    assert format_percent(None) == "Unavailable"
    assert format_percent(0.125) == "12.5%"

### Task 2: Implement the defensive dashboard view model

**Files:**
- Create: `dashboard_model.py`
- Test: `tests/test_dashboard_model.py`

- [ ] **Step 1: Run the RED test**

Run:

```powershell
python -m pytest -q tests/test_dashboard_model.py
```

Expected: collection fails because `dashboard_model` does not exist.

- [ ] **Step 2: Implement the minimal pure model**

Define frozen dataclasses and functions with these signatures:

```python
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

State = Mapping[str, Any]
ReadinessStatus = Literal["ready", "attention", "blocked", "not_applicable"]

@dataclass(frozen=True)
class ReadinessItem:
    key: str
    label: str
    status: ReadinessStatus
    detail: str
    action: str | None = None

@dataclass(frozen=True)
class Alert:
    severity: Literal["critical", "warning", "info"]
    title: str
    detail: str
    action: str | None = None

@dataclass(frozen=True)
class StateSummary:
    mode: str
    orders_enabled: bool
    safety_label: str
    champion_status: str
    frontier_count: int
    family_count: int
    knowledge_count: int
    rescue_count: int
    readiness_status: ReadinessStatus

def format_percent(value: object, decimals: int = 1) -> str: ...
def build_frontier_rows(frontier: State | None) -> list[dict[str, Any]]: ...
def build_readiness(mode: State | None, champion: State | None, frontier: State | None) -> list[ReadinessItem]: ...
def build_alerts(mode: State | None, champion: State | None, frontier: State | None, knowledge: State | None) -> list[Alert]: ...
def summarize_state(mode: State | None, champion: State | None, frontier: State | None, knowledge: State | None, rescue: State | None) -> StateSummary: ...
```

Treat non-mapping JSON values as empty state, flatten only mapping strategy
records, preserve `None` for unavailable metrics, and sort alerts critical before
warning before info. `summarize_state` must derive counts from the same flattened
records used by the UI so counts reconcile.

- [ ] **Step 3: Run the GREEN unit tests**

Run the same pytest command. Expected: all tests in `tests/test_dashboard_model.py`
pass.

- [ ] **Step 4: Commit the model slice**

```powershell
git add dashboard_model.py tests/test_dashboard_model.py
git commit -m "feat: add defensive dashboard view model"
```

### Task 3: Add failing Streamlit behavior tests

**Files:**
- Create: `tests/test_dashboard_app.py`

- [ ] **Step 1: Write AppTest coverage before replacing the UI**

Use `AppTest.from_file` and stable widget keys:
`readiness_filter`, `frontier_search`, `frontier_sort`, `refresh_state`, and
`show_raw_state`.

```python
from streamlit.testing.v1 import AppTest


def test_empty_state_renders_safety_attention_and_no_exception() -> None:
    at = AppTest.from_file("dashboard.py", default_timeout=10).run()
    assert not at.exception
    assert any("PAPER" in item.value.upper() for item in at.badge)
    assert any("Champion" in item.value for item in at.warning + at.error)
    assert not at.json


def test_readiness_filter_can_show_only_attention_items() -> None:
    at = AppTest.from_file("dashboard.py", default_timeout=10).run()
    at.segmented_control(key="readiness_filter").set_value("Needs attention").run()
    assert not at.exception
    assert at.session_state["readiness_filter"] == "Needs attention"


def test_frontier_search_and_sort_do_not_crash_with_empty_state() -> None:
    at = AppTest.from_file("dashboard.py", default_timeout=10).run()
    at.text_input(key="frontier_search").set_value("trend").run()
    at.selectbox(key="frontier_sort").select("Score").run()
    assert not at.exception


def test_refresh_is_explicit_and_raw_state_is_collapsed_by_default() -> None:
    at = AppTest.from_file("dashboard.py", default_timeout=10).run()
    assert not at.session_state.get("show_raw_state", False)
    at.button(key="refresh_state").click().run()
    assert not at.exception
```

- [ ] **Step 2: Run the RED AppTest**

Run:

```powershell
python -m pytest -q tests/test_dashboard_app.py
```

Expected: tests fail because the stable widget keys and new hierarchy do not yet
exist in the current dashboard.

### Task 4: Rebuild the Streamlit page around the approved hierarchy

**Files:**
- Modify: `dashboard.py`
- Test: `tests/test_dashboard_app.py`

- [ ] **Step 1: Add a testable state-directory loader**

Read `QUANT_DASHBOARD_STATE_DIR` from the environment, defaulting to `state`, and
keep all file reads in a cached `load_state(filename)` function. Return `None` for
missing or malformed files, and expose `last_modified` for freshness labels. Do not
write files or call CLI processes.

- [ ] **Step 2: Implement the first viewport**

Render in this order:

1. title + mode/orders badge + last read time;
2. alert panel from `build_alerts`;
3. four priority metrics from `summarize_state`;
4. readiness list with `st.segmented_control(key="readiness_filter")`;
5. next-action panel with safe, copyable CLI guidance.

Use native Streamlit containers, `st.metric`, `st.badge`, `st.warning`, `st.error`,
and `st.info`. Use explicit text such as `SAFE`, `orders disabled`, `Needs
attention`, and `Unavailable`; do not rely on color alone.

- [ ] **Step 3: Implement progressive detail sections**

Add bordered sections or expanders for Champion evidence, Frontier, Knowledge and
Rescue Pool, freshness, and raw state. Champion shows only available metrics and
an evidence-insufficient empty state. Frontier uses `build_frontier_rows`, keyed
search, sort, bounded columns, and a compact family-count horizontal bar chart only
when rows exist. Memory lists are bounded. Raw state is behind
`st.checkbox(key="show_raw_state")` or a collapsed expander.

- [ ] **Step 4: Add safe action guidance**

Buttons may reveal `python cli.py ...` commands in an info/code block, but must not
execute subprocesses, modify state, enable orders, or infer live permissions. The
Live warning must repeat that `orders_enabled` remains false.

- [ ] **Step 5: Run AppTest to verify the GREEN behavior**

Run:

```powershell
python -m pytest -q tests/test_dashboard_app.py
```

Expected: all AppTest cases pass with no uncaught exception.

- [ ] **Step 6: Commit the UI slice**

```powershell
git add dashboard.py tests/test_dashboard_app.py
git commit -m "feat: rebuild research dashboard overview"
```

### Task 5: Validate quality, responsive behavior, and repository boundaries

**Files:**
- Modify: `dashboard.py` or `dashboard_model.py` only if validation finds a concrete issue.
- Test: `tests/test_dashboard_model.py`, `tests/test_dashboard_app.py`

- [ ] **Step 1: Run focused and full tests**

```powershell
python -m pytest -q tests/test_dashboard_model.py tests/test_dashboard_app.py
python -m pytest -q
```

Expected: focused tests and the full existing suite pass; dashboard changes do not
alter protected core behavior.

- [ ] **Step 2: Run static checks**

```powershell
ruff check .
python -m mypy .
```

Expected: no new Ruff or mypy errors. If mypy excludes dashboard files under the
existing configuration, report that limitation rather than claiming dashboard
typing was checked.

- [ ] **Step 3: Run the dashboard and perform a browser visual pass**

```powershell
streamlit run dashboard.py --server.port 8501
```

Inspect the actual page at desktop width and a narrow viewport. Verify safety state,
Champion empty state, alert priority, next action, no clipped labels, no raw JSON
above the fold, readable Frontier table, and intentional mobile stacking. Stop the
server after inspection unless the user asks to keep it running.

- [ ] **Step 4: Verify repository boundaries and diff**

```powershell
git diff --name-only HEAD~2..HEAD
git status --short
```

Confirm only dashboard files, dashboard tests, and the approved plan/spec commits
were added by this work. Do not stage existing user changes in `state/`, `pyproject.toml`,
`.agents/`, `.claude/`, `.omx/`, `.streamlit/`, or other unrelated paths.

- [ ] **Step 5: Final verification commit if fixes were required**

```powershell
git add dashboard.py dashboard_model.py tests/test_dashboard_model.py tests/test_dashboard_app.py
git commit -m "fix: harden dashboard verification findings"
```

Use this commit only when Task 5 required a concrete fix; do not create an empty
commit.

## Validation checklist

- [ ] First viewport answers safe/unsafe, current state, attention, and next action.
- [ ] Current empty Paper state renders without a fabricated performance trend.
- [ ] All state counts reconcile with source payloads.
- [ ] Missing, malformed, partial, and stale state are labeled rather than hidden.
- [ ] Frontier filters and sorting work and do not crash on empty input.
- [ ] Raw JSON is progressive detail, not default content.
- [ ] No UI action executes trades or changes live permissions.
- [ ] Color is never the sole status signal.
- [ ] Desktop and narrow viewport layouts have no overflow/clipping.
- [ ] Pytest, Ruff, and mypy results are reported accurately.
