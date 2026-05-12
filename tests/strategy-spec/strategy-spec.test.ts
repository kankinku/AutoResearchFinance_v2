import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { describe, expect, test } from "vitest";

import { parseAfStrategyConfig } from "../../src/automation/local-backtest/af-config.js";
import { persistCandidateArtifact } from "../../src/mutation/candidate-store.js";
import { AUTORESEARCH_CONTRACT_VERSION } from "../../src/policy/autoresearch-contract.js";
import { renderAfStrategySpecToPine } from "../../src/strategy-spec/codegen-pine.js";
import { hashAfStrategySpec } from "../../src/strategy-spec/hash.js";
import { afStrategySpecToConfig, afStrategySpecFromPine } from "../../src/strategy-spec/to-af-config.js";
import { validateAfStrategySpec } from "../../src/strategy-spec/validate.js";

const spec = {
  version: "af-spec/v1" as const,
  name: "AF Spec Test",
  event: {
    source: "event_floor" as const,
    L1: 8,
    L2: 12,
    L3: 15,
    confirmBars: 2,
    eventFloorBars: 5,
    eventWindowBars: 10,
  },
  regime: {
    trendMode: "Balanced" as const,
    useSupertrendFilter: true,
    riskOffRsi: 44,
    maxExtPct: 5.5,
  },
  entry: {
    primaryTrigger: "bull_event",
    cooldownBars: 1,
    allowBearRebound: true,
    applyFilterToB1: false,
  },
  slot: {
    slotPct: 12,
    maxSlots: 14,
    useReplacement: true,
    replaceMinRank: 3,
    replaceIfPnlBelow: -4,
  },
  exit: {
    weakRangeExit: true,
    maxHoldBars: 18,
    closeAllOnBearConfRiskOff: true,
    resetOnL3: false,
  },
};

describe("AF strategy spec v1", () => {
  test("converts spec to local AF config", () => {
    const config = afStrategySpecToConfig(spec);

    expect(config.studyTitle).toBe("AF Spec Test");
    expect(config.L1).toBe(8);
    expect(config.L2).toBe(12);
    expect(config.L3).toBe(15);
    expect(config.eventWindowBars).toBe(10);
    expect(config.maxHoldBars).toBe(18);
  });

  test("generates Pine that satisfies the local compatibility parser", () => {
    const pine = renderAfStrategySpecToPine(spec);
    const parsed = parseAfStrategyConfig(pine);

    expect(pine).toContain("// AF_SPEC_VERSION=af-spec/v1");
    expect(pine).toContain(`// AF_SPEC_HASH=${hashAfStrategySpec(spec)}`);
    expect(pine).toContain(`// AF_CONTRACT_VERSION=${AUTORESEARCH_CONTRACT_VERSION}`);
    expect(pine).toContain("process_orders_on_close=true");
    expect(pine).toContain('plot(close, "AF compile sentinel", display=display.none)');
    expect(pine).toContain("backtestStartTime = input.time");
    expect(pine).toContain("inBacktestWindow");
    expect(pine).toContain("localBarIndex");
    expect(pine).toContain("AFTRACE|v1|");
    expect(pine).toContain("alert_message=trace");
    expect(pine).toContain("f_entry_qty");
    expect(pine).toContain("strategy.equity * (pct * 0.01)");
    expect(pine).toContain("array.push(slotIds, newId)");
    expect(pine).toContain("emaSeed = ta.sma(close, emaLen)");
    expect(pine).toContain("baseEmaSeed = ta.sma(close, baseEmaLen)");
    expect(pine).toContain("ema = f_local_ema(close, emaLen, emaSeed)");
    expect(pine).not.toContain("na(out[1]) ? ta.sma(src, length)");
    expect(pine).not.toContain("float seed = ta.sma(src, length)");
    expect(pine).toContain("f_close_slot");
    expect(pine).toContain("entryBar < localBarIndex");
    expect(pine).toContain("freshEntryWouldCloseOnBear");
    expect(pine).toContain("max_hold_bars");
    expect(pine).toContain("weak_range_exit");
    expect(parsed.issues).toEqual([]);
    expect(parsed.config.processOrdersOnClose).toBe(true);
    expect(parsed.config.slotPct).toBe(12);
    expect(parsed.config.maxSlots).toBe(14);
    expect(parsed.config.useSupertrendFilter).toBe(true);
  });

  test("validates generated spec compatibility and can reverse parse generated Pine", () => {
    const validation = validateAfStrategySpec(spec);
    const roundTrip = afStrategySpecFromPine(renderAfStrategySpecToPine(spec));

    expect(validation.ok).toBe(true);
    expect(validation.issues).toEqual([]);
    expect(roundTrip.issues).toEqual([]);
    expect(roundTrip.spec?.event.eventWindowBars).toBe(10);
  });

  test("persists the strategy spec beside the generated candidate Pine", async () => {
    const workspaceRoot = await mkdtemp(path.join(tmpdir(), "af-spec-candidate-"));
    const artifact = await persistCandidateArtifact({
      workspaceRoot,
      parentCandidateId: null,
      branchId: "test",
      parsedMutation: {
        candidateSummary: "Spec-backed candidate",
        nextMutationHints: ["verify promotion evidence"],
        pineScript: renderAfStrategySpecToPine(spec),
        strategySpec: spec,
        specPatch: {
          version: "af-spec-patch/v1",
          summary: "Persist spec-backed candidate artifact.",
          operations: [
            {
              path: "/entry",
              after: spec.entry,
              reason: "Exercise structured patch persistence with an editable entry change.",
            },
          ],
        },
        inventory: [
          {
            conditionId: "entry-bull-event",
            role: "entry",
            summary: "Bull event entry",
            pineLineHints: [1],
          },
        ],
        inventorySource: "llm",
        missingFields: [],
        inferredFields: [],
      },
    });

    expect(artifact.specPath).toBeTruthy();
    expect(artifact.specHash).toBe(hashAfStrategySpec(spec));
    const persisted = JSON.parse(await readFile(artifact.specPath ?? "", "utf8")) as {
      version?: string;
      event?: { eventWindowBars?: number };
    };
    expect(persisted.version).toBe("af-spec/v1");
    expect(persisted.event?.eventWindowBars).toBe(10);
  });
});
