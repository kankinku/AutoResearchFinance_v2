# Quant Autoresearch dashboard redesign

> Status: historical Streamlit design. The active runtime is now the FastAPI/static
> dashboard under `dashboard/`; this document is retained for design traceability.

## A. Understanding of the request

Rebuild the existing Streamlit dashboard using the functional principles from the supplied dashboard prompt, while adapting them to the Quant Autoresearch Harness domain. The dashboard must reduce operator cognitive load, make the current research state trustworthy, and guide the next safe action. The prompt is a source of UX principles, not a literal visual or structural template.

## B. Goal

Create an overview-first Streamlit dashboard with progressive disclosure:

```text
current state -> attention -> next action -> analysis -> detail
```

The primary user is the local research operator who needs to answer quickly:

1. Is the system operating safely?
2. Is research ready to run?
3. Is there a Champion or a problem requiring attention?
4. What should I do next?
5. What evidence supports the displayed state?

## C. Scope

### Included

- Replace the current `dashboard.py` presentation and layout.
- Keep the existing JSON state files as the dashboard's read-only data sources:
  `mode.json`, `champion.json`, `frontier.json`, `knowledge.json`, and
  `rescue_pool.json`.
- Add a shared read-only view model layer inside the dashboard module or a small
  dashboard utility module when that improves testability.
- Build a first viewport containing:
  - explicit Paper/Live/orders status;
  - a concise attention summary;
  - prioritized state KPIs;
  - a next-action/readiness panel.
- Add progressive-detail sections for Champion, Frontier, Knowledge, Rescue Pool,
  freshness, and raw state.
- Add useful Frontier filtering/sorting without exposing every raw field.
- Show exact CLI guidance for research and mode actions; do not execute orders or
  silently enable Live mode from the UI.
- Handle missing, malformed, empty, partial, and stale state intentionally.
- Preserve metric semantics and distinguish implementation state from strategy
  performance evidence.
- Add unit tests for pure view-model/formatting logic and Streamlit `AppTest`
  coverage for critical rendered states and interactions.

### Excluded

- Changes to `core/data`, `core/backtest`, `core/evaluator`, `core/validation`,
  `core/costs`, or `core/integrity`.
- Changes to Strategy IR, evaluation, generation, KIS, paper adapter, or live-gate
  behavior.
- Direct order placement, account operations, or automatic Live activation.
- Inventing performance charts or trend claims when the state does not contain
  time-series evidence.
- Adding a new frontend framework or a third-party dashboard component.
- Replacing the approved architecture document.

## D. Constraints and assumptions

- Streamlit is the current frontend and `dashboard.py` is the entry point.
- Existing repository changes and state files are user-owned and must be preserved.
- The dashboard is a read-only monitoring surface over local state files.
- Paper-only defaults and `orders_enabled: false` remain authoritative.
- The current initialized state is expected to be empty: no Champion, no Frontier,
  no Knowledge entries, and no Rescue Pool entries.
- Values must be labeled with their source/freshness where freshness affects trust.
- New Streamlit code must not use deprecated `use_container_width`.
- Existing dependencies should be reused; no dependency is added for cosmetic
  convenience.

## E. Information architecture

### Level 1 — Safety and global context

The header displays the dashboard title, the active operating mode, orders-enabled
state, and a last-read/freshness summary. Safety state uses text plus icon/badge,
not color alone.

### Level 2 — Priority state

The first KPI row contains only decision-driving values:

- system safety state;
- Champion status;
- Frontier strategy count;
- research readiness status.

Knowledge and Rescue Pool are supporting metrics and are not given equal visual
weight when the system is empty.

### Level 3 — Attention and next action

An attention panel ranks issues by severity. An action panel explains the most
useful next safe step. Empty state copy must answer why the state is empty and what
input or command is required.

### Level 4 — Explanation

Champion evidence and Frontier comparison appear after the first viewport. A
Champion section shows only metrics that exist, with units and validation context.
If there is no Champion, the UI explains that no performance claim is available.

### Level 5 — Detail

Knowledge, Rescue Pool, per-file freshness, raw JSON, and extended fields are
collapsed by default. A raw state expander is a diagnostic escape hatch, not the
primary interface.

## F. Component and data design

The dashboard loads each state file through TTL-cached, failure-tolerant loaders.
Pure functions transform the untrusted JSON dictionaries into a typed or
well-defined dashboard view model:

- `SystemStatus`: mode, orders flag, safety label, source timestamp, freshness;
- `ReadinessItem`: label, state (`ready`, `attention`, `blocked`, or
  `not_applicable`), explanation, safe next step;
- `Alert`: severity, title, explanation, and optional action command;
- `ChampionSummary`: status, identity, evidence metrics, and evidence sufficiency;
- `FrontierRow`: family, strategy ID, state, score, and available metrics;
- `MemorySummary`: counts and bounded detail lists.

Malformed values are represented as unavailable rather than coerced into a
misleading number. State files are never written by the dashboard.

## G. Interaction design

- Sidebar contains global context and a refresh control only.
- A compact readiness filter can focus the user on `All`, `Needs attention`, or
  `Ready`; it changes the displayed readiness list, not the underlying state.
- Frontier table supports bounded search and sorting on decision-relevant columns.
- Champion/Frontier/diagnostic details use expanders or focused sections rather than
  dumping all JSON above the fold.
- Refresh clears the dashboard cache and reruns the page.
- Action buttons reveal copyable CLI commands and safety explanations. They do not
  run shell commands or cause external state changes.

## H. Empty, error, and stale states

- Empty: explain the missing state and identify the required next input.
- Partial: render available sections and label unavailable values.
- Malformed: show a diagnostic warning naming the affected state file without
  exposing sensitive content.
- Stale: keep previous data visible only with an explicit stale/delayed label and
  last successful read time.
- Missing state directory: show a setup explanation and the initialization command.
- Live mode with orders disabled: show a warning because the mode and capability
  are inconsistent, while preserving the safe orders-disabled boundary.

## I. Visual and responsive design

- Use the existing light theme and a restrained neutral/blue palette.
- Reserve orange/red for warnings and critical states; neutral information stays
  neutral.
- Prefer native Streamlit containers, metrics, badges, tables, and charts.
- Use no chart when the data is empty or a precise table answers the question
  better.
- Keep the first viewport compact; stack content intentionally on narrow screens:
  safety -> attention -> readiness/action -> Champion/Frontier -> memory/detail.
- All important state indicators include text labels and icons or directional copy,
  so color is not the sole signal.

## J. Validation and acceptance criteria

### Functional

- The app starts with the repository's current empty Paper state without an
  exception.
- Missing and malformed state files do not crash the app.
- Refresh clears cached reads and reruns.
- Readiness filtering changes only the visible readiness items.
- Frontier search/sort operate on the displayed decision-relevant rows.
- CLI action guidance is visible without executing a command.
- Raw JSON is not rendered in the initial viewport.

### Data integrity

- Paper mode and orders-disabled state are displayed from `mode.json`.
- Champion, Frontier, Knowledge, and Rescue counts reconcile with their source
  payloads.
- No performance evidence is fabricated when `champion.json` is empty or lacks
  metrics.
- Available metrics retain consistent units and explicit unavailable values.
- Per-file freshness is derived from the actual file modification/read state.

### Quality

- Unit tests cover view-model construction, alert priority, empty/malformed state,
  and number formatting.
- `AppTest` covers initial render, readiness filter, Frontier interaction, and
  absence of uncaught exceptions.
- Run `python -m pytest -q`, `ruff check .`, and `python -m mypy .` where the
  existing project configuration permits.
- Perform a browser visual pass at desktop and narrow viewport widths for overflow,
  hierarchy, labels, and focus/interaction clarity.

## K. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Empty state looks like a broken dashboard | Use explicit readiness and next-action guidance. |
| UI implies a strategy improved when only implementation data exists | Label evidence sufficiency and do not render invented trends. |
| Live controls create unsafe expectations | Keep actions informational and repeat Paper/orders-disabled status at the point of action. |
| State schema evolves | Use defensive parsing and narrow view-model contracts. |
| Too much detail returns the wall-of-cards problem | Keep only priority state above the fold and collapse diagnostics. |
| Streamlit reruns become slow | Cache state reads with bounded TTL and keep transforms cheap. |

## L. Recommended implementation sequence

1. Add failing tests for pure dashboard view-model and formatting behavior.
2. Implement the minimal view-model/data-loading layer.
3. Replace the page shell and first-viewport hierarchy.
4. Add Champion, Frontier, memory, freshness, and raw-detail sections.
5. Add filter/search/sort interactions and safe CLI guidance.
6. Add AppTest coverage and run repository quality gates.
7. Run visual desktop/narrow viewport review and fix concrete issues.
