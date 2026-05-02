# Autopilot Context Snapshot

## Task Statement

Implement the approved AF upgrade that adds a curated seed strategy, QQQ 2-hour loss-zone analysis, and feedback of loss reasons into the mutation loop.

## Desired Outcome

- AF uses a renamed curated seed strategy as the fixed reference.
- AF improves only from its own evaluated Strategy Tester trades.
- AF enriches those trades with QQQ 2-hour market context.
- AF turns recurring loss zones into structured repair guidance for the next mutation brief.
- The system remains compatible with the current knowledge-layered state model.

## Known Facts / Evidence

- Approved design: `C:\Users\hanji\Desktop\AF\docs\superpowers\specs\2026-04-24-seed-loss-analysis-design.md`
- Approved implementation plan: `C:\Users\hanji\Desktop\AF\docs\superpowers\plans\2026-04-24-seed-loss-analysis-implementation.md`
- Workspace root: `C:\Users\hanji\Desktop\AF`
- Current runtime is TypeScript + Vitest + Playwright-backed TradingView executor.
- The workspace is not currently a git repository.
- Mutation loop entry point is `src/research/iteration-runner.ts`.
- Knowledge layers already exist under `state/pi-autoresearch`.

## Constraints

- Do not use mock execution paths in runtime behavior.
- Preserve the AF identity and terminology.
- Use only AF-evaluated Strategy Tester trades for loss analysis.
- Keep QQQ 2-hour context scoped to this phase only.
- Follow existing append-only ledger and derived-view design.

## Unknowns / Open Questions

- Whether live market fetch code will need a fully offline-safe fallback in tests.
- How much of the user-provided Pine script should be copied verbatim into the active seed versus referenced through sync logic.

## Likely Codebase Touchpoints

- `C:\Users\hanji\Desktop\AF\src\contracts\types.ts`
- `C:\Users\hanji\Desktop\AF\src\mutation\brief.ts`
- `C:\Users\hanji\Desktop\AF\src\research\workspace.ts`
- `C:\Users\hanji\Desktop\AF\src\research\iteration-runner.ts`
- `C:\Users\hanji\Desktop\AF\src\research\artifact-writer.ts`
- `C:\Users\hanji\Desktop\AF\src\state\knowledge-paths.ts`
- `C:\Users\hanji\Desktop\AF\src\state\index-builder.ts`
- `C:\Users\hanji\Desktop\AF\src\state\knowledge-catalog.ts`
- `C:\Users\hanji\Desktop\AF\tests\research\*.test.ts`
- `C:\Users\hanji\Desktop\AF\tests\state\index-builder.test.ts`
