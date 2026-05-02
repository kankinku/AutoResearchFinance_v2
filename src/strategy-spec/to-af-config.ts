import {
  parseAfStrategyConfig,
  type AfStrategyConfig,
} from "../automation/local-backtest/af-config.js";
import { type AfStrategySpec, parseAfStrategySpec } from "./schema.js";

export function afStrategySpecToConfig(input: unknown): AfStrategyConfig {
  const spec = parseAfStrategySpec(input);
  return {
    studyTitle: spec.name,
    initialCapital: 100_000,
    commissionPercent: 0.05,
    L1: spec.event.L1,
    L2: Math.max(spec.event.L2, spec.event.L1 + 1),
    L3: Math.max(spec.event.L3, Math.max(spec.event.L2, spec.event.L1 + 1) + 1),
    confirmBars: spec.event.confirmBars,
    emaLen: 21,
    baseEmaLen: 55,
    rsiLen: 14,
    maxExtPct: spec.regime.maxExtPct,
    riskOffRsi: spec.regime.riskOffRsi,
    slotPct: spec.slot.slotPct,
    maxSlots: spec.slot.maxSlots,
    useReplacement: spec.slot.useReplacement,
    replaceMinRank: spec.slot.replaceMinRank,
    replaceIfPnlBelow: spec.slot.replaceIfPnlBelow,
    applyFilterToB1: spec.entry.applyFilterToB1,
    minQty: 1,
    closeAllOnBearConfRiskOff: spec.exit.closeAllOnBearConfRiskOff,
    sameBarConflictMode: "StrongWins",
    trendMode: spec.regime.trendMode,
    allowStrongCounterTrend: spec.entry.allowBearRebound,
    entryCooldownBars: spec.entry.cooldownBars,
    useRealFillSync: true,
    resetOnL3: spec.exit.resetOnL3,
    useSupertrendFilter: spec.regime.useSupertrendFilter,
    supertrendAtrPeriod: 10,
    supertrendFactor: 3,
    supertrendBlocksWeakBull: true,
    supertrendRiskOffEnabled: true,
    enableWeakRangeExit: spec.exit.weakRangeExit,
    weakExitAtrLen: 14,
    weakExitBars: 5,
    weakRunupAtrMax: 0.6,
    weakLossAtrMin: 0.9,
    weakSlopeAtrMax: 0.18,
    eventFloorBars: spec.event.eventFloorBars,
    eventWindowBars: spec.event.eventWindowBars,
    maxHoldBars: spec.exit.maxHoldBars,
    bullContinueWindow:
      spec.event.source === "af_exhaustion" ? null : spec.event.eventWindowBars,
    bearReboundWindow:
      spec.event.source === "af_exhaustion" ? null : spec.event.eventWindowBars,
  };
}

export function afStrategySpecFromPine(source: string): {
  spec: AfStrategySpec | null;
  issues: string[];
} {
  const parsed = parseAfStrategyConfig(source);
  if (parsed.issues.length > 0) {
    return {
      spec: null,
      issues: parsed.issues,
    };
  }

  return {
    spec: parseAfStrategySpec({
      version: "af-spec/v1",
      name: parsed.config.studyTitle ?? "AF Spec v1",
      event: {
        source:
          parsed.config.eventFloorBars != null ||
          parsed.config.eventWindowBars != null
            ? "event_floor"
            : "af_exhaustion",
        L1: parsed.config.L1,
        L2: parsed.config.L2,
        L3: parsed.config.L3,
        confirmBars: parsed.config.confirmBars,
        eventFloorBars: parsed.config.eventFloorBars,
        eventWindowBars: parsed.config.eventWindowBars,
      },
      regime: {
        trendMode: parsed.config.trendMode,
        useSupertrendFilter: parsed.config.useSupertrendFilter,
        riskOffRsi: parsed.config.riskOffRsi,
        maxExtPct: parsed.config.maxExtPct,
      },
      entry: {
        primaryTrigger: "bull_event",
        cooldownBars: parsed.config.entryCooldownBars,
        allowBearRebound: parsed.config.allowStrongCounterTrend,
        applyFilterToB1: parsed.config.applyFilterToB1,
      },
      slot: {
        slotPct: parsed.config.slotPct,
        maxSlots: parsed.config.maxSlots,
        useReplacement: parsed.config.useReplacement,
        replaceMinRank: parsed.config.replaceMinRank,
        replaceIfPnlBelow: parsed.config.replaceIfPnlBelow,
      },
      exit: {
        weakRangeExit: parsed.config.enableWeakRangeExit,
        maxHoldBars: parsed.config.maxHoldBars,
        closeAllOnBearConfRiskOff: parsed.config.closeAllOnBearConfRiskOff,
        resetOnL3: parsed.config.resetOnL3,
      },
    }),
    issues: [],
  };
}
