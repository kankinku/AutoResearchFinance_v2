import { describe, expect, test } from "vitest";

import {
  parseMutationResponse,
  parseMutationResponseStrict,
} from "../../src/mutation/parser.js";

const strategySpec = {
  version: "af-spec/v1" as const,
  name: "Strict Spec Candidate",
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

describe("parseMutationResponse", () => {
  test("parses structured JSON with pine script and inventory", () => {
    const response = JSON.stringify({
      candidateSummary: "EMA and RSI entry refinement",
      nextMutationHints: ["tighten risk exit", "test volatility filter"],
      pineScript: "//@version=5\nstrategy('Test', overlay=true)\n",
      inventory: [
        {
          conditionId: "entry-ema-cross",
          role: "entry",
          summary: "Fast EMA above slow EMA",
          pineLineHints: [8, 12],
        },
      ],
    });

    const parsed = parseMutationResponse(response);

    expect(parsed.candidateSummary).toBe("EMA and RSI entry refinement");
    expect(parsed.inventory[0]?.conditionId).toBe("entry-ema-cross");
    expect(parsed.pineScript).toContain("strategy('Test'");
  });

  test("accepts alternate pine-only payloads and infers missing fields", () => {
    const parsed = parseMutationResponse(
      JSON.stringify({
        pine: [
          "//@version=5",
          "strategy('Alt Test', overlay=true)",
          "trendUp = close > ta.ema(close, 200)",
          "longEntry = trendUp and ta.rsi(close, 14) > 55",
          "if longEntry",
          "    strategy.entry('Long', strategy.long)",
        ].join("\n"),
      }),
    );

    expect(parsed.candidateSummary).toContain("Alt Test");
    expect(parsed.inventory.length).toBeGreaterThan(0);
    expect(parsed.inventory[0]?.pineLineHints.length).toBeGreaterThan(0);
    expect(parsed.pineScript).toContain("strategy('Alt Test'");
  });

  test("rejects payloads that omit Pine code entirely", () => {
    expect(() => parseMutationResponse(JSON.stringify({ candidateSummary: "invalid" }))).toThrow(
      /pineScript|Pine code/i,
    );
  });

  test("strict parser renders deterministic Pine from strategySpec", () => {
    const parsed = parseMutationResponseStrict(
      JSON.stringify({
        candidateSummary: "Strict spec candidate",
        nextMutationHints: ["verify in TradingView"],
        strategySpec,
        specPatch: {
          version: "af-spec-patch/v1",
          summary: "Enable event-floor AF entry for strict parser coverage.",
          operations: [
            {
              path: "/event",
              after: strategySpec.event,
              reason: "Test strict parsing of a structured AF event patch.",
            },
          ],
        },
        inventory: [
          {
            conditionId: "entry-bull-event",
            role: "entry",
            summary: "Bull event entry from AF spec",
            pineLineHints: [1],
          },
        ],
      }),
    );

    expect(parsed.strategySpec?.version).toBe("af-spec/v1");
    expect(parsed.pineScript).toContain("Strict Spec Candidate");
    expect(parsed.inferredFields).toEqual([]);
  });

  test("strict parser rejects legacy Pine-only payloads", () => {
    expect(() =>
      parseMutationResponseStrict(
        JSON.stringify({
          candidateSummary: "Legacy Pine only",
          nextMutationHints: [],
          pineScript: "//@version=5\nstrategy('Legacy', overlay=true)\n",
          inventory: [
            {
              conditionId: "entry-legacy",
              role: "entry",
              summary: "Legacy entry",
              pineLineHints: [1],
            },
          ],
        }),
      ),
    ).toThrow(/strategySpec|specPatch/i);
  });
});
