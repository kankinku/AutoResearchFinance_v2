import { type AfStrategyConfig } from "../automation/local-backtest/af-config.js";
import { AUTORESEARCH_CONTRACT_VERSION } from "../policy/autoresearch-contract.js";
import { hashAfStrategySpec, normalizeAfStrategySpec } from "./hash.js";
import { afStrategySpecToConfig } from "./to-af-config.js";

export function renderAfStrategySpecToPine(input: unknown): string {
  const spec = normalizeAfStrategySpec(input);
  const config = afStrategySpecToConfig(spec);
  const specHash = hashAfStrategySpec(spec);
  const optionalInputs = [
    renderOptionalIntInput("eventFloorBars", config.eventFloorBars),
    renderOptionalIntInput("eventWindowBars", config.eventWindowBars),
    renderOptionalIntInput("maxHoldBars", config.maxHoldBars),
    renderOptionalIntInput("bullContinueWindow", config.bullContinueWindow),
    renderOptionalIntInput("bearReboundWindow", config.bearReboundWindow),
  ].filter((line): line is string => line != null);

  return [
    "//@version=5",
    `// AF_SPEC_VERSION=${spec.version}`,
    `// AF_SPEC_HASH=${specHash}`,
    `// AF_CONTRACT_VERSION=${AUTORESEARCH_CONTRACT_VERSION}`,
    `strategy(${quote(config.studyTitle ?? "AF Spec v1")}, overlay=true, initial_capital=${config.initialCapital}, commission_type=strategy.commission.percent, commission_value=${config.commissionPercent}, pyramiding=${config.maxSlots})`,
    "",
    renderIntInput("L1", config.L1),
    renderIntInput("L2", config.L2),
    renderIntInput("L3", config.L3),
    renderIntInput("confirmBars", config.confirmBars),
    renderIntInput("emaLen", config.emaLen),
    renderIntInput("baseEmaLen", config.baseEmaLen),
    renderIntInput("rsiLen", config.rsiLen),
    renderFloatInput("maxExtPct", config.maxExtPct),
    renderFloatInput("riskOffRsi", config.riskOffRsi),
    renderFloatInput("slotPct", config.slotPct),
    renderIntInput("maxSlots", config.maxSlots),
    renderBoolInput("useReplacement", config.useReplacement),
    renderIntInput("replaceMinRank", config.replaceMinRank),
    renderFloatInput("replaceIfPnlBelow", config.replaceIfPnlBelow),
    renderBoolInput("applyFilterToB1", config.applyFilterToB1),
    renderFloatInput("minQty", config.minQty),
    renderBoolInput("closeAllOnBearConfRiskOff", config.closeAllOnBearConfRiskOff),
    renderStringInput("sameBarConflictMode", config.sameBarConflictMode, [
      "StrongWins",
      "SkipBoth",
      "BearPriority",
    ]),
    renderStringInput("trendMode", config.trendMode, [
      "Strict",
      "Balanced",
      "Loose",
    ]),
    renderBoolInput("allowStrongCounterTrend", config.allowStrongCounterTrend),
    renderIntInput("entryCooldownBars", config.entryCooldownBars),
    renderBoolInput("useRealFillSync", config.useRealFillSync),
    renderBoolInput("resetOnL3", config.resetOnL3),
    renderBoolInput("useSupertrendFilter", config.useSupertrendFilter),
    renderIntInput("supertrendAtrPeriod", config.supertrendAtrPeriod),
    renderFloatInput("supertrendFactor", config.supertrendFactor),
    renderBoolInput("supertrendBlocksWeakBull", config.supertrendBlocksWeakBull),
    renderBoolInput("supertrendRiskOffEnabled", config.supertrendRiskOffEnabled),
    renderBoolInput("enableWeakRangeExit", config.enableWeakRangeExit),
    renderIntInput("weakExitAtrLen", config.weakExitAtrLen),
    renderIntInput("weakExitBars", config.weakExitBars),
    renderFloatInput("weakRunupAtrMax", config.weakRunupAtrMax),
    renderFloatInput("weakLossAtrMin", config.weakLossAtrMin),
    renderFloatInput("weakSlopeAtrMax", config.weakSlopeAtrMax),
    ...optionalInputs,
    "",
    "f_find_weakest_idx() =>",
    "    0",
    "",
    "emaFast = ta.ema(close, emaLen)",
    "emaBase = ta.ema(close, baseEmaLen)",
    "rsi = ta.rsi(close, rsiLen)",
    "bullEvent = close < close[4]",
    "bearEvent = close > close[4]",
    "riskOff = rsi < riskOffRsi",
    "trendPass = trendMode == \"Loose\" or close >= emaBase or allowStrongCounterTrend",
    "entryPass = bullEvent and trendPass and not riskOff",
    "if entryPass",
    "    strategy.entry(\"AF-L\", strategy.long, qty=minQty)",
    "if bearEvent and closeAllOnBearConfRiskOff",
    "    strategy.close_all(comment=\"bear_event\")",
    "",
  ].join("\n");
}

function renderIntInput(name: keyof AfStrategyConfig, value: number): string {
  return `${name} = input.int(${formatNumber(value)}, ${quote(name)})`;
}

function renderFloatInput(name: keyof AfStrategyConfig, value: number): string {
  return `${name} = input.float(${formatNumber(value)}, ${quote(name)})`;
}

function renderBoolInput(name: keyof AfStrategyConfig, value: boolean): string {
  return `${name} = input.bool(${value ? "true" : "false"}, ${quote(name)})`;
}

function renderStringInput(
  name: keyof AfStrategyConfig,
  value: string,
  options: string[],
): string {
  return `${name} = input.string(${quote(value)}, ${quote(name)}, options=[${options
    .map(quote)
    .join(", ")}])`;
}

function renderOptionalIntInput(
  name: keyof AfStrategyConfig,
  value: number | null,
): string | null {
  return value == null ? null : renderIntInput(name, value);
}

function formatNumber(value: number): string {
  return Number.isInteger(value) ? value.toFixed(0) : String(value);
}

function quote(value: string): string {
  return JSON.stringify(value);
}
