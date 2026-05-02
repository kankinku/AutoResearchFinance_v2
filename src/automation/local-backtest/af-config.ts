import { extractStudyTitle } from "../tradingview/pine-study.js";
import {
  type LocalCompatibilityContract,
  type LocalCompatibilityIssue,
} from "../../contracts/types.js";

export type ConflictMode = "StrongWins" | "SkipBoth" | "BearPriority";
export type TrendMode = "Strict" | "Balanced" | "Loose";

export interface AfStrategyConfig {
  studyTitle: string | null;
  initialCapital: number;
  commissionPercent: number;
  processOrdersOnClose: boolean;
  L1: number;
  L2: number;
  L3: number;
  confirmBars: number;
  emaLen: number;
  baseEmaLen: number;
  rsiLen: number;
  maxExtPct: number;
  riskOffRsi: number;
  slotPct: number;
  maxSlots: number;
  useReplacement: boolean;
  replaceMinRank: number;
  replaceIfPnlBelow: number;
  applyFilterToB1: boolean;
  minQty: number;
  closeAllOnBearConfRiskOff: boolean;
  sameBarConflictMode: ConflictMode;
  trendMode: TrendMode;
  allowStrongCounterTrend: boolean;
  entryCooldownBars: number;
  useRealFillSync: boolean;
  resetOnL3: boolean;
  useSupertrendFilter: boolean;
  supertrendAtrPeriod: number;
  supertrendFactor: number;
  supertrendBlocksWeakBull: boolean;
  supertrendRiskOffEnabled: boolean;
  enableWeakRangeExit: boolean;
  weakExitAtrLen: number;
  weakExitBars: number;
  weakRunupAtrMax: number;
  weakLossAtrMin: number;
  weakSlopeAtrMax: number;
  eventFloorBars: number | null;
  eventWindowBars: number | null;
  maxHoldBars: number | null;
  bullContinueWindow: number | null;
  bearReboundWindow: number | null;
}

export interface ParsedAfStrategyConfig {
  config: AfStrategyConfig;
  issues: string[];
  compatibilityIssues: LocalCompatibilityIssue[];
}

const DEFAULT_CONFIG: AfStrategyConfig = {
  studyTitle: "AF Local Backtest",
  initialCapital: 100_000,
  commissionPercent: 0.05,
  processOrdersOnClose: true,
  L1: 9,
  L2: 12,
  L3: 14,
  confirmBars: 2,
  emaLen: 21,
  baseEmaLen: 55,
  rsiLen: 14,
  maxExtPct: 6,
  riskOffRsi: 45,
  slotPct: 15,
  maxSlots: 18,
  useReplacement: true,
  replaceMinRank: 3,
  replaceIfPnlBelow: -5,
  applyFilterToB1: false,
  minQty: 1,
  closeAllOnBearConfRiskOff: true,
  sameBarConflictMode: "StrongWins",
  trendMode: "Balanced",
  allowStrongCounterTrend: true,
  entryCooldownBars: 0,
  useRealFillSync: true,
  resetOnL3: false,
  useSupertrendFilter: false,
  supertrendAtrPeriod: 10,
  supertrendFactor: 3,
  supertrendBlocksWeakBull: true,
  supertrendRiskOffEnabled: true,
  enableWeakRangeExit: true,
  weakExitAtrLen: 14,
  weakExitBars: 5,
  weakRunupAtrMax: 0.6,
  weakLossAtrMin: 0.9,
  weakSlopeAtrMax: 0.18,
  eventFloorBars: null,
  eventWindowBars: null,
  maxHoldBars: null,
  bullContinueWindow: null,
  bearReboundWindow: null,
};

const REQUIRED_INPUT_NAMES: Array<keyof AfStrategyConfig> = [
  "L1",
  "L2",
  "L3",
  "confirmBars",
  "emaLen",
  "baseEmaLen",
  "rsiLen",
  "maxExtPct",
  "riskOffRsi",
  "slotPct",
  "maxSlots",
  "useReplacement",
  "replaceMinRank",
  "replaceIfPnlBelow",
  "applyFilterToB1",
  "minQty",
  "closeAllOnBearConfRiskOff",
  "sameBarConflictMode",
  "trendMode",
  "allowStrongCounterTrend",
  "entryCooldownBars",
  "useRealFillSync",
  "resetOnL3",
  "useSupertrendFilter",
  "supertrendAtrPeriod",
  "supertrendFactor",
  "supertrendBlocksWeakBull",
  "supertrendRiskOffEnabled",
  "enableWeakRangeExit",
  "weakExitAtrLen",
  "weakExitBars",
  "weakRunupAtrMax",
  "weakLossAtrMin",
  "weakSlopeAtrMax",
];

const REQUIRED_HELPER_FUNCTIONS = ["f_find_weakest_idx"] as const;

const OPTIONAL_ROUTE_INPUT_NAMES: Array<keyof AfStrategyConfig> = [
  "eventFloorBars",
  "eventWindowBars",
  "maxHoldBars",
  "bullContinueWindow",
  "bearReboundWindow",
];

const FORBIDDEN_PATTERNS = [
  "indicator(",
  "study(",
  "request.security_lower_tf(",
] as const;

export const AF_LOCAL_COMPATIBILITY_CONTRACT: LocalCompatibilityContract = {
  strategyFamily: "AF",
  requiredInputs: [...REQUIRED_INPUT_NAMES],
  requiredFunctions: [...REQUIRED_HELPER_FUNCTIONS],
  forbiddenPatterns: [...FORBIDDEN_PATTERNS],
  supportedSymbols: ["QQQ"],
  supportedTimeframes: ["120", "120m", "2h"],
  supportedChartTargets: ["QQQ:120", "QQQ:120m", "QQQ:2h"],
  notes: [
    "Emit a Pine v5 strategy() script.",
    "Define every required AF input via input.* declarations.",
    "Keep enableWeakRangeExit as an explicit input bool.",
    "Use process_orders_on_close=true for close-fill local parity.",
  ],
  compatibleSeedCandidatePath: null,
};

const INPUT_ALIASES: Partial<Record<keyof AfStrategyConfig, string[]>> = {
  L1: ["L1", "L1_in"],
  L2: ["L2", "L2_in"],
  L3: ["L3", "L3_in"],
  eventWindowBars: [
    "eventWindowBars",
    "entryWindowBars",
    "windowBars",
    "rotationWindowBars",
  ],
  maxHoldBars: ["maxHoldBars", "holdBars", "holdBars4"],
};

export function getAfLocalCompatibilityContract(): LocalCompatibilityContract {
  return {
    ...AF_LOCAL_COMPATIBILITY_CONTRACT,
    requiredInputs: [...AF_LOCAL_COMPATIBILITY_CONTRACT.requiredInputs],
    requiredFunctions: [...AF_LOCAL_COMPATIBILITY_CONTRACT.requiredFunctions],
    forbiddenPatterns: [...AF_LOCAL_COMPATIBILITY_CONTRACT.forbiddenPatterns],
    supportedSymbols: [...AF_LOCAL_COMPATIBILITY_CONTRACT.supportedSymbols],
    supportedTimeframes: [...AF_LOCAL_COMPATIBILITY_CONTRACT.supportedTimeframes],
    supportedChartTargets: [...AF_LOCAL_COMPATIBILITY_CONTRACT.supportedChartTargets],
    notes: [...AF_LOCAL_COMPATIBILITY_CONTRACT.notes],
  };
}

export function parseAfStrategyConfig(source: string): ParsedAfStrategyConfig {
  const parsedInputs = new Map<string, string>();
  const inputPattern =
    /^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*input\.(int|float|bool|string)\(\s*([^,\r\n]+)\s*,/gm;

  for (const match of source.matchAll(inputPattern)) {
    const [, variableName, inputType, rawValue] = match;
    parsedInputs.set(variableName, normalizeInputValue(rawValue, inputType));
  }

  const issues: string[] = [];
  const compatibilityIssues: LocalCompatibilityIssue[] = [];
  const config: AfStrategyConfig = {
    ...DEFAULT_CONFIG,
    studyTitle: extractStudyTitle(source),
    initialCapital: parseNamedNumber(source, "initial_capital", DEFAULT_CONFIG.initialCapital),
    commissionPercent: parseNamedNumber(source, "commission_value", DEFAULT_CONFIG.commissionPercent),
    processOrdersOnClose: parseNamedBoolean(
      source,
      "process_orders_on_close",
      DEFAULT_CONFIG.processOrdersOnClose,
    ),
  };

  for (const name of AF_LOCAL_COMPATIBILITY_CONTRACT.requiredInputs as Array<keyof AfStrategyConfig>) {
    const rawValue = resolveParsedInputValue(parsedInputs, name);
    if (rawValue == null) {
      issues.push(`missing_input:${name}`);
      compatibilityIssues.push({
        kind: "missing_input",
        code: `missing_input:${name}`,
        field: name,
        detail: `Required AF input "${name}" is missing.`,
      });
      continue;
    }

    assignParsedValue(config, name, rawValue);
  }

  for (const name of OPTIONAL_ROUTE_INPUT_NAMES) {
    const rawValue =
      resolveParsedInputValue(parsedInputs, name) ??
      resolveParsedVariableNumber(source, name) ??
      resolveDerivedRouteValue(source, name);
    if (rawValue != null) {
      assignParsedValue(config, name, rawValue);
    }
  }

  for (const functionName of AF_LOCAL_COMPATIBILITY_CONTRACT.requiredFunctions) {
    if (source.includes(functionName)) {
      continue;
    }
    issues.push(`missing_function:${functionName}`);
    compatibilityIssues.push({
      kind: "missing_function",
      code: `missing_function:${functionName}`,
      field: functionName,
      detail: `Required AF helper function "${functionName}" is missing.`,
    });
  }

  if (!source.includes("strategy(")) {
    issues.push("unsupported_pattern:missing_strategy_declaration");
    compatibilityIssues.push({
      kind: "unsupported_pattern",
      code: "unsupported_pattern:missing_strategy_declaration",
      field: null,
      detail: "Candidate is missing a strategy() declaration.",
    });
  }

  for (const pattern of AF_LOCAL_COMPATIBILITY_CONTRACT.forbiddenPatterns) {
    if (pattern === "indicator(" || pattern === "study(") {
      if (source.includes(pattern)) {
        issues.push(`unsupported_pattern:${pattern}`);
        compatibilityIssues.push({
          kind: "unsupported_pattern",
          code: `unsupported_pattern:${pattern}`,
          field: null,
          detail: `Candidate uses forbidden pattern "${pattern}".`,
        });
      }
      continue;
    }
    if (source.includes(pattern)) {
      issues.push(`unsupported_pattern:${pattern}`);
      compatibilityIssues.push({
        kind: "unsupported_pattern",
        code: `unsupported_pattern:${pattern}`,
        field: null,
        detail: `Candidate uses unsupported pattern "${pattern}".`,
      });
    }
  }

  if (compatibilityIssues.length > 0) {
    issues.push("unsupported_strategy_family");
  }

  config.L2 = Math.max(config.L2, config.L1 + 1);
  config.L3 = Math.max(config.L3, config.L2 + 1);

  return {
    config,
    issues,
    compatibilityIssues,
  };
}

export function summarizeAfCompatibilityIssues(
  issues: LocalCompatibilityIssue[],
): {
  missingInputs: string[];
  missingFunctions: string[];
  unsupportedPatterns: string[];
} {
  return issues.reduce(
    (summary, issue) => {
      if (issue.kind === "missing_input" && issue.field) {
        summary.missingInputs.push(issue.field);
      } else if (issue.kind === "missing_function" && issue.field) {
        summary.missingFunctions.push(issue.field);
      } else {
        summary.unsupportedPatterns.push(issue.code);
      }
      return summary;
    },
    {
      missingInputs: [] as string[],
      missingFunctions: [] as string[],
      unsupportedPatterns: [] as string[],
    },
  );
}

function resolveParsedInputValue(
  parsedInputs: Map<string, string>,
  name: keyof AfStrategyConfig,
): string | undefined {
  const aliases = INPUT_ALIASES[name] ?? [name];
  for (const alias of aliases) {
    const value = parsedInputs.get(alias);
    if (value != null) {
      return value;
    }
  }

  return undefined;
}

function resolveParsedVariableNumber(
  source: string,
  name: keyof AfStrategyConfig,
): string | undefined {
  const aliases = INPUT_ALIASES[name] ?? [name];
  for (const alias of aliases) {
    const pattern = new RegExp(
      `^\\s*${escapeForRegex(alias)}\\s*=\\s*(-?\\d+(?:\\.\\d+)?)\\s*(?:$|//)`,
      "m",
    );
    const match = source.match(pattern);
    if (match) {
      return match[1];
    }
  }

  return undefined;
}

function resolveDerivedRouteValue(
  source: string,
  name: keyof AfStrategyConfig,
): string | undefined {
  if (name === "eventWindowBars") {
    return resolveMaxConditionalVariableNumber(source, [
      "windowBars",
      "rotationWindowBars",
    ]);
  }

  if (name === "maxHoldBars") {
    return resolveMaxRankHoldBars(source);
  }

  return undefined;
}

function resolveMaxConditionalVariableNumber(
  source: string,
  aliases: string[],
): string | undefined {
  for (const alias of aliases) {
    const expression = resolveVariableExpression(source, alias);
    if (!expression) {
      continue;
    }

    const branchValues = [...expression.matchAll(/[?:]\s*(-?\d+(?:\.\d+)?)/g)]
      .map((match) => Number.parseFloat(match[1] ?? ""))
      .filter(Number.isFinite);
    if (branchValues.length > 0) {
      return `${Math.max(...branchValues)}`;
    }

    const simpleValue = expression.match(/^\s*(-?\d+(?:\.\d+)?)\s*$/)?.[1];
    if (simpleValue != null) {
      return simpleValue;
    }
  }

  return undefined;
}

function resolveMaxRankHoldBars(source: string): string | undefined {
  const values = ["holdBars1", "holdBars2", "holdBars3", "holdBars4"]
    .map((alias) => resolveVariableExpression(source, alias))
    .map((expression) => expression?.match(/^\s*(-?\d+(?:\.\d+)?)\s*$/)?.[1])
    .filter((value): value is string => value != null)
    .map((value) => Number.parseFloat(value))
    .filter(Number.isFinite);

  if (values.length === 0) {
    return undefined;
  }

  return `${Math.max(...values)}`;
}

function resolveVariableExpression(
  source: string,
  identifier: string,
): string | undefined {
  const pattern = new RegExp(
    `^\\s*(?:int\\s+|float\\s+)?${escapeForRegex(identifier)}\\s*=\\s*([^\\r\\n/]+)`,
    "m",
  );
  return source.match(pattern)?.[1]?.trim();
}

function normalizeInputValue(rawValue: string, inputType: string): string {
  const trimmed = rawValue.trim();
  if (inputType === "string") {
    return trimmed.replace(/^["']|["']$/g, "");
  }

  return trimmed;
}

function parseNamedNumber(source: string, key: string, fallback: number): number {
  const pattern = new RegExp(`${key}\\s*=\\s*(-?\\d+(?:\\.\\d+)?)`);
  const match = source.match(pattern);
  if (!match) {
    return fallback;
  }

  const parsed = Number.parseFloat(match[1]);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function parseNamedBoolean(source: string, key: string, fallback: boolean): boolean {
  const pattern = new RegExp(`${key}\\s*=\\s*(true|false)`);
  const match = source.match(pattern);
  if (!match) {
    return fallback;
  }

  return match[1] === "true";
}

function escapeForRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function assignParsedValue(
  config: AfStrategyConfig,
  name: keyof AfStrategyConfig,
  rawValue: string,
): void {
  switch (name) {
    case "sameBarConflictMode":
      config.sameBarConflictMode = parseConflictMode(rawValue);
      return;
    case "trendMode":
      config.trendMode = parseTrendMode(rawValue);
      return;
    case "useReplacement":
    case "applyFilterToB1":
    case "closeAllOnBearConfRiskOff":
    case "allowStrongCounterTrend":
    case "useRealFillSync":
    case "resetOnL3":
    case "useSupertrendFilter":
    case "supertrendBlocksWeakBull":
    case "supertrendRiskOffEnabled":
    case "enableWeakRangeExit":
      (config[name] as boolean) = rawValue === "true";
      return;
    default:
      (config[name] as number) = Number.parseFloat(rawValue);
  }
}

function parseConflictMode(value: string): ConflictMode {
  return value === "SkipBoth" || value === "BearPriority" ? value : "StrongWins";
}

function parseTrendMode(value: string): TrendMode {
  return value === "Strict" || value === "Loose" ? value : "Balanced";
}
