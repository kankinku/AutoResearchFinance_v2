import {
  type CriterionDirective,
  type CriterionKey,
  type ExperimentRecord,
  type ObjectiveConfig,
} from "../../contracts/types.js";
import {
  type CalibrationEventRecord,
  type ProblemEventRecord,
} from "../../contracts/autonomous.js";

type CriterionMetricRecord = {
  testerMetrics?: ExperimentRecord["testerMetrics"] | null;
  artifactSummary?: ExperimentRecord["artifactSummary"] | null;
  localTvParity?: ExperimentRecord["localTvParity"] | null;
} & Record<string, unknown>;

export interface CriterionAnalysisInput {
  criterion?: CriterionKey | null;
  experiments: ExperimentRecord[];
  calibrationEvents: CalibrationEventRecord[];
  problemEvents: ProblemEventRecord[];
  objective: ObjectiveConfig;
}

export interface CriterionOutcome {
  criterionBefore: number | null;
  criterionAfter: number | null;
  criterionDelta: number | null;
  criterionVerdict: "improved" | "regressed" | "unchanged" | "not_applicable";
}

export function buildCriterionDirective(
  input: CriterionAnalysisInput,
): CriterionDirective {
  const criterion = input.criterion ?? selectAutoCriterion(input);
  const latestMetric = readCriterionMetric(criterion, latestExperiment(input.experiments));
  const recent = input.experiments.slice(-20);
  const recentProblemText = input.problemEvents
    .slice(-10)
    .map((event) => `${event.problemKind}: ${event.diagnosis}`)
    .join(" | ");
  const parityCounts = countParityStatuses(input.calibrationEvents);
  const common = {
    criterion,
    metricBefore: latestMetric,
  };

  switch (criterion) {
    case "trade_count":
      return {
        ...common,
        metricDirection: "increase",
        branchBias: "exploration_breakout",
        statusSummary: `Latest total trades are ${formatMetric(latestMetric)}; configured minimum is ${input.objective.hardGates.minimumTotalTrades}.`,
        weaknessSummary:
          "Recent candidates are under-delivering trade count or relying on sparse entry windows.",
        successCriteria: `Increase full-sample trades to at least ${input.objective.hardGates.minimumTotalTrades} without breaking OOS post-fee profitability.`,
        repairPriorities: [
          "criterion_trade_count",
          "recover_trade_count",
          "reduce_over_filtering",
          "broaden_primary_entry_window",
        ],
        forbiddenPatterns: [
          "Do not add new filters or confirmations while trade_count is the active criterion.",
          "Do not preserve a sparse 31/7-style trade profile.",
        ],
        nextMutationDirection:
          "Criterion focus is trade_count. Analyze the current sparse entry path, identify the strongest over-filtering weakness, and produce a broader AF-compatible mutation that lifts trade count before optimizing profit.",
      };
    case "entry_frequency":
      return {
        ...common,
        metricDirection: "increase",
        branchBias: "exploration_breakout",
        statusSummary: `Latest entry frequency proxy is ${formatMetric(latestMetric)} trades.`,
        weaknessSummary:
          "Entry conditions are too narrow, cooldown-heavy, or overly confirmation-dependent.",
        successCriteria:
          "Increase opportunity density while preserving the AF local compatibility contract.",
        repairPriorities: [
          "criterion_entry_frequency",
          "remove_secondary_entry_gates",
          "shorten_cooldown",
        ],
        forbiddenPatterns: [
          "Do not introduce a new regime filter as the main entry-frequency repair.",
          "Do not require stacked confirmations after the primary AF event.",
        ],
        nextMutationDirection:
          "Criterion focus is entry_frequency. Diagnose the narrowest entry gate and replace it with one primary AF event trigger plus at most one lightweight exclusion.",
      };
    case "oos_robustness":
      return {
        ...common,
        metricDirection: "increase",
        branchBias: "near_miss_repair",
        statusSummary: `Latest OOS post-fee profit is ${formatMetric(latestMetric)}.`,
        weaknessSummary:
          "Recent candidates lose robustness outside the training segment or fail OOS trade floors.",
        successCriteria:
          "Improve OOS post-fee profitability and positive fold consistency without collapsing trade count.",
        repairPriorities: [
          "criterion_oos_robustness",
          "improve_oos_retention",
          "reduce_fragile_filters",
        ],
        forbiddenPatterns: [
          "Do not solve OOS failure by shrinking trades below the OOS floor.",
          "Do not add multiple new filters that only protect the in-sample window.",
        ],
        nextMutationDirection:
          "Criterion focus is oos_robustness. Identify the weakest OOS failure mode and simplify fragile exit/risk logic while preserving trade count.",
      };
    case "drawdown":
      return {
        ...common,
        metricDirection: "decrease",
        branchBias: "near_miss_repair",
        statusSummary: `Latest max drawdown is ${formatMetric(latestMetric)}%.`,
        weaknessSummary:
          "Risk-off or exit logic is not cutting adverse exposure quickly enough.",
        successCriteria:
          "Lower max drawdown while retaining the configured minimum trade count and positive post-fee profit.",
        repairPriorities: [
          "criterion_drawdown",
          "risk_logic_repair",
          "tighten_adverse_exposure",
        ],
        forbiddenPatterns: [
          "Do not reduce drawdown by preventing most valid entries.",
          "Do not add broad risk-off gates that collapse OOS trade count.",
        ],
        nextMutationDirection:
          "Criterion focus is drawdown. Analyze adverse exposure and repair risk or exit handling without using trade starvation as the drawdown fix.",
      };
    case "profitability":
      return {
        ...common,
        metricDirection: "increase",
        branchBias: "champion_exploit",
        statusSummary: `Latest post-fee net profit is ${formatMetric(latestMetric)}%.`,
        weaknessSummary:
          "The candidate needs stronger post-fee returns after hard gates are respected.",
        successCriteria:
          "Increase post-fee net profit while preserving hard gates, OOS viability, and local compatibility.",
        repairPriorities: [
          "criterion_profitability",
          "exit_profit_repair",
          "preserve_trade_retention",
        ],
        forbiddenPatterns: [
          "Do not optimize profit by reducing trades below the configured floor.",
          "Do not replace AF behavior with a generic trend-following template.",
        ],
        nextMutationDirection:
          "Criterion focus is profitability. Preserve viable entry density and improve loser management, slot turnover, or exits to lift post-fee net profit.",
      };
    case "local_tv_parity":
      return {
        ...common,
        metricDirection: "decrease",
        branchBias: "frontier_exploit",
        statusSummary: `Recent TV parity counts: ${JSON.stringify(parityCounts)}.`,
        weaknessSummary:
          "Local-first behavior is diverging from TradingView calibration or the calibration queue is backlogged.",
        successCriteria:
          "Avoid high-divergence families and prefer local structures with matched or low-drift calibration history.",
        repairPriorities: [
          "criterion_local_tv_parity",
          "avoid_high_divergence_family",
          "prefer_low_divergence_family",
        ],
        forbiddenPatterns: [
          "Do not repeat fingerprint families with recent major_drift parity.",
          "Do not treat local-only evidence as promotion evidence.",
        ],
        nextMutationDirection:
          "Criterion focus is local_tv_parity. Analyze calibration drift and choose a mutation path that avoids high-divergence families while keeping local hard gates intact.",
      };
    case "complexity":
      return {
        ...common,
        metricDirection: "decrease",
        branchBias: "adversarial_simplification",
        statusSummary: `Latest complexity penalty is ${formatMetric(latestMetric)}.`,
        weaknessSummary:
          "Recent candidates carry too many gates, feature flags, or brittle condition stacks.",
        successCriteria:
          "Reduce complexity penalty while preserving minimum trades and OOS viability.",
        repairPriorities: [
          "criterion_complexity",
          "simplify_condition_stack",
          "remove_nonessential_filters",
        ],
        forbiddenPatterns: [
          "Do not add new subsystems while complexity is the active criterion.",
          "Do not preserve multiple redundant filters if one primary trigger is sufficient.",
        ],
        nextMutationDirection:
          "Criterion focus is complexity. Remove or merge the weakest condition stack and keep the strategy AF-compatible with fewer moving parts.",
      };
    case "novelty":
      return {
        ...common,
        metricDirection: "increase",
        branchBias: "exploration_breakout",
        statusSummary: `Latest novelty score is ${formatMetric(latestMetric)}.`,
        weaknessSummary:
          "Recent candidates are too close to archived fingerprint families.",
        successCriteria:
          "Create a materially distinct AF-compatible structure without violating hard gates.",
        repairPriorities: [
          "criterion_novelty",
          "rotate_structure_family",
          "avoid_duplicate_fingerprint_family",
        ],
        forbiddenPatterns: [
          "Do not make a cosmetic threshold-only edit.",
          "Do not repeat recent archive fingerprint families.",
        ],
        nextMutationDirection:
          "Criterion focus is novelty. Identify repeated structure families and generate a materially different AF-compatible route that still clears local hard gates.",
      };
    case "exit_quality":
      return {
        ...common,
        metricDirection: "increase",
        branchBias: "near_miss_repair",
        statusSummary: `Latest average trade percent is ${formatMetric(latestMetric)}.`,
        weaknessSummary:
          recentProblemText || "Exit behavior is likely leaving weak trades open too long or clipping winners too early.",
        successCriteria:
          "Improve average trade quality or post-fee profitability without reducing trade count below the floor.",
        repairPriorities: [
          "criterion_exit_quality",
          "exit_profit_repair",
          "improve_loser_management",
        ],
        forbiddenPatterns: [
          "Do not repair exits by disabling the main entry route.",
          "Do not add broad entry filters as a substitute for exit repair.",
        ],
        nextMutationDirection:
          "Criterion focus is exit_quality. Analyze weak-exit and trade lifecycle evidence, then adjust exit or slot management while preserving entry opportunity density.",
      };
  }
}

export function buildCriterionOutcome(input: {
  directive: CriterionDirective | null | undefined;
  record: CriterionMetricRecord;
}): CriterionOutcome {
  if (!input.directive) {
    return {
      criterionBefore: null,
      criterionAfter: null,
      criterionDelta: null,
      criterionVerdict: "not_applicable",
    };
  }
  const before = input.directive.metricBefore;
  const after = readCriterionMetric(input.directive.criterion, input.record);
  if (before == null || after == null) {
    return {
      criterionBefore: before,
      criterionAfter: after,
      criterionDelta: null,
      criterionVerdict: "not_applicable",
    };
  }
  const delta = after - before;
  const epsilon = 0.000001;
  const improved =
    input.directive.metricDirection === "increase"
      ? delta > epsilon
      : delta < -epsilon;
  const regressed =
    input.directive.metricDirection === "increase"
      ? delta < -epsilon
      : delta > epsilon;
  return {
    criterionBefore: before,
    criterionAfter: after,
    criterionDelta: delta,
    criterionVerdict: improved ? "improved" : regressed ? "regressed" : "unchanged",
  };
}

function selectAutoCriterion(input: CriterionAnalysisInput): CriterionKey {
  const parityCounts = countParityStatuses(input.calibrationEvents);
  const pendingCalibrationCount = input.calibrationEvents.filter(
    (event) => event.eventKind === "calibration_candidate_added" && event.queueState === "queued",
  ).length;
  if (
    pendingCalibrationCount >= 100 ||
    (parityCounts.major_drift ?? 0) > (parityCounts.matched ?? 0)
  ) {
    return "local_tv_parity";
  }

  const recent = input.experiments.slice(-20);
  if (recent.some((record) => hasBlockingReason(record, "low_trade_count"))) {
    return "trade_count";
  }
  if (
    recent.some(
      (record) =>
        hasBlockingReason(record, "oos_trade_count_fail") ||
        hasBlockingReason(record, "robustness_fail"),
    )
  ) {
    return "oos_robustness";
  }
  if (recent.some((record) => hasBlockingReason(record, "drawdown_limit_fail"))) {
    return "drawdown";
  }
  return "trade_count";
}

function latestExperiment(records: ExperimentRecord[]): ExperimentRecord | null {
  return [...records].sort((left, right) => right.iteration - left.iteration)[0] ?? null;
}

function readCriterionMetric(
  criterion: CriterionKey,
  record: CriterionMetricRecord | null,
): number | null {
  if (!record) {
    return null;
  }
  switch (criterion) {
    case "trade_count":
    case "entry_frequency":
      return record.testerMetrics?.totalTrades ?? record.artifactSummary?.tradeCount ?? null;
    case "oos_robustness":
      return (
        readNestedNumber(record, [
          "splitEvaluation",
          "outOfSample",
          "metrics",
          "postFeeNetProfitPercent",
        ]) ??
        readNestedNumber(record, [
          "walkForwardEvaluation",
          "medianOosPostFeeNetProfitPercent",
        ]) ??
        null
      );
    case "drawdown":
      return (
        record.testerMetrics?.maxStrategyDrawdownPercent ??
        record.artifactSummary?.strategy?.maxStrategyDrawdownPercent ??
        null
      );
    case "profitability":
      return (
        record.testerMetrics?.postFeeNetProfitPercent ??
        record.artifactSummary?.strategy?.postFeeNetProfitPercent ??
        null
      );
    case "local_tv_parity":
      return parityPenalty(record.localTvParity?.status);
    case "complexity":
      return readNestedNumber(record, [
        "autoSelectionBreakdown",
        "complexityPenalty",
      ]);
    case "novelty":
      return readNestedNumber(record, ["autoSelectionBreakdown", "noveltyScore"]);
    case "exit_quality":
      return record.testerMetrics?.avgTradePercent ?? null;
  }
}

function readNestedNumber(
  record: Record<string, unknown>,
  keys: string[],
): number | null {
  let current: unknown = record;
  for (const key of keys) {
    if (!current || typeof current !== "object") {
      return null;
    }
    current = (current as Record<string, unknown>)[key];
  }
  return typeof current === "number" && Number.isFinite(current) ? current : null;
}

function parityPenalty(status: string | null | undefined): number | null {
  switch (status) {
    case "matched":
      return 0;
    case "minor_drift":
      return 1;
    case "major_drift":
      return 2;
    case "not_comparable":
      return 3;
    default:
      return status ? 3 : null;
  }
}

function countParityStatuses(
  events: CalibrationEventRecord[],
): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const event of events) {
    const status = event.parity?.status;
    if (!status) {
      continue;
    }
    counts[status] = (counts[status] ?? 0) + 1;
  }
  return counts;
}

function hasBlockingReason(record: ExperimentRecord, kind: string): boolean {
  const reasons = (record as { eligibility?: { blockingReasons?: Array<{ kind?: string }> } })
    .eligibility?.blockingReasons ?? [];
  return reasons.some((reason) => reason.kind === kind);
}

function formatMetric(value: number | null): string {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toFixed(4)
    : "unknown";
}
