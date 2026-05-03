import path from "node:path";

import {
  type ArtifactValidationResult,
  type ArtifactBundle,
  type FallbackEvaluation,
  type FinalAnalysisSummary,
  type MetricComparison,
  type ObjectiveBreakdown,
  type PineAnalysisSummary,
  type PromotionStatus,
  type RecordEra,
  type SurfaceRecoveryAttempt,
  type SyncArtifact,
  type VerificationRuntimeFailureKind,
  type VerificationFailureReason,
  type VerificationStatus,
} from "../contracts/types.js";
import { ensureDir, writeJson } from "../utils/fs.js";
import { resolveKnowledgePaths } from "../state/knowledge-paths.js";

interface WriteIterationArtifactsInput {
  workspaceRoot: string;
  stateRoot?: string;
  candidateId: string;
  iteration: number;
  syncArtifact?: SyncArtifact;
  artifactBundle?: ArtifactBundle;
  objectiveArtifact?: Record<string, unknown>;
  tradeContextArtifact?: Record<string, unknown>;
  lossAnalysisArtifact?: Record<string, unknown>;
  pineAnalysisArtifact?: Record<string, unknown>;
  fallbackEvaluationArtifact?: Record<string, unknown>;
}

export async function writeIterationArtifacts(
  input: WriteIterationArtifactsInput,
): Promise<Record<string, string>> {
  const stateRoot =
    input.stateRoot ?? path.join(input.workspaceRoot, "state", "pi-autoresearch");
  const knowledgePaths = resolveKnowledgePaths(stateRoot);
  const desktopRunsDir = knowledgePaths.desktopRunsDir;
  const resultsDir = knowledgePaths.resultsDir;
  await ensureDir(desktopRunsDir);
  await ensureDir(resultsDir);

  const suffix = `${String(input.iteration).padStart(2, "0")}-${input.candidateId}`;
  const artifactPaths: Record<string, string> = {};
  if (input.syncArtifact) {
    const syncArtifactPath = path.join(desktopRunsDir, `pi-loop-sync-${suffix}.json`);
    await writeJson(syncArtifactPath, input.syncArtifact);
    artifactPaths.syncArtifact = syncArtifactPath;
  }

  if (input.artifactBundle) {
    const backtestArtifactPath = path.join(
      desktopRunsDir,
      `pi-loop-backtest-${suffix}.json`,
    );
    await writeJson(backtestArtifactPath, input.artifactBundle);
    await writeJson(path.join(resultsDir, "tester-full-backtest.json"), input.artifactBundle);
    artifactPaths.backtestArtifact = backtestArtifactPath;
    artifactPaths.latestBacktestArtifact = path.join(resultsDir, "tester-full-backtest.json");
  }

  if (input.objectiveArtifact) {
    const objectiveArtifactPath = path.join(
      resultsDir,
      `pi-loop-objective-${suffix}.json`,
    );
    const latestObjectiveArtifactPath = path.join(
      resultsDir,
      "tester-pi-objective.json",
    );
    await writeJson(objectiveArtifactPath, input.objectiveArtifact);
    await writeJson(latestObjectiveArtifactPath, input.objectiveArtifact);
    artifactPaths.objectiveArtifact = objectiveArtifactPath;
    artifactPaths.latestObjectiveArtifact = latestObjectiveArtifactPath;
  }

  if (input.tradeContextArtifact) {
    const tradeContextArtifactPath = path.join(
      resultsDir,
      `trade-context-${suffix}.json`,
    );
    await writeJson(tradeContextArtifactPath, input.tradeContextArtifact);
    artifactPaths.tradeContextArtifact = tradeContextArtifactPath;
  }

  if (input.lossAnalysisArtifact) {
    const lossAnalysisArtifactPath = path.join(
      resultsDir,
      `loss-analysis-${suffix}.json`,
    );
    await writeJson(lossAnalysisArtifactPath, input.lossAnalysisArtifact);
    artifactPaths.lossAnalysisArtifact = lossAnalysisArtifactPath;
  }

  if (input.pineAnalysisArtifact) {
    const pineAnalysisArtifactPath = path.join(
      resultsDir,
      `pine-analysis-${suffix}.json`,
    );
    await writeJson(pineAnalysisArtifactPath, input.pineAnalysisArtifact);
    artifactPaths.pineAnalysisArtifact = pineAnalysisArtifactPath;
  }

  if (input.fallbackEvaluationArtifact) {
    const fallbackEvaluationArtifactPath = path.join(
      resultsDir,
      `fallback-evaluation-${suffix}.json`,
    );
    await writeJson(fallbackEvaluationArtifactPath, input.fallbackEvaluationArtifact);
    artifactPaths.fallbackEvidenceArtifact = fallbackEvaluationArtifactPath;
  }

  return artifactPaths;
}

export function buildObjectiveArtifact(input: {
  candidateId: string;
  decision: string;
  objectiveBreakdown: ObjectiveBreakdown;
  strategyMetrics: Record<string, unknown>;
  attachDiagnostics?: Record<string, unknown>;
  artifactValidation?: ArtifactValidationResult;
  verificationStatus?: VerificationStatus;
  verificationFailureReason?: VerificationFailureReason;
  verificationRuntimeFailureKind?: VerificationRuntimeFailureKind;
  recoveryAttempts?: SurfaceRecoveryAttempt[];
  fallbackEvaluation?: FallbackEvaluation | null;
  promotionStatus?: PromotionStatus;
  promotionReady?: boolean;
  screeningVsVerificationDiff?: MetricComparison[] | null;
  recordEra?: RecordEra;
  pineAnalysisSummary?: PineAnalysisSummary;
  finalAnalysisSummary?: FinalAnalysisSummary;
}): Record<string, unknown> {
  return {
    candidateId: input.candidateId,
    decision: input.decision,
    score: input.objectiveBreakdown.score,
    objectiveBreakdown: input.objectiveBreakdown,
    strategyMetrics: input.strategyMetrics,
    attachDiagnostics: input.attachDiagnostics,
    artifactValidation: input.artifactValidation,
    verificationStatus: input.verificationStatus,
    verificationFailureReason: input.verificationFailureReason ?? null,
    verificationRuntimeFailureKind: input.verificationRuntimeFailureKind ?? null,
    recoveryAttempts: input.recoveryAttempts ?? [],
    fallbackEvaluation: input.fallbackEvaluation ?? null,
    promotionStatus: input.promotionStatus,
    promotionReady: input.promotionReady ?? false,
    screeningVsVerificationDiff: input.screeningVsVerificationDiff ?? null,
    recordEra: input.recordEra ?? "v2",
    pineAnalysisSummary: input.pineAnalysisSummary,
    finalAnalysisSummary: input.finalAnalysisSummary,
    generatedAt: new Date().toISOString(),
  };
}
