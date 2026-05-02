import { readFile } from "node:fs/promises";

import {
  type CompileFailureClass,
  type ExperimentRecord,
  type LossAnalysisSummary,
  type MutationBrief,
  type ObjectiveConfig,
  type SeedStrategyReference,
} from "../contracts/types.js";
import { buildMutationBrief } from "../mutation/brief.js";
import { normalizeCompileFailureClasses } from "../mutation/compile-failure.js";
import {
  findActiveHeadRecord,
  findBestAcceptedRecord,
  findMutationGuidanceRecord,
} from "../state/accepted-head.js";
import { fileExists } from "../utils/fs.js";
import { selectRelevantResearchContext } from "./research-knowledge.js";
import {
  loadSeedStrategyReference,
  readActiveBaseline,
} from "./seed-strategy.js";

export interface PreparedMutationContext {
  seedStrategy: SeedStrategyReference & { candidateHash: string };
  acceptedRecord: ExperimentRecord | null;
  activeHeadRecord: ExperimentRecord | null;
  acceptedHeadCandidateId: string;
  acceptedHeadScore: number | null;
  improvementSource: "seed" | "accepted_head";
  recentFailures: string[];
  recentCompileErrors: string[];
  recentCompileFailureClasses: CompileFailureClass[];
  guidanceRecord: ExperimentRecord | null;
  recentLossAnalysis: LossAnalysisSummary;
  researchContext: MutationBrief["researchContext"];
  stagnationSignals: string[];
  brief: MutationBrief;
}

function resolveFallbackEvidenceGuidance(
  records: ExperimentRecord[],
): MutationBrief["analysisGuidance"]["fallbackEvidenceGuidance"] {
  const fallbackRecord = [...records]
    .reverse()
    .find((record) => record.fallbackEvaluation != null);
  if (!fallbackRecord?.fallbackEvaluation) {
    return {
      available: false,
      source: null,
      authoritative: false,
      summary:
        "No fallback evidence is currently available. Do not infer authoritative improvement from local-only evidence.",
      suggestedHypothesis:
        "If TradingView verification fails later, use local fallback only to form a narrow hypothesis and re-verify before any promotion decision.",
      forbiddenInterpretation: "do_not_treat_as_verified",
    };
  }

  const fallback = fallbackRecord.fallbackEvaluation;
  const metricSummary =
    fallback.metrics != null
      ? ` Local fallback metrics showed ${fallback.metrics.totalTrades} trades and ${fallback.metrics.postFeeNetProfitPercent.toFixed(2)}% post-fee net profit.`
      : "";
  const decisionSummary = fallback.decisionIfScreeningOnly
    ? ` Screening-only decision was ${fallback.decisionIfScreeningOnly}.`
    : "";

  return {
    available: true,
    source: fallback.executorKind,
    authoritative: false,
    summary:
      `TradingView verification previously failed at ${fallbackRecord.verificationRuntimeFailureKind ?? "unknown_runtime_failure"}; local fallback evidence was recorded as ${fallback.status}.` +
      metricSummary +
      decisionSummary,
    suggestedHypothesis:
      fallback.decisionIfScreeningOnly === "screening_improvement"
        ? "Preserve the localized rule change that improved the local backtest, but treat it only as a hypothesis until TradingView verification succeeds."
        : "Use fallback evidence only to narrow the next mutation scope; do not assume the local result reflects authoritative performance.",
    forbiddenInterpretation: "do_not_treat_as_verified",
  };
}

export function resolveRecentFailures(records: ExperimentRecord[]): string[] {
  return records
    .filter(
      (record) =>
        record.decision !== "screening_improvement" &&
        record.decision !== "verified_improvement" &&
        record.decision !== "promoted_head" &&
        record.decision !== "valid_no_promotion" &&
        !record.decision.startsWith("accepted_"),
    )
    .slice(-5)
    .map((record) => record.decision);
}

export function resolveRecentCompileErrors(records: ExperimentRecord[]): string[] {
  const uniqueErrors: string[] = [];

  for (let index = records.length - 1; index >= 0; index -= 1) {
    const record = records[index];
    if (record?.decision !== "compile_fail") {
      continue;
    }

    for (const error of record.compile?.errors ?? []) {
      const normalized = error.trim();
      if (!normalized || uniqueErrors.includes(normalized)) {
        continue;
      }
      uniqueErrors.push(normalized);
      if (uniqueErrors.length >= 6) {
        return uniqueErrors;
      }
    }
  }

  return uniqueErrors;
}

export function resolveRecentCompileFailureClasses(
  records: ExperimentRecord[],
): CompileFailureClass[] {
  return normalizeCompileFailureClasses(resolveRecentCompileErrors(records));
}

export function resolveStagnationSignals(input: {
  previousRecords: ExperimentRecord[];
  acceptedHeadScore: number | null;
}): string[] {
  const evaluatedRecords = input.previousRecords.filter(
    (record) =>
      record.status === "evaluated" &&
      record.candidateScore !== null &&
      record.candidateScore !== undefined &&
      (record.repairPriorities?.length ?? 0) > 0,
  );
  const recentEvaluated = evaluatedRecords.slice(-5);
  if (recentEvaluated.length < 3) {
    return [];
  }

  const priorBestScore =
    input.acceptedHeadScore ??
    evaluatedRecords
      .slice(0, Math.max(0, evaluatedRecords.length - recentEvaluated.length))
      .reduce<number>(
        (best, record) =>
          Math.max(best, record.candidateScore ?? Number.NEGATIVE_INFINITY),
        Number.NEGATIVE_INFINITY,
      );
  if (priorBestScore === Number.NEGATIVE_INFINITY) {
    return [];
  }

  const summaryByPriority = new Map<
    string,
    { count: number; bestScore: number }
  >();
  for (const record of recentEvaluated) {
    const uniquePriorities = [...new Set(record.repairPriorities ?? [])];
    for (const priority of uniquePriorities) {
      const current = summaryByPriority.get(priority) ?? {
        count: 0,
        bestScore: Number.NEGATIVE_INFINITY,
      };
      current.count += 1;
      current.bestScore = Math.max(
        current.bestScore,
        record.candidateScore ?? Number.NEGATIVE_INFINITY,
      );
      summaryByPriority.set(priority, current);
    }
  }

  return [...summaryByPriority.entries()]
    .filter(
      ([, summary]) =>
        summary.count >= 3 && summary.bestScore <= priorBestScore + 1e-6,
    )
    .sort((left, right) => right[1].count - left[1].count)
    .slice(0, 3)
    .map(
      ([priority, summary]) =>
        `Avoid repeating repair priority "${priority}" again without a materially different rule change; it appeared ${summary.count} times in the last ${recentEvaluated.length} evaluated candidates without score improvement.`,
    );
}

export function createUnavailableLossAnalysisSummary(): LossAnalysisSummary {
  return {
    status: "unavailable_no_trades",
    summary: "No prior loss analysis is available yet.",
    topLossZones: [],
    lossZoneDetails: [],
    tradeLifecycle: [],
    repairPriorities: [],
  };
}

export async function resolveMutationSourcePine(
  workspaceRoot: string,
  acceptedRecord: ExperimentRecord | null,
): Promise<string> {
  const acceptedPath = acceptedRecord?.candidatePath;
  if (acceptedPath && (await fileExists(acceptedPath))) {
    return readFile(acceptedPath, "utf8");
  }
  return readActiveBaseline(workspaceRoot);
}

export async function prepareMutationContext(input: {
  workspaceRoot: string;
  stateRoot?: string;
  objective: ObjectiveConfig;
  previousRecords: ExperimentRecord[];
  acceptedHeadScore?: number | null;
}): Promise<PreparedMutationContext> {
  const seedStrategy = await loadSeedStrategyReference(input.workspaceRoot);
  const acceptedRecord = findBestAcceptedRecord(input.previousRecords);
  const activeHeadRecord = findActiveHeadRecord(
    input.previousRecords,
    acceptedRecord,
  );
  const improvementSource: "seed" | "accepted_head" = acceptedRecord
    ? "accepted_head"
    : "seed";
  const acceptedHeadCandidateId =
    activeHeadRecord?.candidateId ??
    acceptedRecord?.candidateId ??
    seedStrategy.candidateId;
  const acceptedHeadScore =
    input.acceptedHeadScore ?? acceptedRecord?.candidateScore ?? null;
  const recentFailures = resolveRecentFailures(input.previousRecords);
  const recentCompileErrors = resolveRecentCompileErrors(input.previousRecords);
  const recentCompileFailureClasses = resolveRecentCompileFailureClasses(
    input.previousRecords,
  );
  const stagnationSignals = resolveStagnationSignals({
    previousRecords: input.previousRecords,
    acceptedHeadScore,
  });
  const guidanceRecord = findMutationGuidanceRecord(input.previousRecords, {
    acceptedRecord: activeHeadRecord ?? acceptedRecord,
    minimumTotalTrades: input.objective.hardGates.minimumTotalTrades,
  });
  const recentLossAnalysis =
    guidanceRecord?.lossAnalysisSummary ?? createUnavailableLossAnalysisSummary();
  const researchContext = await selectRelevantResearchContext({
    workspaceRoot: input.workspaceRoot,
    stateRoot: input.stateRoot,
    recentFailures,
    lossHotZones: recentLossAnalysis.topLossZones,
    repairPriorities: recentLossAnalysis.repairPriorities,
    objectiveLabel: `${input.objective.symbol} ${input.objective.timeframe}m`,
  });
  const fallbackEvidenceGuidance = resolveFallbackEvidenceGuidance(
    input.previousRecords,
  );
  const brief = buildMutationBrief({
    objective: input.objective,
    seedStrategy,
    acceptedHead:
      (activeHeadRecord?.candidateScore ?? acceptedHeadScore) === null
        ? null
        : {
            candidateId: acceptedHeadCandidateId,
            score: activeHeadRecord?.candidateScore ?? acceptedHeadScore ?? 0,
            summary: activeHeadRecord?.mutationBriefSummary,
            metrics: activeHeadRecord?.testerMetrics,
          },
    recentFailures,
    recentCompileErrors,
    recentCompileFailureClasses,
    recentLossAnalysis,
    researchContext,
    guidanceMetrics: guidanceRecord?.testerMetrics,
    stagnationSignals,
    fallbackEvidenceGuidance,
  });

  return {
    seedStrategy,
    acceptedRecord,
    activeHeadRecord,
    acceptedHeadCandidateId,
    acceptedHeadScore,
    improvementSource,
    recentFailures,
    recentCompileErrors,
    recentCompileFailureClasses,
    guidanceRecord,
    recentLossAnalysis,
    researchContext,
    stagnationSignals,
    brief,
  };
}
