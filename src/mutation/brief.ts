import {
  type BacktestMetrics,
  type CompileFailureClass,
  type MutationBrief,
  type MutationResearchContext,
  type ObjectiveConfig,
  type RepairMode,
} from "../contracts/types.js";

function buildTradeRetentionTarget(
  metrics: BacktestMetrics | undefined,
  minimumTotalTrades: number,
): number | undefined {
  if (!metrics || metrics.totalTrades < minimumTotalTrades) {
    return undefined;
  }
  return Math.max(minimumTotalTrades, Math.ceil(metrics.totalTrades * 0.7));
}

function dedupeStrings(values: string[], limit?: number): string[] {
  const deduped = values.filter(
    (value, index, items) => value.trim().length > 0 && items.indexOf(value) === index,
  );
  return limit === undefined ? deduped : deduped.slice(0, limit);
}

function isExitProfitRepairZone(zone: string): boolean {
  const normalized = zone.toLowerCase();
  return normalized.includes("weak_exit") || normalized.includes("range_squeeze");
}

function resolveRepairMode(input: {
  minimumTotalTrades: number;
  recentFailures: string[];
  recentLossAnalysis: {
    topLossZones: string[];
  };
  guidanceMetrics?: BacktestMetrics;
}): RepairMode {
  const guidanceTrades = input.guidanceMetrics?.totalTrades;
  if (
    (guidanceTrades !== undefined && guidanceTrades < input.minimumTotalTrades) ||
    input.recentFailures.includes("backtest_empty")
  ) {
    return "entry_recovery";
  }

  const exitRepairZoneCount = input.recentLossAnalysis.topLossZones.filter(
    isExitProfitRepairZone,
  ).length;
  if (
    input.recentLossAnalysis.topLossZones.length > 0 &&
    exitRepairZoneCount * 2 >= input.recentLossAnalysis.topLossZones.length
  ) {
    return "exit_profit_repair";
  }

  return "balanced";
}

function buildCompileFailureConstraint(
  failureClasses: CompileFailureClass[],
): string | null {
  if (failureClasses.length === 0) {
    return null;
  }

  return `Do not reintroduce recent compile-failure classes: ${failureClasses.join(", ")}.`;
}

export function buildMutationBrief(input: {
  objective: ObjectiveConfig;
  seedStrategy: {
    candidateId: string;
    summary: string;
    studyTitle: string | null;
  };
  acceptedHead: {
    candidateId: string;
    score: number;
    summary?: string;
    metrics?: BacktestMetrics;
  } | null;
  recentFailures: string[];
  recentCompileErrors: string[];
  recentCompileFailureClasses?: CompileFailureClass[];
  recentLossAnalysis: {
    status: "available" | "unavailable_no_trades" | "market_context_unavailable";
    summary: string;
    topLossZones: string[];
    repairPriorities: string[];
  };
  researchContext: MutationResearchContext;
  guidanceMetrics?: BacktestMetrics;
  stagnationSignals?: string[];
  fallbackEvidenceGuidance?: MutationBrief["analysisGuidance"]["fallbackEvidenceGuidance"];
}): MutationBrief {
  const recentFailures = input.recentFailures.slice(0, 5);
  const recentCompileErrors = input.recentCompileErrors.slice(0, 6);
  const recentCompileFailureClasses = (
    input.recentCompileFailureClasses ?? []
  ).slice(0, 6);
  const repairPriorities = input.recentLossAnalysis.repairPriorities.slice(0, 5);
  const researchSuggestions = input.researchContext.insights
    .map((insight) => insight.suggestedMutation.trim())
    .filter(Boolean)
    .slice(0, 3);
  const stagnationSignals = dedupeStrings(input.stagnationSignals ?? [], 3);
  const tradeRetentionTarget = buildTradeRetentionTarget(
    input.acceptedHead?.metrics,
    input.objective.hardGates.minimumTotalTrades,
  );
  const acceptedHead = input.acceptedHead
    ? {
        ...input.acceptedHead,
        ...(tradeRetentionTarget ? { tradeRetentionTarget } : {}),
      }
    : null;
  const repairMode = resolveRepairMode({
    minimumTotalTrades: input.objective.hardGates.minimumTotalTrades,
    recentFailures,
    recentLossAnalysis: input.recentLossAnalysis,
    guidanceMetrics: input.guidanceMetrics,
  });
  const actionableLossAnalysis =
    input.recentLossAnalysis.status === "available" &&
    (input.recentLossAnalysis.topLossZones.length > 0 || repairPriorities.length > 0);
  const strongAcceptedHead =
    acceptedHead?.metrics !== undefined &&
    acceptedHead.metrics.postFeeNetProfitPercent >= 20 &&
    acceptedHead.metrics.totalTrades >= input.objective.hardGates.minimumTotalTrades;
  const improvementSource = input.acceptedHead ? "accepted_head" : "seed";

  const scopeControlActions: string[] = [];
  if (strongAcceptedHead) {
    scopeControlActions.push(
      "Use the accepted head as a control and make one localized behavioral change in a single block per mutation unless the brief explicitly requires a coordinated pair.",
      "Prefer parameter, threshold, or single-rule adjustments before introducing new state, regime engines, or multi-part subsystems.",
    );
  }

  const repairModeActions: string[] = [];
  if (repairMode === "entry_recovery") {
    if (tradeRetentionTarget && acceptedHead?.metrics) {
      repairModeActions.push(
        `Preserve parent tradability from ${acceptedHead.metrics.totalTrades} trades and keep at least ${tradeRetentionTarget} closed trades before optimizing other metrics.`,
      );
    }
    repairModeActions.push(
      "Recover tradability by loosening or removing existing entry filters, regime gates, cooldowns, or extension blockers before adding any new logic.",
      "If tradability has collapsed, change entry gating only; defer exit and subsystem rewrites until the trade floor is restored.",
    );
  } else if (repairMode === "exit_profit_repair") {
    if (tradeRetentionTarget) {
      repairModeActions.push(
        `Keep tradability above ${tradeRetentionTarget} closed trades while prioritizing exit and risk repairs over entry expansion.`,
      );
    }
    repairModeActions.push(
      "Mutate staged bearish exit, loser-trimming, risk-off liquidation, replacement, or slot-management thresholds before touching entry gating.",
      "Translate each loss-cluster diagnosis into one concrete exit or risk rule change rather than repeating the same abstract diagnosis.",
    );
  } else {
    repairModeActions.push(
      "Balance one localized entry adjustment with one localized exit or risk adjustment while preserving the AF seed core.",
    );
  }

  const targetedRepairActions: string[] = [];
  if (actionableLossAnalysis && repairMode !== "entry_recovery") {
    targetedRepairActions.push(...repairPriorities);
  } else if (repairMode === "entry_recovery" && repairPriorities.length > 0) {
    targetedRepairActions.push(repairPriorities[0] ?? "");
  }

  const selectedResearchSuggestions =
    strongAcceptedHead && repairMode !== "balanced"
      ? researchSuggestions.slice(0, 1)
      : researchSuggestions;

  const nextMutationActions = dedupeStrings([
    ...scopeControlActions,
    ...repairModeActions,
    ...targetedRepairActions,
    ...selectedResearchSuggestions,
    ...stagnationSignals,
  ]);

  const nextMutationDirection =
    nextMutationActions.length > 0
      ? `Preserve the AF seed core architecture while applying these changes: ${nextMutationActions.join(" ")}`
      : recentFailures.length > 0
      ? `Preserve the AF seed core architecture and avoid repeating recent failure modes: ${recentFailures.join(", ")}`
      : "Preserve the AF seed core architecture while improving post-fee profitability with stable drawdown and sufficient trade count.";

  const forbiddenPatterns = [
    "Do not remove strategy() declaration.",
    "Do not emit empty or placeholder Pine code.",
    "Do not leave TODO, placeholder, or markdown fence text inside pineScript.",
    "Do not use ta.adx(); use Pine v5-safe manual DMI/ADX logic if ADX is required.",
    "Do not optimize for fewer than the minimum required trades.",
    "Do not replace the AF seed with a generic EMA crossover or generic trend-following template.",
    "Preserve the AF seed core: exhaustion count sequencing, confirmation logic, slot-based position scaling or replacement, and staged bearish exit handling unless directly improving one of those blocks.",
  ];

  if (tradeRetentionTarget && acceptedHead?.metrics) {
    forbiddenPatterns.push(
      `Do not produce a mutation that collapses below ${tradeRetentionTarget} trades when the control candidate is already trading ${acceptedHead.metrics.totalTrades} times, unless the brief explicitly accepts that trade-off.`,
    );
  }

  if (repairMode === "entry_recovery") {
    forbiddenPatterns.push(
      "Do not respond to backtest_empty or low tradability by stacking extra entry filters, regime gates, or extension blockers on top of the control candidate.",
      "During entry_recovery, do not add new filters or new subsystems; recover tradability by loosening, removing, or reverting recent restrictions first.",
      "During entry_recovery, do not rewrite exit logic as the primary change until the trade floor is restored.",
    );
  }

  if (repairMode === "exit_profit_repair") {
    forbiddenPatterns.push(
      "During exit_profit_repair, do not use broad entry expansion, blanket gate removal, or new entry families as the main change.",
      "During exit_profit_repair, keep changes inside exit, risk, loser-management, or slot-management blocks unless a tiny entry-side adjustment is explicitly required.",
      "Do not revert to blanket tradability-recovery instructions when guidance trades already satisfy the minimum trade floor.",
    );
  }

  if (actionableLossAnalysis && tradeRetentionTarget && acceptedHead?.metrics) {
    forbiddenPatterns.push(
      "Do not fall back to blanket tradability-recovery instructions when actionable loss analysis is already available; prefer targeted exit and risk repairs first.",
      "Do not repeat the same weak-exit or late-entry diagnosis without changing the specific mutated rule, threshold, or regime scope.",
    );
  }

  if (recentCompileErrors.length > 0) {
    forbiddenPatterns.push(
      `Do not repeat recent compile failures: ${recentCompileErrors.join(" | ")}`,
    );
  }

  const compileFailureConstraint = buildCompileFailureConstraint(
    recentCompileFailureClasses,
  );
  if (compileFailureConstraint) {
    forbiddenPatterns.push(compileFailureConstraint);
  }

  if (strongAcceptedHead) {
    forbiddenPatterns.push(
      "Do not simultaneously rewrite multiple core blocks when the control candidate already passes hard gates with strong profitability.",
      "Do not change entry gating, regime classification, and bearish exit staging all in the same mutation unless the brief explicitly requires that coordinated change.",
      "Preserve control-candidate defaults and parameters outside the targeted repair area.",
      "Do not add new multi-part subsystems such as regime classifiers, setup-tier engines, or per-slot state trackers unless the brief explicitly calls for them.",
    );
  }

  if (stagnationSignals.length > 0) {
    forbiddenPatterns.push(
      "Do not repeat the same diagnosis again without a materially different rule, threshold, regime scope, or targeted block change.",
    );
  }

  return {
    objective: `${input.objective.symbol} ${input.objective.timeframe}m hard-gate-passing strategy improvement`,
    guardrails: {
      minimumTotalTrades: input.objective.hardGates.minimumTotalTrades,
      minimumPostFeeNetProfitPercent:
        input.objective.hardGates.minimumPostFeeNetProfitPercent,
      maximumStrategyDrawdownPercent:
        input.objective.softGuardrails.maximumStrategyDrawdownPercent,
    },
    repairMode,
    seedStrategy: input.seedStrategy,
    acceptedHead,
    improvementSource,
    recentFailures,
    recentCompileErrors,
    recentCompileFailureClasses,
    recentLossAnalysis: input.recentLossAnalysis,
    researchContext: input.researchContext,
    lossHotZones: input.recentLossAnalysis.topLossZones,
    repairPriorities,
    stagnationSignals,
    nextMutationDirection,
    analysisGuidance: {
      hypothesis:
        targetedRepairActions[0] ??
        selectedResearchSuggestions[0] ??
        "A localized Pine mutation should improve the objective without violating trade-count guardrails.",
      expectedEffect:
        repairMode === "entry_recovery"
          ? "Recover closed trades first, then preserve or improve profitability."
          : repairMode === "exit_profit_repair"
            ? "Reduce loss clusters and drawdown while preserving tradability."
            : "Improve score with a targeted change while preserving the AF seed core.",
      invalidIf:
        tradeRetentionTarget && acceptedHead?.metrics
          ? `Invalid if total trades drop below ${tradeRetentionTarget} from the control candidate's ${acceptedHead.metrics.totalTrades} trades.`
          : "Invalid if hard gates fail or tradability collapses.",
      preserveConditions: acceptedHead?.summary ? [acceptedHead.summary] : [],
      weakenConditions:
        repairMode === "entry_recovery"
          ? ["over-restrictive entry filters", "recent added regime gates"]
          : repairMode === "exit_profit_repair"
            ? ["slow weak exits", "late loser liquidation"]
            : [],
      lossZoneGuidance: input.recentLossAnalysis.topLossZones.slice(0, 3),
      fallbackEvidenceGuidance: input.fallbackEvidenceGuidance ?? {
        available: false,
        source: null,
        authoritative: false,
        summary:
          "No local fallback evidence is currently available. Do not assume unverified local evidence.",
        suggestedHypothesis:
          "Treat any future local fallback evidence as a non-authoritative hint only.",
        forbiddenInterpretation: "do_not_treat_as_verified",
      },
    },
    forbiddenPatterns,
  };
}
