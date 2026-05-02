import { describe, expect, test } from "vitest";

import { parseAfStrategyConfig } from "../../src/automation/local-backtest/af-config.js";
import { renderAfStrategySpecToPine } from "../../src/strategy-spec/codegen-pine.js";
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

    expect(parsed.issues).toEqual([]);
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
});
