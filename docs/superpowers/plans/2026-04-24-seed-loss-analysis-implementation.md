# Seed Strategy And Loss-Zone Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a curated seed strategy and a QQQ 2-hour loss-zone analysis loop so AF improves from its own evaluated trades instead of only generic score deltas.

**Architecture:** Keep the new behavior inside AF's existing layered structure. Add a small seed-strategy module for curated baseline handling, add market-context and loss-analysis modules under `src/research`, then thread their outputs into mutation brief generation, evidence artifacts, experiment ledgers, and derived views.

**Tech Stack:** TypeScript, Vitest, Playwright-backed TradingView executor, Zod schemas, Node.js filesystem APIs

---

> **Workspace note:** `C:\Users\hanji\Desktop\AF` is currently not a git repository. The commit steps below include the intended commit message and file set, but actual `git commit` commands will only work after git is initialized.

## File Map

### New files

- `C:\Users\hanji\Desktop\AF\src\research\seed-strategy.ts`
- `C:\Users\hanji\Desktop\AF\src\research\market-context.ts`
- `C:\Users\hanji\Desktop\AF\src\research\trade-context.ts`
- `C:\Users\hanji\Desktop\AF\src\research\loss-analysis.ts`
- `C:\Users\hanji\Desktop\AF\tests\research\seed-strategy.test.ts`
- `C:\Users\hanji\Desktop\AF\tests\research\market-context.test.ts`
- `C:\Users\hanji\Desktop\AF\tests\research\trade-context.test.ts`
- `C:\Users\hanji\Desktop\AF\tests\research\loss-analysis.test.ts`
- `C:\Users\hanji\Desktop\AF\tests\mutation\brief.test.ts`
- `C:\Users\hanji\Desktop\AF\strategies\source\seed_primary.pine`

### Modified files

- `C:\Users\hanji\Desktop\AF\src\contracts\types.ts`
- `C:\Users\hanji\Desktop\AF\src\mutation\brief.ts`
- `C:\Users\hanji\Desktop\AF\src\research\workspace.ts`
- `C:\Users\hanji\Desktop\AF\src\research\artifact-writer.ts`
- `C:\Users\hanji\Desktop\AF\src\research\iteration-runner.ts`
- `C:\Users\hanji\Desktop\AF\src\state\knowledge-paths.ts`
- `C:\Users\hanji\Desktop\AF\src\state\index-builder.ts`
- `C:\Users\hanji\Desktop\AF\src\state\knowledge-catalog.ts`
- `C:\Users\hanji\Desktop\AF\tests\research\iteration.test.ts`
- `C:\Users\hanji\Desktop\AF\tests\state\index-builder.test.ts`
- `C:\Users\hanji\Desktop\AF\strategies\source\baseline.pine`

## Task 1: Add Curated Seed Strategy Support

**Files:**
- Create: `C:\Users\hanji\Desktop\AF\src\research\seed-strategy.ts`
- Create: `C:\Users\hanji\Desktop\AF\tests\research\seed-strategy.test.ts`
- Create: `C:\Users\hanji\Desktop\AF\strategies\source\seed_primary.pine`
- Modify: `C:\Users\hanji\Desktop\AF\src\research\workspace.ts`
- Modify: `C:\Users\hanji\Desktop\AF\strategies\source\baseline.pine`

- [ ] **Step 1: Write the failing seed-strategy tests**

```ts
import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { describe, expect, test } from "vitest";

import {
  ensureActiveSeedBaseline,
  loadSeedStrategyReference,
} from "../../src/research/seed-strategy.js";

describe("seed strategy", () => {
  test("copies the curated seed into baseline when baseline is missing", async () => {
    const workspace = await mkdtemp(path.join(tmpdir(), "af-seed-"));

    await ensureActiveSeedBaseline(workspace);

    const baseline = await readFile(
      path.join(workspace, "strategies", "source", "baseline.pine"),
      "utf8",
    );
    expect(baseline).toContain("strategy(\"AF Seed 01\"");
  });

  test("loads a structured seed strategy reference", async () => {
    const workspace = await mkdtemp(path.join(tmpdir(), "af-seed-ref-"));

    await ensureActiveSeedBaseline(workspace);
    const seed = await loadSeedStrategyReference(workspace);

    expect(seed.candidateId).toBe("seed_primary");
    expect(seed.studyTitle).toContain("AF Seed 01");
    expect(seed.summary.length).toBeGreaterThan(0);
  });
});
```

- [ ] **Step 2: Run the seed-strategy tests to verify they fail**

Run: `npx vitest run C:\Users\hanji\Desktop\AF\tests\research\seed-strategy.test.ts`  
Expected: FAIL with module-not-found or exported-function errors for `seed-strategy.ts`

- [ ] **Step 3: Add the curated seed module and seed file**

```ts
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";

import { ensureDir, fileExists, sha256 } from "../utils/fs.js";

function sourceDir(workspaceRoot: string): string {
  return path.join(workspaceRoot, "strategies", "source");
}

export async function ensureActiveSeedBaseline(workspaceRoot: string): Promise<void> {
  const dir = sourceDir(workspaceRoot);
  const curatedPath = path.join(dir, "seed_primary.pine");
  const baselinePath = path.join(dir, "baseline.pine");
  await ensureDir(dir);

  if (!(await fileExists(curatedPath))) {
    throw new Error(`Curated seed is missing: ${curatedPath}`);
  }

  if (!(await fileExists(baselinePath))) {
    const curated = await readFile(curatedPath, "utf8");
    await writeFile(baselinePath, curated, "utf8");
  }
}

export async function loadSeedStrategyReference(workspaceRoot: string): Promise<{
  candidateId: string;
  summary: string;
  studyTitle: string | null;
  candidateHash: string;
}> {
  const curatedPath = path.join(sourceDir(workspaceRoot), "seed_primary.pine");
  const source = await readFile(curatedPath, "utf8");
  const titleMatch = source.match(/strategy\\((['\"])(.*?)\\1/);

  return {
    candidateId: "seed_primary",
    summary: "Curated exhaustion seed strategy used as the AF research anchor.",
    studyTitle: titleMatch?.[2] ?? null,
    candidateHash: sha256(source),
  };
}
```

`C:\Users\hanji\Desktop\AF\strategies\source\seed_primary.pine` should contain the user-provided Pine logic with only the strategy title changed to:

```pine
strategy("AF Seed 01", overlay=true, pyramiding=30, process_orders_on_close=true, initial_capital=100000, default_qty_type=strategy.percent_of_equity, default_qty_value=5, commission_type=strategy.commission.percent, commission_value=0.05)
```

- [ ] **Step 4: Wire seed initialization into workspace bootstrap**

```ts
import { ensureActiveSeedBaseline } from "./seed-strategy.js";

export async function initializeWorkspace(workspaceRoot: string): Promise<void> {
  await ensureDir(path.join(workspaceRoot, "strategies", "source"));
  await copyIfMissing(
    path.join(TEMPLATE_ROOT, "strategies", "source", "seed_primary.pine"),
    path.join(workspaceRoot, "strategies", "source", "seed_primary.pine"),
  );

  await ensureActiveSeedBaseline(workspaceRoot);
  await copyIfMissing(
    path.join(TEMPLATE_ROOT, "strategies", "source", "runtime_target.pine"),
    path.join(workspaceRoot, "strategies", "source", "runtime_target.pine"),
  );
  const stateRoot = path.join(workspaceRoot, "state", "pi-autoresearch");
  await ensureStateRoot(stateRoot);
  const objective = await loadObjectiveConfig(workspaceRoot);
  await syncKnowledgeCatalog(workspaceRoot, objective);
  await migrateLegacyKnowledgeLayout(workspaceRoot);
  await rebuildIndexes(stateRoot);
}
```

- [ ] **Step 5: Run tests to verify the seed layer passes**

Run: `npx vitest run C:\Users\hanji\Desktop\AF\tests\research\seed-strategy.test.ts C:\Users\hanji\Desktop\AF\tests\research\iteration.test.ts`  
Expected: PASS for the new seed tests, existing iteration tests still PASS

- [ ] **Step 6: Record commit intent**

Planned files:

```text
src/research/seed-strategy.ts
src/research/workspace.ts
tests/research/seed-strategy.test.ts
strategies/source/seed_primary.pine
strategies/source/baseline.pine
```

Planned commit message:

```text
feat: add curated seed strategy support
```

## Task 2: Extend Contracts And Mutation Briefs For Seed And Loss Context

**Files:**
- Modify: `C:\Users\hanji\Desktop\AF\src\contracts\types.ts`
- Modify: `C:\Users\hanji\Desktop\AF\src\mutation\brief.ts`
- Create: `C:\Users\hanji\Desktop\AF\tests\mutation\brief.test.ts`

- [ ] **Step 1: Write the failing mutation-brief tests**

```ts
import { describe, expect, test } from "vitest";

import { buildMutationBrief } from "../../src/mutation/brief.js";

describe("buildMutationBrief", () => {
  test("includes curated seed and loss analysis context", () => {
    const brief = buildMutationBrief({
      objective: {
        symbol: "QQQ",
        timeframe: "120",
        hardGates: {
          minimumTotalTrades: 50,
          minimumPostFeeNetProfitPercent: 0,
        },
        softGuardrails: {
          maximumStrategyDrawdownPercent: 15,
          softGuardrailPenalty: 0.1,
        },
        weights: {
          netProfitPercent: 0.45,
          profitFactor: 0.15,
          inverseMaxDrawdown: 0.15,
          percentProfitable: 0.1,
          totalTrades: 0.05,
          avgTradePercent: 0.1,
        },
        normalizationCaps: {
          netProfitPercent: 30,
          profitFactor: 3,
          maxStrategyDrawdownPercent: 30,
          percentProfitable: 100,
          totalTrades: 100,
          avgTradePercent: 1,
        },
      },
      seedStrategy: {
        candidateId: "seed_primary",
        summary: "Curated seed",
        studyTitle: "AF Seed 01",
      },
      acceptedHead: null,
      recentFailures: ["hard_gate_fail"],
      recentLossAnalysis: {
        status: "available",
        summary: "Losses cluster in trend_down counter-trend entries.",
        topLossZones: ["trend_down:counter_trend_entry"],
        repairPriorities: ["Reduce B2/B3 entries during trend_down regimes."],
      },
    });

    expect(brief.seedStrategy.candidateId).toBe("seed_primary");
    expect(brief.improvementSource).toBe("seed");
    expect(brief.lossHotZones[0]).toContain("trend_down");
  });
});
```

- [ ] **Step 2: Run the mutation-brief tests to verify they fail**

Run: `npx vitest run C:\Users\hanji\Desktop\AF\tests\mutation\brief.test.ts`  
Expected: FAIL because `MutationBrief` does not yet include `seedStrategy`, `improvementSource`, or loss-analysis fields

- [ ] **Step 3: Extend the shared contracts**

Add these schema shapes inside `C:\Users\hanji\Desktop\AF\src\contracts\types.ts`:

```ts
export const seedStrategyReferenceSchema = z.object({
  candidateId: z.string().min(1),
  summary: z.string().min(1),
  studyTitle: z.string().nullable(),
});

export const lossAnalysisSummarySchema = z.object({
  status: z.enum(["available", "unavailable_no_trades", "market_context_unavailable"]),
  summary: z.string().min(1),
  topLossZones: z.array(z.string()).default([]),
  repairPriorities: z.array(z.string()).default([]),
});
```

And extend `mutationBriefSchema`:

```ts
seedStrategy: seedStrategyReferenceSchema,
improvementSource: z.enum(["seed", "accepted_head"]),
recentLossAnalysis: lossAnalysisSummarySchema,
lossHotZones: z.array(z.string()),
repairPriorities: z.array(z.string()),
```

- [ ] **Step 4: Upgrade the brief builder**

Update `C:\Users\hanji\Desktop\AF\src\mutation\brief.ts` so it accepts the new input and produces deterministic loss-aware guidance:

```ts
const improvementSource = input.acceptedHead ? "accepted_head" : "seed";
const recentFailures = input.recentFailures.slice(0, 5);
const repairPriorities = input.recentLossAnalysis.repairPriorities.slice(0, 5);

return {
  objective: `${input.objective.symbol} ${input.objective.timeframe}m hard-gate-passing strategy improvement`,
  guardrails: {
    minimumTotalTrades: input.objective.hardGates.minimumTotalTrades,
    minimumPostFeeNetProfitPercent:
      input.objective.hardGates.minimumPostFeeNetProfitPercent,
    maximumStrategyDrawdownPercent:
      input.objective.softGuardrails.maximumStrategyDrawdownPercent,
  },
  seedStrategy: input.seedStrategy,
  acceptedHead: input.acceptedHead,
  improvementSource,
  recentFailures,
  recentLossAnalysis: input.recentLossAnalysis,
  lossHotZones: input.recentLossAnalysis.topLossZones,
  repairPriorities,
  nextMutationDirection:
    repairPriorities.length > 0
      ? repairPriorities.join(" ")
      : recentFailures.length > 0
        ? `Avoid repeating recent failure modes: ${recentFailures.join(", ")}`
        : "Improve net profit with stable drawdown and sufficient trade count.",
  forbiddenPatterns: [
    "Do not remove strategy() declaration.",
    "Do not emit empty or placeholder Pine code.",
    "Do not leave TODO, placeholder, or markdown fence text inside pineScript.",
    "Do not use ta.adx(); use Pine v5-safe manual DMI/ADX logic if ADX is required.",
    "Do not optimize for fewer than the minimum required trades.",
  ],
};
```

- [ ] **Step 5: Run contract and brief tests**

Run: `npx vitest run C:\Users\hanji\Desktop\AF\tests\mutation\brief.test.ts C:\Users\hanji\Desktop\AF\tests\mutation\parser.test.ts C:\Users\hanji\Desktop\AF\tests\research\iteration.test.ts`  
Expected: PASS, and no existing brief-dependent tests regress

- [ ] **Step 6: Record commit intent**

Planned files:

```text
src/contracts/types.ts
src/mutation/brief.ts
tests/mutation/brief.test.ts
```

Planned commit message:

```text
feat: extend mutation brief with seed and loss context
```

## Task 3: Build The QQQ 2-Hour Market Context Cache

**Files:**
- Create: `C:\Users\hanji\Desktop\AF\src\research\market-context.ts`
- Create: `C:\Users\hanji\Desktop\AF\tests\research\market-context.test.ts`
- Modify: `C:\Users\hanji\Desktop\AF\src\state\knowledge-paths.ts`
- Modify: `C:\Users\hanji\Desktop\AF\src\state\knowledge-catalog.ts`

- [ ] **Step 1: Write the failing market-context tests**

```ts
import { describe, expect, test } from "vitest";

import { buildTwoHourBars, classifyMarketRegime } from "../../src/research/market-context.js";

describe("market context", () => {
  test("compresses hourly QQQ bars into 2-hour bars", () => {
    const bars = buildTwoHourBars([
      { time: "2026-04-20T00:00:00.000Z", open: 100, high: 101, low: 99, close: 100.5, volume: 10 },
      { time: "2026-04-20T01:00:00.000Z", open: 100.5, high: 102, low: 100, close: 101.5, volume: 12 },
    ]);

    expect(bars).toHaveLength(1);
    expect(bars[0]?.close).toBe(101.5);
    expect(bars[0]?.volume).toBe(22);
  });

  test("classifies clear down-trend bars", () => {
    const regime = classifyMarketRegime({
      close: 95,
      ema20: 97,
      ema50: 100,
      ema200: 110,
      atrPercent: 2.2,
      bbWidth: 0.06,
    });

    expect(regime).toBe("trend_down");
  });
});
```

- [ ] **Step 2: Run the market-context tests to verify they fail**

Run: `npx vitest run C:\Users\hanji\Desktop\AF\tests\research\market-context.test.ts`  
Expected: FAIL because `market-context.ts` does not exist

- [ ] **Step 3: Implement the context builder and cache loader**

Core functions in `C:\Users\hanji\Desktop\AF\src\research\market-context.ts`:

```ts
export interface MarketContextBar {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  ema20: number | null;
  ema50: number | null;
  ema200: number | null;
  atr14: number | null;
  atrPercent: number | null;
  rsi14: number | null;
  bbWidth: number | null;
  ret3: number | null;
  ret10: number | null;
  regime: string;
}

export function buildTwoHourBars(hourlyBars: HourlyBar[]): HourlyBar[] {
  const result: HourlyBar[] = [];
  for (let index = 0; index < hourlyBars.length; index += 2) {
    const first = hourlyBars[index];
    const second = hourlyBars[index + 1];
    if (!first || !second) {
      break;
    }
    result.push({
      time: first.time,
      open: first.open,
      high: Math.max(first.high, second.high),
      low: Math.min(first.low, second.low),
      close: second.close,
      volume: first.volume + second.volume,
    });
  }
  return result;
}

export function classifyMarketRegime(input: {
  close: number;
  ema20: number | null;
  ema50: number | null;
  ema200: number | null;
  atrPercent: number | null;
  bbWidth: number | null;
}): string {
  if (
    input.ema20 !== null &&
    input.ema50 !== null &&
    input.ema200 !== null &&
    input.close < input.ema20 &&
    input.ema20 < input.ema50 &&
    input.ema50 < input.ema200
  ) {
    return "trend_down";
  }
  if (
    input.ema20 !== null &&
    input.ema50 !== null &&
    input.ema200 !== null &&
    input.close > input.ema20 &&
    input.ema20 > input.ema50 &&
    input.ema50 > input.ema200
  ) {
    return "trend_up";
  }
  if ((input.bbWidth ?? 0) <= 0.03) {
    return "range_squeeze";
  }
  if ((input.atrPercent ?? 0) >= 2.5) {
    return "volatile";
  }
  return "range";
}

export async function loadQqqTwoHourContext(workspaceRoot: string, options?: {
  fetchImpl?: typeof fetch;
  forceRefresh?: boolean;
}): Promise<{ bars: MarketContextBar[]; cachePath: string; fromCache: boolean }> {
  const fetchImpl = options?.fetchImpl ?? fetch;
  const stateRoot = path.join(workspaceRoot, "state", "pi-autoresearch");
  const cachePath = resolveKnowledgePaths(stateRoot).qqqTwoHourContextPath;
  if (!options?.forceRefresh && (await fileExists(cachePath))) {
    return {
      bars: JSON.parse(await readFile(cachePath, "utf8")).bars,
      cachePath,
      fromCache: true,
    };
  }

  const response = await fetchImpl(
    "https://query1.finance.yahoo.com/v8/finance/chart/QQQ?range=730d&interval=1h",
  );
  const payload = await response.json();
  const hourlyBars = extractHourlyBars(payload);
  const bars = enrichTwoHourBars(buildTwoHourBars(hourlyBars));
  await writeJson(cachePath, { generatedAt: new Date().toISOString(), bars });
  return { bars, cachePath, fromCache: false };
}
```

- [ ] **Step 4: Register the new evidence artifact path**

Extend `C:\Users\hanji\Desktop\AF\src\state\knowledge-paths.ts` with:

```ts
qqqTwoHourContextPath: path.join(resultsDir, "qqq-2h-context.json"),
lossPatternSummaryPath: path.join(viewsDir, "loss-pattern-summary.json"),
```

And add matching catalog entries in `C:\Users\hanji\Desktop\AF\src\state\knowledge-catalog.ts`.

- [ ] **Step 5: Run market-context and catalog tests**

Run: `npx vitest run C:\Users\hanji\Desktop\AF\tests\research\market-context.test.ts C:\Users\hanji\Desktop\AF\tests\state\knowledge-catalog.test.ts`  
Expected: PASS and the knowledge catalog includes the new context cache artifact

- [ ] **Step 6: Record commit intent**

Planned files:

```text
src/research/market-context.ts
src/state/knowledge-paths.ts
src/state/knowledge-catalog.ts
tests/research/market-context.test.ts
```

Planned commit message:

```text
feat: add qqq 2h market context cache
```

## Task 4: Enrich Trades And Derive Loss-Zone Analysis

**Files:**
- Create: `C:\Users\hanji\Desktop\AF\src\research\trade-context.ts`
- Create: `C:\Users\hanji\Desktop\AF\src\research\loss-analysis.ts`
- Create: `C:\Users\hanji\Desktop\AF\tests\research\trade-context.test.ts`
- Create: `C:\Users\hanji\Desktop\AF\tests\research\loss-analysis.test.ts`
- Modify: `C:\Users\hanji\Desktop\AF\src\contracts\types.ts`

- [ ] **Step 1: Write the failing trade-enrichment and loss-analysis tests**

```ts
import { describe, expect, test } from "vitest";

import { enrichTradesWithMarketContext } from "../../src/research/trade-context.js";
import { summarizeLossZones } from "../../src/research/loss-analysis.js";

describe("trade context", () => {
  test("matches trade timestamps to the nearest 2-hour bars", () => {
    const trades = [
      {
        entryComment: "entry",
        entryPrice: 100,
        entryTime: "2026-04-20T00:30:00.000Z",
        exitComment: "exit",
        exitPrice: 98,
        exitTime: "2026-04-20T02:10:00.000Z",
        qty: 1,
        profitValue: -2,
        profitPercent: -2,
        runupPercent: 0.5,
        drawdownPercent: 3,
      },
    ];
    const bars = [
      { time: "2026-04-20T00:00:00.000Z", regime: "trend_down", close: 100, ema20: 101, ema50: 103, ema200: 110, atrPercent: 2, rsi14: 40, bbWidth: 0.06, ret3: -0.03, ret10: -0.05 },
      { time: "2026-04-20T02:00:00.000Z", regime: "trend_down", close: 98, ema20: 100, ema50: 102, ema200: 109, atrPercent: 2.4, rsi14: 36, bbWidth: 0.07, ret3: -0.04, ret10: -0.06 },
    ];

    const enriched = enrichTradesWithMarketContext(trades, bars);

    expect(enriched[0]?.entryContext?.regime).toBe("trend_down");
    expect(enriched[0]?.flags.counterTrendEntry).toBe(true);
  });
});

describe("loss analysis", () => {
  test("turns losing trade clusters into repair priorities", () => {
    const summary = summarizeLossZones([
      {
        profitPercent: -2.1,
        flags: { counterTrendEntry: true, overextendedEntry: false, lateEntry: true, weakExit: true },
        entryContext: { regime: "trend_down", atrPercent: 2.2, bbWidth: 0.06 },
        exitContext: { regime: "trend_down", atrPercent: 2.4, bbWidth: 0.07 },
      },
      {
        profitPercent: -1.5,
        flags: { counterTrendEntry: true, overextendedEntry: false, lateEntry: false, weakExit: true },
        entryContext: { regime: "trend_down", atrPercent: 2.0, bbWidth: 0.05 },
        exitContext: { regime: "trend_down", atrPercent: 2.1, bbWidth: 0.05 },
      },
    ]);

    expect(summary.status).toBe("available");
    expect(summary.topLossZones[0]).toContain("trend_down");
    expect(summary.repairPriorities[0]).toContain("counter-trend");
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx vitest run C:\Users\hanji\Desktop\AF\tests\research\trade-context.test.ts C:\Users\hanji\Desktop\AF\tests\research\loss-analysis.test.ts`  
Expected: FAIL because the new modules and types do not exist yet

- [ ] **Step 3: Implement trade enrichment**

Use these shapes in `C:\Users\hanji\Desktop\AF\src\research\trade-context.ts`:

```ts
export function enrichTradesWithMarketContext(
  trades: TradeRecord[],
  bars: MarketContextBar[],
): EnrichedTradeRecord[] {
  return trades.map((trade) => {
    const entryContext = findNearestBar(trade.entryTime, bars);
    const exitContext = findNearestBar(trade.exitTime, bars);

    return {
      ...trade,
      entryContext,
      exitContext,
      flags: {
        counterTrendEntry:
          Boolean(entryContext) &&
          entryContext.regime === "trend_down" &&
          (trade.entryComment ?? "").toLowerCase().includes("entry"),
        overextendedEntry:
          Boolean(entryContext?.ema20) &&
          Boolean(trade.entryPrice) &&
          trade.entryPrice! > entryContext!.ema20! * 1.03,
        lateEntry:
          Boolean(entryContext?.ret3) && (entryContext?.ret3 ?? 0) > 0.03,
        weakExit:
          (trade.profitPercent ?? 0) < 0 && (trade.drawdownPercent ?? 0) > 1,
      },
    };
  });
}
```

- [ ] **Step 4: Implement loss-zone summarization**

Use this shape in `C:\Users\hanji\Desktop\AF\src\research\loss-analysis.ts`:

```ts
export function summarizeLossZones(
  trades: EnrichedTradeRecord[],
): LossAnalysisSummary {
  const losers = trades.filter((trade) => (trade.profitPercent ?? 0) < 0);
  if (losers.length === 0) {
    return {
      status: "unavailable_no_trades",
      summary: "No losing trades were available for loss-zone analysis.",
      topLossZones: [],
      repairPriorities: [],
    };
  }

  const counterTrendLosses = losers.filter((trade) => trade.flags.counterTrendEntry);
  const weakExitLosses = losers.filter((trade) => trade.flags.weakExit);
  const trendDownLosses = losers.filter(
    (trade) => trade.entryContext?.regime === "trend_down",
  );

  const topLossZones = [
    `trend_down:${trendDownLosses.length}`,
    `counter_trend_entry:${counterTrendLosses.length}`,
    `weak_exit:${weakExitLosses.length}`,
  ].filter((value) => !value.endsWith(":0"));

  const repairPriorities = [
    counterTrendLosses.length > 0
      ? "Reduce counter-trend long entries during trend_down regimes."
      : null,
    weakExitLosses.length > 0
      ? "Tighten exit behavior when losing trades continue into deeper drawdown."
      : null,
  ].filter((value): value is string => Boolean(value));

  return {
    status: "available",
    summary: `Analyzed ${losers.length} losing trades with QQQ 2h context.`,
    topLossZones,
    repairPriorities,
  };
}
```

- [ ] **Step 5: Run the new research tests**

Run: `npx vitest run C:\Users\hanji\Desktop\AF\tests\research\trade-context.test.ts C:\Users\hanji\Desktop\AF\tests\research\loss-analysis.test.ts`  
Expected: PASS with deterministic top loss zones and repair priorities

- [ ] **Step 6: Record commit intent**

Planned files:

```text
src/research/trade-context.ts
src/research/loss-analysis.ts
src/contracts/types.ts
tests/research/trade-context.test.ts
tests/research/loss-analysis.test.ts
```

Planned commit message:

```text
feat: add trade enrichment and loss zone analysis
```

## Task 5: Integrate Seed And Loss Analysis Into The Iteration Loop

**Files:**
- Modify: `C:\Users\hanji\Desktop\AF\src\research\iteration-runner.ts`
- Modify: `C:\Users\hanji\Desktop\AF\src\research\artifact-writer.ts`
- Modify: `C:\Users\hanji\Desktop\AF\src\contracts\types.ts`
- Modify: `C:\Users\hanji\Desktop\AF\tests\research\iteration.test.ts`

- [ ] **Step 1: Extend the iteration test with seed and loss-analysis assertions**

Add this assertion block to `C:\Users\hanji\Desktop\AF\tests\research\iteration.test.ts` inside the accepted-improvement test:

```ts
expect(result.experiment.seedStrategyId).toBe("seed_primary");
expect(result.experiment.improvementSource).toBe("seed");
expect(result.experiment.lossAnalysisSummary?.status).toBe("available");
expect(result.experiment.topLossZones?.length).toBeGreaterThan(0);
expect(result.hypothesis.nextMutationDirection).toContain("Reduce");
expect(result.experiment.artifactPaths?.tradeContextArtifact).toBeTruthy();
expect(result.experiment.artifactPaths?.lossAnalysisArtifact).toBeTruthy();
```

- [ ] **Step 2: Run the iteration test to verify it fails**

Run: `npx vitest run C:\Users\hanji\Desktop\AF\tests\research\iteration.test.ts`  
Expected: FAIL because the iteration result does not yet include seed and loss-analysis data

- [ ] **Step 3: Add artifact writing support for trade-context and loss-analysis**

Update `C:\Users\hanji\Desktop\AF\src\research\artifact-writer.ts`:

```ts
interface WriteIterationArtifactsInput {
  workspaceRoot: string;
  candidateId: string;
  iteration: number;
  syncArtifact: SyncArtifact;
  artifactBundle?: ArtifactBundle;
  objectiveArtifact?: Record<string, unknown>;
  tradeContextArtifact?: Record<string, unknown>;
  lossAnalysisArtifact?: Record<string, unknown>;
}

if (input.tradeContextArtifact) {
  const tradeContextPath = path.join(
    resultsDir,
    `trade-context-${suffix}.json`,
  );
  await writeJson(tradeContextPath, input.tradeContextArtifact);
  artifactPaths.tradeContextArtifact = tradeContextPath;
}

if (input.lossAnalysisArtifact) {
  const lossAnalysisPath = path.join(
    resultsDir,
    `loss-analysis-${suffix}.json`,
  );
  await writeJson(lossAnalysisPath, input.lossAnalysisArtifact);
  artifactPaths.lossAnalysisArtifact = lossAnalysisPath;
}
```

- [ ] **Step 4: Thread seed and loss analysis through `runSingleIteration`**

Add this flow to `C:\Users\hanji\Desktop\AF\src\research\iteration-runner.ts`:

```ts
const seedStrategy = await loadSeedStrategyReference(input.workspaceRoot);
const marketContext = await loadQqqTwoHourContext(input.workspaceRoot).catch(() => null);
const enrichedTrades =
  artifactBundle.trades.length > 0 && marketContext
    ? enrichTradesWithMarketContext(artifactBundle.trades, marketContext.bars)
    : [];
const lossAnalysis =
  marketContext === null
    ? {
        status: "market_context_unavailable",
        summary: "QQQ 2h market context was unavailable during this iteration.",
        topLossZones: [],
        repairPriorities: [],
      }
    : summarizeLossZones(enrichedTrades);

const brief = buildMutationBrief({
  objective,
  seedStrategy,
  acceptedHead: acceptedHeadScore === null ? null : {
    candidateId: acceptedHeadCandidateId,
    score: acceptedHeadScore,
  },
  recentFailures,
  recentLossAnalysis: lossAnalysis,
});
```

And add these experiment fields before persisting:

```ts
seedStrategyId: seedStrategy.candidateId,
improvementSource: acceptedRecord ? "accepted_head" : "seed",
lossAnalysisSummary: lossAnalysis,
topLossZones: lossAnalysis.topLossZones,
repairPriorities: lossAnalysis.repairPriorities,
```

- [ ] **Step 5: Run iteration-focused verification**

Run: `npx vitest run C:\Users\hanji\Desktop\AF\tests\research\iteration.test.ts C:\Users\hanji\Desktop\AF\tests\mutation\brief.test.ts C:\Users\hanji\Desktop\AF\tests\research\loss-analysis.test.ts`  
Expected: PASS and the saved experiment records now contain seed and loss-analysis summaries

- [ ] **Step 6: Record commit intent**

Planned files:

```text
src/research/iteration-runner.ts
src/research/artifact-writer.ts
src/contracts/types.ts
tests/research/iteration.test.ts
```

Planned commit message:

```text
feat: feed seed and loss analysis into the iteration loop
```

## Task 6: Add Derived Loss Views And End-To-End Regression Coverage

**Files:**
- Modify: `C:\Users\hanji\Desktop\AF\src\state\index-builder.ts`
- Modify: `C:\Users\hanji\Desktop\AF\tests\state\index-builder.test.ts`
- Modify: `C:\Users\hanji\Desktop\AF\src\state\knowledge-paths.ts`

- [ ] **Step 1: Add a failing index-builder test for the loss summary view**

Append this test to `C:\Users\hanji\Desktop\AF\tests\state\index-builder.test.ts`:

```ts
test("rebuilds loss-pattern-summary from experiment loss analysis", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "af-loss-summary-"));
  const stateRoot = path.join(root, "state", "pi-autoresearch");
  const knowledgePaths = resolveKnowledgePaths(stateRoot);

  await appendExperimentRecord(stateRoot, {
    runId: "run-3",
    iteration: 1,
    candidateId: "cand-1",
    parentCandidateId: "seed_primary",
    branchId: "main",
    acceptedHeadCandidateId: "seed_primary",
    baselineCandidateId: "seed_primary",
    candidateScore: 0.55,
    decision: "accepted_improvement",
    status: "evaluated",
    lossAnalysisSummary: {
      status: "available",
      summary: "Losses cluster in trend_down.",
      topLossZones: ["trend_down:counter_trend_entry"],
      repairPriorities: ["Reduce counter-trend entries during trend_down regimes."],
    },
    topLossZones: ["trend_down:counter_trend_entry"],
    repairPriorities: ["Reduce counter-trend entries during trend_down regimes."],
  });

  await rebuildIndexes(stateRoot);

  const lossSummary = JSON.parse(
    await readFile(knowledgePaths.lossPatternSummaryPath, "utf8"),
  );
  expect(lossSummary.topLossZones[0].label).toBe("trend_down:counter_trend_entry");
  expect(lossSummary.topRepairPriorities[0].label).toContain("Reduce counter-trend");
});
```

- [ ] **Step 2: Run the index-builder tests to verify they fail**

Run: `npx vitest run C:\Users\hanji\Desktop\AF\tests\state\index-builder.test.ts`  
Expected: FAIL because `lossPatternSummaryPath` and the new view are not yet generated

- [ ] **Step 3: Implement the derived loss summary view**

Update `C:\Users\hanji\Desktop\AF\src\state\index-builder.ts` with aggregation logic:

```ts
const lossZoneCounts = new Map<string, number>();
const repairPriorityCounts = new Map<string, number>();

for (const record of records) {
  for (const zone of record.topLossZones ?? []) {
    lossZoneCounts.set(zone, (lossZoneCounts.get(zone) ?? 0) + 1);
  }
  for (const priority of record.repairPriorities ?? []) {
    repairPriorityCounts.set(priority, (repairPriorityCounts.get(priority) ?? 0) + 1);
  }
}

await writeJson(paths.lossPatternSummaryPath, {
  generatedAt: new Date().toISOString(),
  topLossZones: [...lossZoneCounts.entries()]
    .sort((left, right) => right[1] - left[1])
    .map(([label, count]) => ({ label, count })),
  topRepairPriorities: [...repairPriorityCounts.entries()]
    .sort((left, right) => right[1] - left[1])
    .map(([label, count]) => ({ label, count })),
});
```

- [ ] **Step 4: Run the full targeted regression set**

Run:

```powershell
npx vitest run `
  C:\Users\hanji\Desktop\AF\tests\research\seed-strategy.test.ts `
  C:\Users\hanji\Desktop\AF\tests\mutation\brief.test.ts `
  C:\Users\hanji\Desktop\AF\tests\research\market-context.test.ts `
  C:\Users\hanji\Desktop\AF\tests\research\trade-context.test.ts `
  C:\Users\hanji\Desktop\AF\tests\research\loss-analysis.test.ts `
  C:\Users\hanji\Desktop\AF\tests\research\iteration.test.ts `
  C:\Users\hanji\Desktop\AF\tests\state\index-builder.test.ts
```

Expected: PASS for all new and updated focused tests

- [ ] **Step 5: Run project-wide validation**

Run:

```powershell
npx vitest run
npx tsc -p C:\Users\hanji\Desktop\AF\tsconfig.json --noEmit
```

Expected:

- `vitest` PASS
- `tsc` exits with no errors

- [ ] **Step 6: Record commit intent**

Planned files:

```text
src/state/index-builder.ts
src/state/knowledge-paths.ts
tests/state/index-builder.test.ts
```

Planned commit message:

```text
feat: add derived loss pattern view
```

## Spec Coverage Check

- Curated seed strategy support: covered by Task 1 and Task 5
- Seed vs accepted-head distinction in briefs: covered by Task 2 and Task 5
- QQQ 2-hour context cache: covered by Task 3
- Trade-to-market enrichment: covered by Task 4
- Loss-zone evidence and repair priorities: covered by Task 4 and Task 5
- Experiment ledger and artifact persistence: covered by Task 5
- Derived loss summary view: covered by Task 6
- Error handling for no-trade and missing-context cases: covered by Task 4 and Task 5 tests plus implementation steps

## Placeholder Scan

- No `TODO`, `TBD`, or "implement later" placeholders remain.
- Each task includes exact file paths, concrete commands, and concrete code snippets.

## Type Consistency Check

- `seedStrategy`, `improvementSource`, `lossAnalysisSummary`, `topLossZones`, and `repairPriorities` use the same names across contracts, brief generation, iteration records, and index rebuilding.
- `MarketContextBar`, `EnrichedTradeRecord`, and `LossAnalysisSummary` are introduced once and then reused consistently in later tasks.
