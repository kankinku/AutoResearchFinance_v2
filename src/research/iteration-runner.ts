import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";

import { extractStudyTitle } from "../strategy-source/pine-study.js";
import { type PineEvaluationExecutor } from "../automation/common/executor.js";
import { type CliMonitor } from "../cli/monitor.js";
import { loadObjectiveConfig } from "../config/objective.js";
import {
  type ApplyResult,
  type ArtifactBundle,
  type ArtifactValidationResult,
  type BacktestMetrics,
  type CandidateArtifact,
  type ChartTarget,
  type CompileResult,
  type ConditionContribution,
  type DecisionCode,
  type EvaluationExecutorName,
  type ExecutorCapability,
  type ExperimentRecord,
  type FallbackEvaluation,
  type FinalAnalysisSummary,
  type LossAnalysisSummary,
  type MetricComparison,
  type MutationProvenance,
  type MutationParseStatus,
  type MutationBrief,
  type ObjectiveBreakdown,
  type ParsedMutationResponse,
  type PineAnalysisSummary,
  type PromotionStatus,
  type RecordEra,
  type SurfaceRecoveryAttempt,
  type SyncArtifact,
  type VerificationFailureReason,
  type VerificationRuntimeFailureKind,
  type VerificationStatus,
} from "../contracts/types.js";
import {
  isArtifactPromotionReady,
  validateArtifactBundle,
} from "../evaluation/artifact-validation.js";
import { computeConditionContributions } from "../evaluation/condition-contribution.js";
import {
  classifyAuthoritativeDecision,
  classifyScreeningDecision,
  derivePromotionReadiness,
  derivePromotionStatus,
  deriveVerificationFailureReason,
  deriveVerificationStatus,
} from "../evaluation/decision.js";
import { evaluateObjective } from "../evaluation/objective.js";
import { persistCandidateArtifact } from "../mutation/candidate-store.js";
import { type MutationLlmClient } from "../mutation/llm-client.js";
import { parseMutationResponseStrict } from "../mutation/parser.js";
import {
  AUTORESEARCH_CONTRACT_VERSION,
  STRATEGY_SPEC_MUTATION_AUTHORITY,
} from "../policy/autoresearch-contract.js";
import {
  formatPreflightIssuesForRepair,
  inspectGeneratedMutation,
  type PineGenerationIssue,
} from "../mutation/preflight.js";
import { writeMutationRuntimeArtifact } from "../mutation/runtime-artifact.js";
import { rebuildIndexes } from "../state/index-builder.js";
import {
  appendCandidateLedgerRecord,
  appendExperimentRecord,
  appendIncidentRecord,
  appendMutationBriefRecord,
  readExperimentRecords,
} from "../state/jsonl-store.js";
import { buildObjectiveArtifact, writeIterationArtifacts } from "./artifact-writer.js";
import {
  createMarketContextUnavailableLossAnalysis,
  createNoTradesLossAnalysis,
  summarizeLossZones,
} from "./loss-analysis.js";
import { loadMarketContext } from "./market-context.js";
import {
  prepareMutationContext,
  resolveMutationSourcePine,
} from "./mutation-context.js";
import {
  analyzePineMutation,
  synthesizeFinalAnalysis,
} from "./pine-analysis.js";
import { ensureActiveSeedBaseline } from "./seed-strategy.js";
import { enrichTradesWithMarketContext } from "./trade-context.js";
import {
  attemptLocalRuntimeRecovery,
  buildFallbackEvidenceFromScreening,
  classifyLocalRuntimeFailure,
  collectLocalFallbackEvidence,
} from "./verification-fallback.js";
import { initializeWorkspace } from "./workspace.js";
import { createCandidateId, sha256 } from "../utils/fs.js";

const STUDY_DECLARATION_EXPRESSION =
  /\b(strategy|indicator)\s*\(\s*(['"`])([^'"`]+)\2/;

interface RunSingleIterationInput {
  workspaceRoot: string;
  stateRoot?: string;
  llmClient: MutationLlmClient;
  executor: PineEvaluationExecutor;
  executorName?: EvaluationExecutorName;
  promotionVerificationExecutorFactory?: () => PineEvaluationExecutor;
  promotionVerificationExecutorName?: EvaluationExecutorName | "none";
  acceptedHeadScore?: number | null;
  runId?: string;
  chartType?: string;
  maxTrades?: number;
  maxCompileRepairAttempts?: number;
  monitor?: CliMonitor;
  fallbackLocalOnRuntimeFailure?: boolean;
  localFallbackExecutorFactory?: () => PineEvaluationExecutor;
  consumeFallbackSlot?: () => boolean;
}

interface IterationRunResult {
  decision: DecisionCode;
  experiment: ExperimentRecord;
  conditionContributions: ConditionContribution[];
  hypothesis: {
    objective: string;
    nextMutationDirection: string;
    recentFailures: string[];
    acceptedHeadCandidateId: string | null;
  };
}

function resolveStateRoot(workspaceRoot: string): string {
  return path.join(
    workspaceRoot,
    "state",
    "targets",
    "qqq-120m-af",
    "pi-autoresearch",
  );
}

function isBacktestEmpty(
  bundle: ArtifactBundle,
  validation?: ArtifactValidationResult,
): boolean {
  return (
    !bundle.strategy ||
    ((validation?.hasTotalTrades ?? true) && bundle.strategy.totalTrades <= 0)
  );
}

function mergeHints(...hintSets: Array<string[] | undefined>): string[] {
  return hintSets
    .flatMap((hints) => hints ?? [])
    .filter((hint, index, array) => array.indexOf(hint) === index);
}

function shouldComputeConditionContributions(input: {
  decision: DecisionCode;
  candidateScore: number;
  hardGatesPassed: boolean;
  acceptedHeadScore: number | null;
}): boolean {
  if (
    input.decision === "screening_improvement" ||
    input.decision === "verified_improvement" ||
    input.decision === "valid_no_promotion" ||
    input.decision === "promoted_head"
  ) {
    return true;
  }

  if (input.hardGatesPassed) {
    return true;
  }

  if (input.acceptedHeadScore === null) {
    return false;
  }

  return input.candidateScore >= input.acceptedHeadScore * 0.85;
}

async function logMonitor(
  monitor: CliMonitor | undefined,
  event: string,
  message: string,
  details?: Record<string, unknown>,
): Promise<void> {
  await monitor?.log(event, message, details);
}

function summarizeHypothesis(
  brief: MutationBrief,
  recentFailures: string[],
): string {
  const failureHint =
    recentFailures.length > 0 ? ` avoiding ${recentFailures.join(", ")}` : "";
  return `${brief.objective}${failureHint}`;
}

function resolveRuntimeTargetPath(workspaceRoot: string): string {
  return path.join(
    workspaceRoot,
    "strategies",
    "source",
    "runtime_target.pine",
  );
}

function enforceStudyTitle(source: string, studyTitle: string | null): string {
  if (!studyTitle) {
    return source;
  }

  return source.replace(
    STUDY_DECLARATION_EXPRESSION,
    (_match, kind: string, quote: string) => `${kind}(${quote}${studyTitle}${quote}`,
  );
}

function shouldVerifyPromotedCandidate(input: {
  decision: DecisionCode;
  executorName?: EvaluationExecutorName;
  verificationExecutorName?: EvaluationExecutorName | "none";
}): boolean {
  if (input.decision !== "screening_improvement") {
    return false;
  }
  if (!input.verificationExecutorName || input.verificationExecutorName === "none") {
    return false;
  }
  return input.executorName !== input.verificationExecutorName;
}

function hashArtifactBundle(bundle: ArtifactBundle | undefined): string | null {
  return bundle ? sha256(JSON.stringify(bundle)) : null;
}

function buildExperimentV2Fields(input: {
  mutationParseStatus: MutationParseStatus;
  mutationProvenance?: MutationProvenance | null;
  executorCapability: ExecutorCapability;
  artifactValidation?: ArtifactValidationResult;
  verificationStatus: VerificationStatus;
  verificationFailureReason?: VerificationFailureReason;
  verificationRuntimeFailureKind?: VerificationRuntimeFailureKind;
  recoveryAttempts?: SurfaceRecoveryAttempt[];
  fallbackEvaluation?: FallbackEvaluation | null;
  promotionStatus: PromotionStatus;
  promotionReady?: boolean;
  screeningVsVerificationDiff?: MetricComparison[] | null;
  recordEra?: RecordEra;
  candidateHash?: string | null;
  baselineHash?: string | null;
  artifactBundle?: ArtifactBundle;
}): Pick<
  ExperimentRecord,
  | "mutationParseStatus"
  | "mutationProvenance"
  | "executorCapability"
  | "artifactValidation"
  | "verificationStatus"
  | "verificationFailureReason"
  | "verificationRuntimeFailureKind"
  | "recoveryAttempts"
  | "fallbackEvaluation"
  | "promotionStatus"
  | "promotionReady"
  | "screeningVsVerificationDiff"
  | "recordEra"
  | "recordMeta"
> {
  return {
    mutationParseStatus: input.mutationParseStatus,
    mutationProvenance: input.mutationProvenance ?? null,
    executorCapability: input.executorCapability,
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
    recordMeta: {
      schemaVersion: "experiment/v2",
      recordHash: "pending",
      candidateHash: input.candidateHash ?? null,
      baselineHash: input.baselineHash ?? null,
      artifactBundleHash: hashArtifactBundle(input.artifactBundle),
      pipelineVersion: "af-research-pipeline/v2",
    },
  };
}

function buildMutationPromptHash(operation: string, payload: unknown): string {
  return sha256(JSON.stringify({ operation, payload }));
}

function buildMutationProvenance(input: {
  briefHash: string | null;
  promptHash: string | null;
  responseHash: string | null;
  responseSchemaVersion: string | null;
  parseStatus: MutationParseStatus;
  inventorySource: ParsedMutationResponse["inventorySource"] | null;
  inferredFields: string[];
  missingFields: string[];
}): MutationProvenance {
  return {
    briefHash: input.briefHash,
    promptHash: input.promptHash,
    responseHash: input.responseHash,
    responseSchemaVersion: input.responseSchemaVersion,
    parseStatus: input.parseStatus,
    inventorySource: input.inventorySource,
    inferredFields: input.inferredFields,
    missingFields: input.missingFields,
  };
}

function buildScreeningVsVerificationDiff(
  screeningMetrics: BacktestMetrics | undefined,
  verificationMetrics: BacktestMetrics | undefined,
): MetricComparison[] | null {
  if (!screeningMetrics && !verificationMetrics) {
    return null;
  }

  const metricKeys: Array<keyof BacktestMetrics> = [
    "netProfitPercent",
    "postFeeNetProfitPercent",
    "profitFactor",
    "maxStrategyDrawdownPercent",
    "percentProfitable",
    "totalTrades",
    "avgTradePercent",
  ];

  return metricKeys.map((metric) => ({
    metric,
    screening: screeningMetrics?.[metric] ?? null,
    verification: verificationMetrics?.[metric] ?? null,
  }));
}

function buildBaseExperiment(input: {
  runId: string;
  iteration: number;
  artifact: CandidateArtifact;
  acceptedHeadCandidateId: string;
  baselineCandidateId: string;
  seedStrategyId: string;
  improvementSource: "seed" | "accepted_head";
  parsedMutation: ParsedMutationResponse;
  researchContext: MutationBrief["researchContext"];
  runtimeTargetPath: string;
}): Omit<
  ExperimentRecord,
  | "candidateScore"
  | "decision"
  | "status"
  | "compile"
  | "apply"
  | "syncArtifact"
  | "testerMetrics"
  | "artifactBundle"
  | "objectiveBreakdown"
  | "conditionContributions"
  | "recordedAt"
> {
  return {
    runId: input.runId,
    iteration: input.iteration,
    candidateId: input.artifact.candidateId,
    parentCandidateId: input.artifact.parentId,
    branchId: input.artifact.branchId,
    acceptedHeadCandidateId: input.acceptedHeadCandidateId,
    baselineCandidateId: input.baselineCandidateId,
    seedStrategyId: input.seedStrategyId,
    improvementSource: input.improvementSource,
    candidatePath: input.artifact.pinePath,
    candidateHash: input.artifact.pineHash,
    studyTitle: input.artifact.studyTitle,
    conditionInventory: input.artifact.inventory,
    mutationBriefSummary: input.parsedMutation.candidateSummary,
    researchContextSummary: input.researchContext,
    nextMutationHints: input.parsedMutation.nextMutationHints,
    artifactPaths: {
      candidate: input.artifact.pinePath,
      runtimeTarget: input.runtimeTargetPath,
    },
  };
}

async function materializeIterationCandidate(input: {
  workspaceRoot: string;
  stateRoot: string;
  runId: string;
  iteration: number;
  parsedMutation: ParsedMutationResponse;
  parentCandidateId: string | null;
  monitor?: CliMonitor;
  persistEvent: string;
  persistMessage: string;
  runtimeEvent: string;
  runtimeMessage: string;
}): Promise<{
  artifact: CandidateArtifact;
  candidateSource: string;
  runtimeTargetPath: string;
}> {
  const artifact = await persistCandidateArtifact({
    workspaceRoot: input.workspaceRoot,
    parsedMutation: input.parsedMutation,
    parentCandidateId: input.parentCandidateId,
    branchId: "main",
  });
  await logMonitor(input.monitor, input.persistEvent, input.persistMessage, {
    candidateId: artifact.candidateId,
    candidatePath: artifact.pinePath,
    parentCandidateId: artifact.parentId,
    studyTitle: artifact.studyTitle,
  });
  await appendCandidateLedgerRecord(input.stateRoot, {
    runId: input.runId,
    iteration: input.iteration,
    candidateId: artifact.candidateId,
    parentCandidateId: artifact.parentId,
    branchId: artifact.branchId,
    studyTitle: artifact.studyTitle,
    candidatePath: artifact.pinePath,
    candidateHash: artifact.pineHash,
    contractVersion: AUTORESEARCH_CONTRACT_VERSION,
    mutationAuthority: artifact.specHash
      ? STRATEGY_SPEC_MUTATION_AUTHORITY
      : null,
    specPath: artifact.specPath ?? null,
    specHash: artifact.specHash ?? null,
    candidateSummary: artifact.candidateSummary,
    nextMutationHints: artifact.nextMutationHints,
  });

  const candidateSource = await readFile(artifact.pinePath, "utf8");
  const runtimeTargetPath = resolveRuntimeTargetPath(input.workspaceRoot);
  await writeFile(runtimeTargetPath, candidateSource, "utf8");
  await logMonitor(input.monitor, input.runtimeEvent, input.runtimeMessage, {
    runtimeTargetPath,
    studyTitle: artifact.studyTitle,
  });

  return {
    artifact,
    candidateSource,
    runtimeTargetPath,
  };
}

async function recordMutationGenerationFailure(input: {
  workspaceRoot: string;
  stateRoot: string;
  runId: string;
  iteration: number;
  acceptedHeadCandidateId: string;
  baselineCandidateId: string;
  seedStrategyId: string;
  improvementSource: "seed" | "accepted_head";
  brief: MutationBrief;
  monitor?: CliMonitor;
  decision: DecisionCode;
  mutationParseStatus: MutationParseStatus;
  executorCapability: ExecutorCapability;
  baselineHash?: string | null;
  incidentType: string;
  detail: string;
  rawResponse?: string;
  issues?: PineGenerationIssue[];
  mutationProvenance?: MutationProvenance | null;
}): Promise<ExperimentRecord> {
  const failureCandidateId = createCandidateId("genfail");
  const failureArtifactPath = await writeMutationRuntimeArtifact({
    workspaceRoot: input.workspaceRoot,
    stateRoot: input.stateRoot,
    iteration: input.iteration,
    stage: input.incidentType,
    payload: {
      acceptedHeadCandidateId: input.acceptedHeadCandidateId,
      detail: input.detail,
      rawResponse: input.rawResponse ?? null,
      issues: input.issues ?? [],
      brief: input.brief,
    },
  });
  const experiment = await appendExperimentRecord(input.stateRoot, {
    runId: input.runId,
    iteration: input.iteration,
    candidateId: failureCandidateId,
    parentCandidateId: input.acceptedHeadCandidateId,
    branchId: "main",
    acceptedHeadCandidateId: input.acceptedHeadCandidateId,
    baselineCandidateId: input.baselineCandidateId,
    seedStrategyId: input.seedStrategyId,
    improvementSource: input.improvementSource,
    candidateScore: null,
    decision: input.decision,
    status: "mutation_failed",
    mutationBriefSummary: input.detail,
    nextMutationHints: [],
    artifactPaths: {
      mutationFailureArtifact: failureArtifactPath,
    },
    researchContextSummary: input.brief.researchContext,
    ...buildExperimentV2Fields({
      mutationParseStatus: input.mutationParseStatus,
      mutationProvenance: input.mutationProvenance ?? null,
      executorCapability: input.executorCapability,
      verificationStatus: "not_requested",
      promotionStatus: "not_promoted",
      candidateHash: null,
      baselineHash: input.baselineHash ?? null,
    }),
  });
  await appendIncidentRecord(input.stateRoot, {
    runId: input.runId,
    iteration: input.iteration,
    candidateId: failureCandidateId,
    incidentType: input.incidentType,
    detail: `${input.detail} | artifact=${failureArtifactPath}`,
  });
  await rebuildIndexes(input.stateRoot);
  await logMonitor(
    input.monitor,
    "mutation.generation_failed",
    "Mutation generation failure recorded",
    {
      candidateId: failureCandidateId,
      incidentType: input.incidentType,
      artifactPath: failureArtifactPath,
    },
  );
  return experiment;
}

export async function runSingleIteration(
  input: RunSingleIterationInput,
): Promise<IterationRunResult> {
  let verificationExecutor: PineEvaluationExecutor | null = null;

  try {
    const stateRoot = input.stateRoot ?? resolveStateRoot(input.workspaceRoot);
    await initializeWorkspace({
      workspaceRoot: input.workspaceRoot,
      stateRoot,
    });
    await ensureActiveSeedBaseline(input.workspaceRoot);

    const objective = await loadObjectiveConfig(input.workspaceRoot);
    const previousRecords = await readExperimentRecords(stateRoot);
    const iteration = previousRecords.length + 1;
    const runId = input.runId ?? `run-${Date.now()}`;
    const primaryExecutorCapability = input.executor.getCapability();
    const mutationContext = await prepareMutationContext({
      workspaceRoot: input.workspaceRoot,
      stateRoot,
      objective,
      previousRecords,
      acceptedHeadScore: input.acceptedHeadScore,
    });
    const {
      seedStrategy,
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
      brief,
    } = mutationContext;
    const briefHash = sha256(JSON.stringify(brief));
    const mutationSourcePine = await resolveMutationSourcePine(
      input.workspaceRoot,
      activeHeadRecord,
    );
    await logMonitor(input.monitor, "iteration.start", "Starting iteration", {
      iteration,
      acceptedHeadCandidateId,
      acceptedHeadScore,
      improvementSource,
    });
    await logMonitor(input.monitor, "hypothesis.ready", "Hypothesis prepared", {
      hypothesis: summarizeHypothesis(brief, recentFailures),
      nextMutationDirection: brief.nextMutationDirection,
    });
    await logMonitor(input.monitor, "mutation.brief", "Mutation brief ready", {
      recentFailures,
      guidanceCandidateId: guidanceRecord?.candidateId ?? null,
      guidanceCandidateScore: guidanceRecord?.candidateScore ?? null,
      guidanceCandidateTrades: guidanceRecord?.testerMetrics?.totalTrades ?? null,
      recentCompileErrors,
      recentCompileFailureClasses,
      recentLossSummary: recentLossAnalysis.summary,
      lossHotZones: recentLossAnalysis.topLossZones,
      researchSummary: researchContext.summary,
      researchInsightCount: researchContext.insights.length,
      forbiddenPatterns: brief.forbiddenPatterns,
    });
    await appendMutationBriefRecord(stateRoot, {
      runId,
      iteration,
      acceptedHeadCandidateId,
      briefHash: null,
      promptHash: null,
      responseHash: null,
      brief,
    });

    const hypothesis = {
      objective: brief.objective,
      nextMutationDirection: brief.nextMutationDirection,
      recentFailures,
      acceptedHeadCandidateId,
    };

    const buildExecutorStageArtifact = async (payload: {
      stage: string;
      executorName?: EvaluationExecutorName | "none";
      decision: DecisionCode;
      compile?: CompileResult;
      apply?: ApplyResult;
      testerMetrics?: BacktestMetrics | null;
      objectiveBreakdown?: ObjectiveBreakdown | null;
      artifactBundle?: ArtifactBundle;
    }): Promise<string> =>
      writeMutationRuntimeArtifact({
        workspaceRoot: input.workspaceRoot,
        stateRoot,
        iteration,
        stage: payload.stage,
        payload: {
          executor: payload.executorName ?? null,
          decision: payload.decision,
          compile: payload.compile ?? null,
          apply: payload.apply ?? null,
          testerMetrics: payload.testerMetrics ?? null,
          objectiveBreakdown: payload.objectiveBreakdown ?? null,
          tradeCount: payload.artifactBundle?.trades.length ?? 0,
          equityPoints: payload.artifactBundle?.equity.pointCount ?? 0,
          attachDiagnostics:
            payload.artifactBundle?.attachDiagnostics ??
            payload.apply?.attachDiagnostics ??
            null,
        },
      });

    let llmResponse: string;
    let currentPromptHash = buildMutationPromptHash("generateMutation", {
      brief,
      baselinePine: mutationSourcePine,
    });
    let currentResponseHash: string | null = null;
    let currentResponseSchemaVersion: string | null = null;
    let currentInventorySource: ParsedMutationResponse["inventorySource"] | null = null;
    let currentInferredFields: string[] = [];
    let currentMissingFields: string[] = [];
    const currentMutationProvenance = (
      parseStatus: MutationParseStatus,
    ): MutationProvenance =>
      buildMutationProvenance({
        briefHash,
        promptHash: currentPromptHash,
        responseHash: currentResponseHash,
        responseSchemaVersion: currentResponseSchemaVersion,
        parseStatus,
        inventorySource: currentInventorySource,
        inferredFields: currentInferredFields,
        missingFields: currentMissingFields,
      });
    try {
      await logMonitor(input.monitor, "mutation.request", "Requesting mutation from LLM", {
        iteration,
        acceptedHeadCandidateId,
        repairMode: brief.repairMode,
        improvementSource,
      });
      llmResponse = await input.llmClient.generateMutation({
        brief,
        baselinePine: mutationSourcePine,
      });
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      const experiment = await recordMutationGenerationFailure({
        workspaceRoot: input.workspaceRoot,
        stateRoot,
        runId,
        iteration,
        acceptedHeadCandidateId,
        baselineCandidateId: seedStrategy.candidateId,
        seedStrategyId: seedStrategy.candidateId,
        improvementSource,
        brief,
        monitor: input.monitor,
        decision: "mutation_generation_fail",
        mutationParseStatus: "invalid",
        executorCapability: primaryExecutorCapability,
        baselineHash: seedStrategy.candidateHash,
        incidentType: "mutation_request_failed",
        detail,
        mutationProvenance: currentMutationProvenance("invalid"),
      });
      return {
        decision: "mutation_generation_fail",
        experiment,
        conditionContributions: [],
        hypothesis,
      };
    }
    await logMonitor(input.monitor, "mutation.response", "Received mutation response", {
      responseLength: llmResponse.length,
    });
    currentResponseHash = sha256(llmResponse);
    currentResponseSchemaVersion = "parsed-mutation-response/v1";

    let currentMutation: ParsedMutationResponse;
    let currentMutationParseStatus: MutationParseStatus = "valid";
    try {
      currentMutation = parseMutationResponseStrict(llmResponse);
      currentInventorySource = currentMutation.inventorySource;
      currentInferredFields = currentMutation.inferredFields;
      currentMissingFields = currentMutation.missingFields;
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      const experiment = await recordMutationGenerationFailure({
        workspaceRoot: input.workspaceRoot,
        stateRoot,
        runId,
        iteration,
        acceptedHeadCandidateId,
        baselineCandidateId: seedStrategy.candidateId,
        seedStrategyId: seedStrategy.candidateId,
        improvementSource,
        brief,
        monitor: input.monitor,
        decision: "mutation_schema_fail",
        mutationParseStatus: "invalid",
        executorCapability: primaryExecutorCapability,
        baselineHash: seedStrategy.candidateHash,
        incidentType: "mutation_parse_failed",
        detail,
        rawResponse: llmResponse,
        mutationProvenance: currentMutationProvenance("invalid"),
      });
      return {
        decision: "mutation_schema_fail",
        experiment,
        conditionContributions: [],
        hypothesis,
      };
    }
    await logMonitor(input.monitor, "mutation.parsed", "Parsed mutation response", {
      candidateSummary: currentMutation.candidateSummary,
      conditionCount: currentMutation.inventory.length,
    });

    let preflight = inspectGeneratedMutation(currentMutation, {
      recentCompileErrors,
      recentCompileFailureClasses,
    });
    await logMonitor(input.monitor, "mutation.preflight", "Mutation preflight completed", {
      issueCount: preflight.issues.length,
      blockingIssueCount: preflight.blockingIssues.length,
      warningIssueCount: preflight.warningIssues.length,
      issueCodes: preflight.issues.map((issue) => issue.code),
    });

    if (preflight.blockingIssues.length > 0) {
      const preflightArtifactPath = await writeMutationRuntimeArtifact({
        workspaceRoot: input.workspaceRoot,
        stateRoot,
        iteration,
        stage: "mutation-preflight-blocked",
        payload: {
          acceptedHeadCandidateId,
          issues: preflight.blockingIssues,
          candidateSummary: currentMutation.candidateSummary,
          pineScript: currentMutation.pineScript,
        },
      });
      await appendIncidentRecord(stateRoot, {
        runId,
        iteration,
        candidateId: createCandidateId("preflight"),
        incidentType: "mutation_preflight_blocked",
        detail: `Blocking Pine generation issues detected | artifact=${preflightArtifactPath}`,
      });
      await logMonitor(
        input.monitor,
        "mutation.preflight_blocked",
        "Blocking mutation preflight issues detected",
        {
          issueCodes: preflight.blockingIssues.map((issue) => issue.code),
          artifactPath: preflightArtifactPath,
        },
      );

      try {
        const repairedResponse = await input.llmClient.repairMutation({
          brief,
          candidatePine: currentMutation.pineScript,
          compileErrors: formatPreflightIssuesForRepair(preflight.blockingIssues),
          candidateSummary: currentMutation.candidateSummary,
          inventory: currentMutation.inventory,
        });
        currentPromptHash = buildMutationPromptHash("repairMutation", {
          brief,
          candidatePine: currentMutation.pineScript,
          compileErrors: formatPreflightIssuesForRepair(preflight.blockingIssues),
          candidateSummary: currentMutation.candidateSummary,
          inventory: currentMutation.inventory,
        });
        await logMonitor(
          input.monitor,
          "mutation.preflight_repair",
          "Attempting preflight repair",
          {
            blockingIssueCount: preflight.blockingIssues.length,
            responseLength: repairedResponse.length,
          },
        );
        llmResponse = repairedResponse;
        currentResponseHash = sha256(repairedResponse);
        currentResponseSchemaVersion = "parsed-mutation-response/v1";
        currentMutation = parseMutationResponseStrict(repairedResponse);
        currentInventorySource = currentMutation.inventorySource;
        currentInferredFields = currentMutation.inferredFields;
        currentMissingFields = currentMutation.missingFields;
        preflight = inspectGeneratedMutation(currentMutation, {
          recentCompileErrors,
          recentCompileFailureClasses,
        });
        await logMonitor(
          input.monitor,
          "mutation.preflight",
          "Mutation preflight completed",
          {
            issueCount: preflight.issues.length,
            blockingIssueCount: preflight.blockingIssues.length,
            warningIssueCount: preflight.warningIssues.length,
            issueCodes: preflight.issues.map((issue) => issue.code),
            repaired: true,
          },
        );
      } catch (error) {
        const detail = error instanceof Error ? error.message : String(error);
        const experiment = await recordMutationGenerationFailure({
          workspaceRoot: input.workspaceRoot,
          stateRoot,
          runId,
          iteration,
          acceptedHeadCandidateId,
          baselineCandidateId: seedStrategy.candidateId,
          seedStrategyId: seedStrategy.candidateId,
          improvementSource,
          brief,
          monitor: input.monitor,
          decision: "preflight_fail",
          mutationParseStatus: "invalid",
          executorCapability: primaryExecutorCapability,
          baselineHash: seedStrategy.candidateHash,
          incidentType: "mutation_preflight_repair_failed",
          detail,
          rawResponse: llmResponse,
          issues: preflight.blockingIssues,
          mutationProvenance: currentMutationProvenance("invalid"),
        });
        return {
          decision: "preflight_fail",
          experiment,
          conditionContributions: [],
          hypothesis,
        };
      }
    }

    if (preflight.blockingIssues.length > 0) {
      const experiment = await recordMutationGenerationFailure({
        workspaceRoot: input.workspaceRoot,
        stateRoot,
        runId,
        iteration,
        acceptedHeadCandidateId,
        baselineCandidateId: seedStrategy.candidateId,
        seedStrategyId: seedStrategy.candidateId,
        improvementSource,
        brief,
        monitor: input.monitor,
        decision: "preflight_fail",
        mutationParseStatus: "invalid",
        executorCapability: primaryExecutorCapability,
        baselineHash: seedStrategy.candidateHash,
        incidentType: "mutation_preflight_failed",
        detail: "Blocking Pine generation issues remained after preflight repair.",
        rawResponse: llmResponse,
        issues: preflight.blockingIssues,
        mutationProvenance: currentMutationProvenance("invalid"),
      });
      return {
        decision: "preflight_fail",
        experiment,
        conditionContributions: [],
        hypothesis,
      };
    }
    let currentPineAnalysis = analyzePineMutation({
      baselineSource: mutationSourcePine,
      candidateSource: currentMutation.pineScript,
      candidateSummary: currentMutation.candidateSummary,
      inventory: currentMutation.inventory,
      brief,
      issues: preflight.issues,
    });

    const chartTarget: ChartTarget = {
      symbol: objective.symbol,
      timeframe: objective.timeframe,
      chartType: input.chartType ?? "candles",
    };
    const compatibility =
      (await input.executor.assessCompatibility?.({
        source: currentMutation.pineScript,
        chartTarget,
      })) ?? {
        supported: true,
        reasonCode: null,
        detail: null,
      };
    if (!compatibility.supported) {
      const detail =
        compatibility.detail ??
        "Candidate is outside the supported executor compatibility envelope.";
      const decision = compatibility.reasonCode ?? "unsupported_strategy_family";
      const experiment = await recordMutationGenerationFailure({
        workspaceRoot: input.workspaceRoot,
        stateRoot,
        runId,
        iteration,
        acceptedHeadCandidateId,
        baselineCandidateId: seedStrategy.candidateId,
        seedStrategyId: seedStrategy.candidateId,
        improvementSource,
        brief,
        monitor: input.monitor,
        decision,
        mutationParseStatus: "valid",
        executorCapability: primaryExecutorCapability,
        baselineHash: seedStrategy.candidateHash,
        incidentType: decision,
        detail,
        rawResponse: llmResponse,
        issues: preflight.issues,
      });
      return {
        decision,
        experiment,
        conditionContributions: [],
        hypothesis,
      };
    }

    let currentCandidate = await materializeIterationCandidate({
      workspaceRoot: input.workspaceRoot,
      stateRoot,
      runId,
      iteration,
      parsedMutation: currentMutation,
      parentCandidateId: acceptedHeadCandidateId,
      monitor: input.monitor,
      persistEvent: "candidate.persisted",
      persistMessage: "Candidate artifact persisted",
      runtimeEvent: "runtime.updated",
      runtimeMessage: "Runtime target updated",
    });
    let currentBaseExperiment = buildBaseExperiment({
      runId,
      iteration,
      artifact: currentCandidate.artifact,
      acceptedHeadCandidateId,
      baselineCandidateId: seedStrategy.candidateId,
      seedStrategyId: seedStrategy.candidateId,
      improvementSource,
      parsedMutation: currentMutation,
      researchContext,
      runtimeTargetPath: currentCandidate.runtimeTargetPath,
    });
    await input.executor.prepareChart(chartTarget);
    await logMonitor(input.monitor, "executor.chart_ready", "Evaluation surface prepared", {
      symbol: objective.symbol,
      timeframe: objective.timeframe,
      chartType: chartTarget.chartType,
    });
    await input.executor.updateStrategySource(currentCandidate.candidateSource);
    await logMonitor(input.monitor, "executor.source_updated", "Pine source pushed", {
      candidateId: currentCandidate.artifact.candidateId,
      studyTitle: currentCandidate.artifact.studyTitle,
    });

    let compile = await input.executor.compileStrategy();
    await logMonitor(input.monitor, "executor.compile", "Compile finished", {
      ok: compile.ok,
      errors: compile.errors,
    });
    let syncArtifact: SyncArtifact =
      (await input.executor.buildSyncArtifact?.({
        chartTarget,
        compile,
      })) ?? {
        chartTarget,
        compile,
        stateAfter: {},
      };

    let lastCompileFailureExperiment: ExperimentRecord | null = null;
    if (!compile.ok) {
      const maxCompileRepairAttempts = input.maxCompileRepairAttempts ?? 2;
      for (let attempt = 0; !compile.ok; attempt += 1) {
        const compileFailureAnalysis = synthesizeFinalAnalysis({
          decision: "compile_fail",
          pineAnalysis: currentPineAnalysis,
        });
        const artifactPaths = await writeIterationArtifacts({
          workspaceRoot: input.workspaceRoot,
          stateRoot,
          candidateId: currentCandidate.artifact.candidateId,
          iteration,
          syncArtifact,
          pineAnalysisArtifact: currentPineAnalysis,
        });
        lastCompileFailureExperiment = await appendExperimentRecord(stateRoot, {
          ...currentBaseExperiment,
          candidateScore: null,
          decision: "compile_fail",
          status: "compile_failed",
          compile,
          syncArtifact,
          pineAnalysisSummary: currentPineAnalysis,
          finalAnalysisSummary: compileFailureAnalysis,
          artifactPaths: {
            ...(currentBaseExperiment.artifactPaths ?? {}),
            ...artifactPaths,
          },
          ...buildExperimentV2Fields({
            mutationParseStatus: currentMutationParseStatus,
            mutationProvenance: currentMutationProvenance(currentMutationParseStatus),
            executorCapability: primaryExecutorCapability,
            verificationStatus: "not_requested",
            promotionStatus: "not_promoted",
            candidateHash: currentCandidate.artifact.pineHash,
            baselineHash: seedStrategy.candidateHash,
          }),
        });
        await logMonitor(input.monitor, "state.recorded", "Compile failure recorded", {
          candidateId: currentCandidate.artifact.candidateId,
          decision: "compile_fail",
          repairAttempt: attempt,
        });

        if (attempt >= maxCompileRepairAttempts) {
          break;
        }

        try {
          await logMonitor(input.monitor, "repair.compile.start", "Starting compile repair", {
            attempt: attempt + 1,
            candidateId: currentCandidate.artifact.candidateId,
            errors: compile.errors,
          });
          const repairResponse = await input.llmClient.repairMutation({
            brief,
            candidatePine: currentCandidate.candidateSource,
            compileErrors: compile.errors,
            candidateSummary: currentMutation.candidateSummary,
            inventory: currentCandidate.artifact.inventory,
          });
          currentPromptHash = buildMutationPromptHash("repairMutation", {
            brief,
            candidatePine: currentCandidate.candidateSource,
            compileErrors: compile.errors,
            candidateSummary: currentMutation.candidateSummary,
            inventory: currentCandidate.artifact.inventory,
          });
          await logMonitor(
            input.monitor,
            "repair.compile.response",
            "Received compile repair response",
            {
              attempt: attempt + 1,
              responseLength: repairResponse.length,
            },
          );
          currentResponseHash = sha256(repairResponse);
          currentResponseSchemaVersion = "parsed-mutation-response/v1";
          currentMutation = parseMutationResponseStrict(repairResponse);
          currentInventorySource = currentMutation.inventorySource;
          currentInferredFields = currentMutation.inferredFields;
          currentMissingFields = currentMutation.missingFields;
          currentPineAnalysis = analyzePineMutation({
            baselineSource: mutationSourcePine,
            candidateSource: currentMutation.pineScript,
            candidateSummary: currentMutation.candidateSummary,
            inventory: currentMutation.inventory,
            brief,
          });
          await logMonitor(
            input.monitor,
            "repair.compile.parsed",
            "Parsed compile repair response",
            {
              attempt: attempt + 1,
              candidateSummary: currentMutation.candidateSummary,
              conditionCount: currentMutation.inventory.length,
            },
          );
          currentCandidate = await materializeIterationCandidate({
            workspaceRoot: input.workspaceRoot,
            stateRoot,
            runId,
            iteration,
            parsedMutation: currentMutation,
            parentCandidateId: currentCandidate.artifact.candidateId,
            monitor: input.monitor,
            persistEvent: "repair.persisted",
            persistMessage: "Repair candidate artifact persisted",
            runtimeEvent: "runtime.updated",
            runtimeMessage: "Runtime target updated",
          });
          currentBaseExperiment = buildBaseExperiment({
            runId,
            iteration,
            artifact: currentCandidate.artifact,
            acceptedHeadCandidateId,
            baselineCandidateId: seedStrategy.candidateId,
            seedStrategyId: seedStrategy.candidateId,
            improvementSource,
            parsedMutation: currentMutation,
            researchContext,
            runtimeTargetPath: currentCandidate.runtimeTargetPath,
          });
          await input.executor.updateStrategySource(currentCandidate.candidateSource);
          await logMonitor(
            input.monitor,
            "repair.compile.applied",
            "Repaired Pine source pushed",
            {
              attempt: attempt + 1,
              candidateId: currentCandidate.artifact.candidateId,
              studyTitle: currentCandidate.artifact.studyTitle,
            },
          );
          compile = await input.executor.compileStrategy();
          syncArtifact =
            (await input.executor.buildSyncArtifact?.({
              chartTarget,
              compile,
            })) ?? {
              chartTarget,
              compile,
              stateAfter: {},
            };
          await logMonitor(
            input.monitor,
            "repair.compile",
            "Compile finished after repair",
            {
              attempt: attempt + 1,
              ok: compile.ok,
              errors: compile.errors,
            },
          );
        } catch (error) {
          const detail = error instanceof Error ? error.message : String(error);
          await appendIncidentRecord(stateRoot, {
            runId,
            iteration,
            candidateId: currentCandidate.artifact.candidateId,
            incidentType: "compile_repair_failed",
            detail,
          });
          await logMonitor(
            input.monitor,
            "repair.compile.failed",
            "Compile repair attempt failed",
            {
              attempt: attempt + 1,
              candidateId: currentCandidate.artifact.candidateId,
              error: detail,
            },
          );
          break;
        }
      }

      if (!compile.ok) {
        await rebuildIndexes(stateRoot);
        return {
          decision: "compile_fail",
          experiment:
            lastCompileFailureExperiment ??
            (await appendExperimentRecord(stateRoot, {
              ...currentBaseExperiment,
              candidateScore: null,
              decision: "compile_fail",
              status: "compile_failed",
              compile,
              syncArtifact,
              pineAnalysisSummary: currentPineAnalysis,
              finalAnalysisSummary: synthesizeFinalAnalysis({
                decision: "compile_fail",
                pineAnalysis: currentPineAnalysis,
              }),
              ...buildExperimentV2Fields({
                mutationParseStatus: currentMutationParseStatus,
                mutationProvenance: currentMutationProvenance(currentMutationParseStatus),
                executorCapability: primaryExecutorCapability,
                verificationStatus: "not_requested",
                promotionStatus: "not_promoted",
                candidateHash: currentCandidate.artifact.pineHash,
                baselineHash: seedStrategy.candidateHash,
              }),
            })),
          conditionContributions: [],
          hypothesis,
        };
      }
    }

    const apply = await input.executor.applyStrategy({
      expectedStudyTitle: currentCandidate.artifact.studyTitle,
    });
    await logMonitor(input.monitor, "executor.apply", "Apply finished", {
      ok: apply.ok,
      message: apply.message,
      expectedStudyTitle: currentCandidate.artifact.studyTitle,
      detectedStudyTitle: apply.attachDiagnostics?.detectedStudyTitle ?? null,
    });
    const appliedSyncArtifact: SyncArtifact =
      (await input.executor.buildSyncArtifact?.({
        chartTarget,
        compile,
        apply,
      })) ?? {
        chartTarget,
        compile,
        apply,
        attachDiagnostics: apply.attachDiagnostics,
        stateAfter: {},
      };
    if (!apply.ok) {
      const finalAnalysisSummary = synthesizeFinalAnalysis({
        decision: "apply_fail",
        pineAnalysis: currentPineAnalysis,
      });
      const artifactPaths = await writeIterationArtifacts({
        workspaceRoot: input.workspaceRoot,
        stateRoot,
        candidateId: currentCandidate.artifact.candidateId,
        iteration,
        syncArtifact: appliedSyncArtifact,
        pineAnalysisArtifact: currentPineAnalysis,
      });
      const experiment = await appendExperimentRecord(stateRoot, {
        ...currentBaseExperiment,
        candidateScore: null,
        decision: "apply_fail",
        status: "apply_failed",
        compile,
        apply,
        syncArtifact: appliedSyncArtifact,
        pineAnalysisSummary: currentPineAnalysis,
        finalAnalysisSummary,
        artifactPaths: {
          ...(currentBaseExperiment.artifactPaths ?? {}),
          ...artifactPaths,
        },
        ...buildExperimentV2Fields({
          mutationParseStatus: currentMutationParseStatus,
          mutationProvenance: currentMutationProvenance(currentMutationParseStatus),
          executorCapability: primaryExecutorCapability,
          verificationStatus: "not_requested",
          promotionStatus: "not_promoted",
          candidateHash: currentCandidate.artifact.pineHash,
          baselineHash: seedStrategy.candidateHash,
        }),
      });
      if (apply.attachDiagnostics?.staleStudySuspected) {
        await appendIncidentRecord(stateRoot, {
          runId: experiment.runId,
          iteration: experiment.iteration,
          candidateId: experiment.candidateId,
          incidentType: "stale_attach_detected",
          detail: `Expected ${currentCandidate.artifact.studyTitle} but detected ${apply.attachDiagnostics.detectedStudyTitle}.`,
        });
      }
      await rebuildIndexes(stateRoot);
      await logMonitor(input.monitor, "state.recorded", "Apply failure recorded", {
        candidateId: currentCandidate.artifact.candidateId,
        decision: "apply_fail",
      });
      return {
        decision: "apply_fail",
        experiment,
        conditionContributions: [],
        hypothesis,
      };
    }

    const primaryArtifactBundle = await input.executor.readArtifactBundle({
      expectedStudyTitle: currentCandidate.artifact.studyTitle,
      maxTrades: input.maxTrades,
    });
    const primaryTesterMetrics = primaryArtifactBundle.strategy;
    await logMonitor(input.monitor, "executor.metrics", "Backtest metrics captured", {
      totalTrades: primaryTesterMetrics?.totalTrades ?? 0,
      netProfitPercent: primaryTesterMetrics?.netProfitPercent ?? 0,
      postFeeNetProfitPercent:
        primaryTesterMetrics?.postFeeNetProfitPercent ?? 0,
      tradesCollected: primaryArtifactBundle.trades.length,
      equityPoints: primaryArtifactBundle.equity.pointCount,
    });
    const primaryArtifactValidation = validateArtifactBundle({
      artifactBundle: primaryArtifactBundle,
      executorCapability: primaryExecutorCapability,
    });
    let finalDecision: DecisionCode = "backtest_empty";
    let finalCompile: CompileResult = compile;
    let finalApply: ApplyResult | undefined = apply;
    let finalSyncArtifact: SyncArtifact = appliedSyncArtifact;
    let finalArtifactBundle: ArtifactBundle | undefined = primaryArtifactBundle;
    let finalTesterMetrics: BacktestMetrics | undefined = primaryTesterMetrics ?? undefined;
    let finalObjectiveBreakdown: ObjectiveBreakdown | undefined;
    let finalArtifactValidation: ArtifactValidationResult | undefined =
      primaryArtifactValidation;
    let finalExecutorCapability: ExecutorCapability = primaryExecutorCapability;
    let finalVerificationStatus: VerificationStatus = "not_requested";
    let finalVerificationFailureReason: VerificationFailureReason = null;
    let finalVerificationRuntimeFailureKind: VerificationRuntimeFailureKind = null;
    let finalRecoveryAttempts: SurfaceRecoveryAttempt[] = [];
    let finalFallbackEvaluation: FallbackEvaluation | null = null;
    let finalPromotionStatus: PromotionStatus = "not_promoted";
    let finalPromotionReady = false;
    let finalScreeningVsVerificationDiff: MetricComparison[] | null = null;
    let contributionExecutor: PineEvaluationExecutor = input.executor;
    let screeningObjectiveBreakdown: ObjectiveBreakdown | undefined;
    let screeningArtifactPath: string | undefined;
    let verificationArtifactPath: string | undefined;
    let fallbackEvaluationArtifact:
      | Record<string, unknown>
      | undefined;
    let usedVerificationExecutor = false;
    let screeningDecision: DecisionCode | null = null;
    const executorArtifactPaths: Record<string, string> = {};

    if (
      !primaryTesterMetrics ||
      isBacktestEmpty(primaryArtifactBundle, primaryArtifactValidation)
    ) {
      finalDecision = "backtest_empty";
      await logMonitor(input.monitor, "evaluation.finalized", "Evaluation finalized", {
        decision: finalDecision,
        executor: input.executorName ?? null,
        reason: "screening_backtest_empty",
      });
    } else {
      screeningObjectiveBreakdown = evaluateObjective(
        primaryTesterMetrics,
        objective,
      );
      screeningDecision = classifyScreeningDecision(
        screeningObjectiveBreakdown,
        acceptedHeadScore,
      );
      finalDecision = screeningDecision;
      finalObjectiveBreakdown = screeningObjectiveBreakdown;

      await logMonitor(input.monitor, "evaluation.screening", "Primary screening evaluated", {
        decision: screeningDecision,
        score: screeningObjectiveBreakdown.score,
        hardGatesPassed: screeningObjectiveBreakdown.hardGatesPassed,
        softGuardrailBreached: screeningObjectiveBreakdown.softGuardrailBreached,
        executor: input.executorName ?? null,
      });

      const shouldVerifyPromotion =
        input.promotionVerificationExecutorFactory != null &&
        shouldVerifyPromotedCandidate({
          decision: screeningDecision,
          executorName: input.executorName,
          verificationExecutorName: input.promotionVerificationExecutorName,
        });

      if (primaryExecutorCapability.authoritative && !shouldVerifyPromotion) {
        finalDecision = classifyAuthoritativeDecision({
          breakdown: screeningObjectiveBreakdown,
          acceptedHeadScore,
          artifactValidation: primaryArtifactValidation,
        });
        finalVerificationStatus = deriveVerificationStatus({
          decision: finalDecision,
          executorCapability: primaryExecutorCapability,
          usedVerificationExecutor: false,
        });
        finalVerificationFailureReason = deriveVerificationFailureReason({
          decision: finalDecision,
          screeningDecision,
          artifactValidation: primaryArtifactValidation,
          hadRuntimeFailure: finalDecision === "compile_fail" || finalDecision === "apply_fail",
          wasBacktestEmpty: finalDecision === "backtest_empty",
          usedVerificationExecutor: false,
        });
        finalPromotionStatus = derivePromotionStatus({
          decision: finalDecision,
          executorCapability: primaryExecutorCapability,
        });
        finalPromotionReady = derivePromotionReadiness({
          decision: finalDecision,
          artifactValidation: primaryArtifactValidation,
          executorCapability: primaryExecutorCapability,
          verificationStatus: finalVerificationStatus,
          fallbackEvaluation: finalFallbackEvaluation,
          mutationProvenance: currentMutationProvenance(currentMutationParseStatus),
        });
      }

      if (shouldVerifyPromotion) {
        usedVerificationExecutor = true;
        finalVerificationStatus = "verification_pending";
        screeningArtifactPath = await buildExecutorStageArtifact({
          stage: "primary-screening",
          executorName: input.executorName,
          decision: screeningDecision,
          compile,
          apply,
          testerMetrics: primaryTesterMetrics,
          objectiveBreakdown: screeningObjectiveBreakdown,
          artifactBundle: primaryArtifactBundle,
        });
        executorArtifactPaths.primaryScreeningArtifact = screeningArtifactPath;

        const resetToScreeningState = () => {
          finalCompile = compile;
          finalApply = apply;
          finalSyncArtifact = appliedSyncArtifact;
          finalArtifactBundle = primaryArtifactBundle;
          finalTesterMetrics = primaryTesterMetrics ?? undefined;
          finalObjectiveBreakdown = screeningObjectiveBreakdown;
          finalArtifactValidation = primaryArtifactValidation;
          finalExecutorCapability = primaryExecutorCapability;
          finalScreeningVsVerificationDiff = null;
        };

        const runPromotionVerificationAttempt = async () => {
          if (!verificationExecutor) {
            throw new Error("Promotion verification executor is not available.");
          }
          const verificationExecutorCapability = verificationExecutor.getCapability();
          finalExecutorCapability = verificationExecutorCapability;
          contributionExecutor = verificationExecutor;

          await verificationExecutor.prepareChart(chartTarget);
          await logMonitor(
            input.monitor,
            "verification.chart_ready",
            "Promotion verification surface prepared",
            {
              symbol: objective.symbol,
              timeframe: objective.timeframe,
              chartType: chartTarget.chartType,
              executor: input.promotionVerificationExecutorName ?? null,
            },
          );
          await verificationExecutor.updateStrategySource(currentCandidate.candidateSource);
          await logMonitor(
            input.monitor,
            "verification.source_updated",
            "Promotion verification source pushed",
            {
              candidateId: currentCandidate.artifact.candidateId,
              studyTitle: currentCandidate.artifact.studyTitle,
              executor: input.promotionVerificationExecutorName ?? null,
            },
          );

          const verificationCompile = await verificationExecutor.compileStrategy();
          await logMonitor(
            input.monitor,
            "verification.compile",
            "Promotion verification compile finished",
            {
              ok: verificationCompile.ok,
              errors: verificationCompile.errors,
              executor: input.promotionVerificationExecutorName ?? null,
            },
          );
          let verificationApply: ApplyResult | undefined;
          let verificationArtifactBundle: ArtifactBundle | undefined;
          let verificationTesterMetrics: BacktestMetrics | undefined;
          let verificationObjectiveBreakdown: ObjectiveBreakdown | undefined;
          let verificationArtifactValidation: ArtifactValidationResult | undefined;
          let verificationSyncArtifact: SyncArtifact =
            (await verificationExecutor.buildSyncArtifact?.({
              chartTarget,
              compile: verificationCompile,
            })) ?? {
              chartTarget,
              compile: verificationCompile,
              stateAfter: {},
            };

          finalCompile = verificationCompile;
          finalApply = undefined;
          finalSyncArtifact = verificationSyncArtifact;
          finalArtifactBundle = undefined;
          finalTesterMetrics = undefined;
          finalObjectiveBreakdown = undefined;
          finalArtifactValidation = undefined;
          finalDecision = "verification_fail";

          if (verificationCompile.ok) {
            verificationApply = await verificationExecutor.applyStrategy({
              expectedStudyTitle: currentCandidate.artifact.studyTitle,
            });
            await logMonitor(
              input.monitor,
              "verification.apply",
              "Promotion verification apply finished",
              {
                ok: verificationApply.ok,
                message: verificationApply.message,
                expectedStudyTitle: currentCandidate.artifact.studyTitle,
                detectedStudyTitle:
                  verificationApply.attachDiagnostics?.detectedStudyTitle ?? null,
                executor: input.promotionVerificationExecutorName ?? null,
              },
            );
            verificationSyncArtifact =
              (await verificationExecutor.buildSyncArtifact?.({
                chartTarget,
                compile: verificationCompile,
                apply: verificationApply,
              })) ?? {
                chartTarget,
                compile: verificationCompile,
                apply: verificationApply,
                attachDiagnostics: verificationApply.attachDiagnostics,
                stateAfter: {},
              };
            finalApply = verificationApply;
            finalSyncArtifact = verificationSyncArtifact;
            finalDecision = "verification_fail";
            if (verificationApply.ok) {
              verificationArtifactBundle = await verificationExecutor.readArtifactBundle({
                expectedStudyTitle: currentCandidate.artifact.studyTitle,
                maxTrades: input.maxTrades,
              });
              verificationTesterMetrics =
                verificationArtifactBundle.strategy ?? undefined;
              verificationArtifactValidation = validateArtifactBundle({
                artifactBundle: verificationArtifactBundle,
                executorCapability: verificationExecutorCapability,
              });
              await logMonitor(
                input.monitor,
                "verification.metrics",
                "Promotion verification metrics captured",
                {
                  totalTrades: verificationTesterMetrics?.totalTrades ?? 0,
                  netProfitPercent:
                    verificationTesterMetrics?.netProfitPercent ?? 0,
                  postFeeNetProfitPercent:
                    verificationTesterMetrics?.postFeeNetProfitPercent ?? 0,
                  tradesCollected: verificationArtifactBundle.trades.length,
                  equityPoints: verificationArtifactBundle.equity.pointCount,
                  executor: input.promotionVerificationExecutorName ?? null,
                },
              );
              finalArtifactBundle = verificationArtifactBundle;
              finalTesterMetrics = verificationTesterMetrics;
              finalArtifactValidation = verificationArtifactValidation;
              finalScreeningVsVerificationDiff = buildScreeningVsVerificationDiff(
                primaryTesterMetrics ?? undefined,
                verificationTesterMetrics,
              );

              if (
                verificationTesterMetrics &&
                !isBacktestEmpty(
                  verificationArtifactBundle,
                  verificationArtifactValidation,
                )
              ) {
                verificationObjectiveBreakdown = evaluateObjective(
                  verificationTesterMetrics,
                  objective,
                );
                finalObjectiveBreakdown = verificationObjectiveBreakdown;
                const authoritativeDecision = classifyAuthoritativeDecision({
                  breakdown: verificationObjectiveBreakdown,
                  acceptedHeadScore,
                  artifactValidation:
                    verificationArtifactValidation ?? primaryArtifactValidation,
                });
                finalDecision = authoritativeDecision;
              } else if (
                verificationArtifactValidation &&
                !verificationArtifactValidation.hasMetrics
              ) {
                finalDecision = "artifact_incomplete";
              }
            }
          }

          finalVerificationStatus = deriveVerificationStatus({
            decision: finalDecision,
            executorCapability: verificationExecutorCapability,
            usedVerificationExecutor: true,
          });
          finalVerificationFailureReason = deriveVerificationFailureReason({
            decision: finalDecision,
            screeningDecision,
            artifactValidation: finalArtifactValidation,
            hadRuntimeFailure: false,
            wasBacktestEmpty:
              finalArtifactBundle != null &&
              isBacktestEmpty(finalArtifactBundle, finalArtifactValidation),
            usedVerificationExecutor: true,
          });
          finalPromotionStatus = derivePromotionStatus({
            decision: finalDecision,
            executorCapability: verificationExecutorCapability,
          });
          finalPromotionReady = derivePromotionReadiness({
            decision: finalDecision,
            artifactValidation: finalArtifactValidation,
            executorCapability: verificationExecutorCapability,
            verificationStatus: finalVerificationStatus,
            fallbackEvaluation: finalFallbackEvaluation,
            mutationProvenance: currentMutationProvenance(currentMutationParseStatus),
          });
        };

        const finalizeRuntimeFailure = async (
          failureKind: VerificationRuntimeFailureKind,
        ) => {
          resetToScreeningState();
          finalDecision = "verification_fail";
          finalVerificationStatus = "verification_failed";
          finalVerificationFailureReason = "verification_runtime_failure";
          finalVerificationRuntimeFailureKind = failureKind;
          finalPromotionStatus = "verification_failed";
          finalPromotionReady = false;
          finalFallbackEvaluation = null;
          fallbackEvaluationArtifact = undefined;

          const allowFallback =
            input.fallbackLocalOnRuntimeFailure ?? true;
          const canReusePrimaryScreening =
            (primaryExecutorCapability.kind === "local-af-screening" ||
              primaryExecutorCapability.kind === "local-af-backtest") &&
            primaryTesterMetrics != null &&
            screeningObjectiveBreakdown != null;
          if (allowFallback && canReusePrimaryScreening) {
            const fallbackResult = buildFallbackEvidenceFromScreening({
              candidateId: currentCandidate.artifact.candidateId,
              chartTarget,
              authoritativeFailureKind: failureKind,
              recoveryAttempts: finalRecoveryAttempts,
              metrics: primaryTesterMetrics ?? null,
              objectiveBreakdown: screeningObjectiveBreakdown ?? null,
              artifactValidation: primaryArtifactValidation,
              decisionIfScreeningOnly: screeningDecision,
              artifactBundle: primaryArtifactBundle,
            });
            finalFallbackEvaluation = fallbackResult.fallbackEvaluation;
            fallbackEvaluationArtifact = fallbackResult.artifactPayload;
          } else if (
            allowFallback &&
            input.localFallbackExecutorFactory &&
            (input.consumeFallbackSlot?.() ?? true)
          ) {
            const fallbackResult = await collectLocalFallbackEvidence({
              candidateId: currentCandidate.artifact.candidateId,
              pineSource: currentCandidate.candidateSource,
              chartTarget,
              objective,
              acceptedHeadScore,
              maxTrades: input.maxTrades,
              authoritativeFailureKind: failureKind,
              recoveryAttempts: finalRecoveryAttempts,
              executorFactory: input.localFallbackExecutorFactory,
              monitor: input.monitor,
            });
            finalFallbackEvaluation = fallbackResult.fallbackEvaluation;
            fallbackEvaluationArtifact = fallbackResult.artifactPayload;
          } else if (allowFallback) {
            await logMonitor(
              input.monitor,
              "verification.fallback_skipped",
              "Local fallback evidence skipped because the task batch budget is exhausted or no factory was provided",
              {
                candidateId: currentCandidate.artifact.candidateId,
                failureKind,
              },
            );
          }

          verificationArtifactPath = await buildExecutorStageArtifact({
            stage: "promotion-verification",
            executorName: input.promotionVerificationExecutorName,
            decision: finalDecision,
            compile: finalCompile,
            apply: finalApply,
            testerMetrics: finalTesterMetrics ?? null,
            objectiveBreakdown: finalObjectiveBreakdown ?? null,
            artifactBundle: finalArtifactBundle,
          });
          executorArtifactPaths.promotionVerificationArtifact =
            verificationArtifactPath;
          await logMonitor(
            input.monitor,
            "evaluation.finalized",
            "Promotion verification finalized after authoritative runtime failure",
            {
              decision: finalDecision,
              score: finalObjectiveBreakdown?.score ?? null,
              executor: input.promotionVerificationExecutorName ?? null,
              verificationRuntimeFailureKind: failureKind,
              fallbackCollected: finalFallbackEvaluation != null,
            },
          );
        };

        verificationExecutor = input.promotionVerificationExecutorFactory!();
        contributionExecutor = verificationExecutor;
        try {
          await runPromotionVerificationAttempt();
        } catch (error) {
          const runtimeFailureKind = classifyLocalRuntimeFailure(error, {
            assumeLocalRuntime: true,
          });
          if (!runtimeFailureKind) {
            throw error;
          }
          await logMonitor(
            input.monitor,
            "verification.runtime_failure",
            "Authoritative promotion verification hit a runtime failure",
            {
              candidateId: currentCandidate.artifact.candidateId,
              failureKind: runtimeFailureKind,
              detail: error instanceof Error ? error.message : String(error),
            },
          );
          const recoveryAttempt = await attemptLocalRuntimeRecovery({
            executorFactory: input.promotionVerificationExecutorFactory!,
            chartTarget,
            failureKind: runtimeFailureKind,
            attempt: 1,
            monitor: input.monitor,
          });
          finalRecoveryAttempts = [recoveryAttempt.recoveryAttempt];
          if (recoveryAttempt.recovered && recoveryAttempt.executor) {
            await verificationExecutor?.close?.();
            verificationExecutor = recoveryAttempt.executor;
            contributionExecutor = verificationExecutor;
            try {
              await runPromotionVerificationAttempt();
            } catch (retryError) {
              const retryFailureKind = classifyLocalRuntimeFailure(retryError, {
                assumeLocalRuntime: true,
              });
              await finalizeRuntimeFailure(
                retryFailureKind ?? runtimeFailureKind ?? "unknown_runtime_failure",
              );
            }
          } else {
            await finalizeRuntimeFailure(runtimeFailureKind);
          }
        }

        if (finalDecision !== "verification_fail" || finalVerificationRuntimeFailureKind == null) {
          verificationArtifactPath = await buildExecutorStageArtifact({
            stage: "promotion-verification",
            executorName: input.promotionVerificationExecutorName,
            decision: finalDecision,
            compile: finalCompile,
            apply: finalApply,
            testerMetrics: finalTesterMetrics ?? null,
            objectiveBreakdown: finalObjectiveBreakdown ?? null,
            artifactBundle: finalArtifactBundle,
          });
          executorArtifactPaths.promotionVerificationArtifact =
            verificationArtifactPath;
          await logMonitor(
            input.monitor,
            "evaluation.finalized",
            "Promotion verification finalized evaluation",
            {
              decision: finalDecision,
              score: finalObjectiveBreakdown?.score ?? null,
              executor: input.promotionVerificationExecutorName ?? null,
            },
          );
        }
      } else {
        finalPromotionStatus = derivePromotionStatus({
          decision: finalDecision,
          executorCapability: primaryExecutorCapability,
        });
        finalPromotionReady = derivePromotionReadiness({
          decision: finalDecision,
          artifactValidation: finalArtifactValidation,
          executorCapability: primaryExecutorCapability,
          verificationStatus: finalVerificationStatus,
          fallbackEvaluation: finalFallbackEvaluation,
          mutationProvenance: currentMutationProvenance(currentMutationParseStatus),
        });
        await logMonitor(input.monitor, "evaluation.objective", "Objective evaluated", {
          decision: finalDecision,
          score: finalObjectiveBreakdown.score,
          hardGatesPassed: finalObjectiveBreakdown.hardGatesPassed,
          softGuardrailBreached: finalObjectiveBreakdown.softGuardrailBreached,
          executor: input.executorName ?? null,
        });
      }
    }

    if (finalDecision === "compile_fail") {
      const finalAnalysisSummary = synthesizeFinalAnalysis({
        decision: "compile_fail",
        pineAnalysis: currentPineAnalysis,
      });
      const artifactPaths = await writeIterationArtifacts({
        workspaceRoot: input.workspaceRoot,
        stateRoot,
        candidateId: currentCandidate.artifact.candidateId,
        iteration,
        syncArtifact: finalSyncArtifact,
        pineAnalysisArtifact: currentPineAnalysis,
      });
      const experiment = await appendExperimentRecord(stateRoot, {
        ...currentBaseExperiment,
        candidateScore: null,
        decision: "compile_fail",
        status: "compile_failed",
        compile: finalCompile,
        syncArtifact: finalSyncArtifact,
        pineAnalysisSummary: currentPineAnalysis,
        finalAnalysisSummary,
        artifactPaths: {
          ...(currentBaseExperiment.artifactPaths ?? {}),
          ...artifactPaths,
          ...executorArtifactPaths,
        },
        ...buildExperimentV2Fields({
          mutationParseStatus: currentMutationParseStatus,
          mutationProvenance: currentMutationProvenance(currentMutationParseStatus),
          executorCapability: finalExecutorCapability,
          artifactValidation: finalArtifactValidation,
          verificationStatus: finalVerificationStatus,
          verificationFailureReason: finalVerificationFailureReason,
          promotionStatus: finalPromotionStatus,
          promotionReady: finalPromotionReady,
          screeningVsVerificationDiff: finalScreeningVsVerificationDiff,
          candidateHash: currentCandidate.artifact.pineHash,
          baselineHash: seedStrategy.candidateHash,
          artifactBundle: finalArtifactBundle,
        }),
      });
      await rebuildIndexes(stateRoot);
      await logMonitor(input.monitor, "state.recorded", "Compile failure recorded", {
        candidateId: currentCandidate.artifact.candidateId,
        decision: "compile_fail",
      });
      return {
        decision: "compile_fail",
        experiment,
        conditionContributions: [],
        hypothesis,
      };
    }

    if (finalDecision === "apply_fail") {
      const finalAnalysisSummary = synthesizeFinalAnalysis({
        decision: "apply_fail",
        pineAnalysis: currentPineAnalysis,
      });
      const artifactPaths = await writeIterationArtifacts({
        workspaceRoot: input.workspaceRoot,
        stateRoot,
        candidateId: currentCandidate.artifact.candidateId,
        iteration,
        syncArtifact: finalSyncArtifact,
        pineAnalysisArtifact: currentPineAnalysis,
      });
      const experiment = await appendExperimentRecord(stateRoot, {
        ...currentBaseExperiment,
        candidateScore: null,
        decision: "apply_fail",
        status: "apply_failed",
        compile: finalCompile,
        apply: finalApply,
        syncArtifact: finalSyncArtifact,
        pineAnalysisSummary: currentPineAnalysis,
        finalAnalysisSummary,
        artifactPaths: {
          ...(currentBaseExperiment.artifactPaths ?? {}),
          ...artifactPaths,
          ...executorArtifactPaths,
        },
        ...buildExperimentV2Fields({
          mutationParseStatus: currentMutationParseStatus,
          mutationProvenance: currentMutationProvenance(currentMutationParseStatus),
          executorCapability: finalExecutorCapability,
          artifactValidation: finalArtifactValidation,
          verificationStatus: finalVerificationStatus,
          verificationFailureReason: finalVerificationFailureReason,
          promotionStatus: finalPromotionStatus,
          promotionReady: finalPromotionReady,
          screeningVsVerificationDiff: finalScreeningVsVerificationDiff,
          candidateHash: currentCandidate.artifact.pineHash,
          baselineHash: seedStrategy.candidateHash,
          artifactBundle: finalArtifactBundle,
        }),
      });
      if (finalApply?.attachDiagnostics?.staleStudySuspected) {
        await appendIncidentRecord(stateRoot, {
          runId: experiment.runId,
          iteration: experiment.iteration,
          candidateId: experiment.candidateId,
          incidentType: "stale_attach_detected",
          detail: `Expected ${currentCandidate.artifact.studyTitle} but detected ${finalApply.attachDiagnostics.detectedStudyTitle}.`,
        });
      }
      await rebuildIndexes(stateRoot);
      await logMonitor(input.monitor, "state.recorded", "Apply failure recorded", {
        candidateId: currentCandidate.artifact.candidateId,
        decision: "apply_fail",
      });
      return {
        decision: "apply_fail",
        experiment,
        conditionContributions: [],
        hypothesis,
      };
    }

    let lossAnalysis: LossAnalysisSummary;
    let tradeContextArtifact: Record<string, unknown> | undefined;
    let marketContextPath: string | null = null;
    if (!finalArtifactBundle || finalArtifactBundle.trades.length === 0) {
      tradeContextArtifact = {
        generatedAt: new Date().toISOString(),
        candidateId: currentCandidate.artifact.candidateId,
        status: "no_trades",
        trades: [],
      };
      lossAnalysis = createNoTradesLossAnalysis();
    } else {
      try {
        const marketContext = await loadMarketContext(input.workspaceRoot, {
          symbol: objective.symbol,
          timeframe: objective.timeframe,
        });
        marketContextPath = marketContext.cachePath;
        const enrichedTrades = enrichTradesWithMarketContext(
          finalArtifactBundle.trades,
          marketContext.bars,
        );
        tradeContextArtifact = {
          generatedAt: new Date().toISOString(),
          candidateId: currentCandidate.artifact.candidateId,
          barsAnalyzed: marketContext.bars.length,
          fromCache: marketContext.fromCache,
          trades: enrichedTrades,
        };
        lossAnalysis = summarizeLossZones(enrichedTrades);
      } catch (error) {
        const detail = error instanceof Error ? error.message : String(error);
        await appendIncidentRecord(stateRoot, {
          runId,
          iteration,
          candidateId: currentCandidate.artifact.candidateId,
          incidentType: "market_context_load_failed",
          detail,
        });
        tradeContextArtifact = {
          generatedAt: new Date().toISOString(),
          candidateId: currentCandidate.artifact.candidateId,
          status: "market_context_unavailable",
          trades: finalArtifactBundle.trades,
        };
        lossAnalysis = createMarketContextUnavailableLossAnalysis();
      }
    }
    await logMonitor(input.monitor, "analysis.loss_zones", "Loss-zone analysis completed", {
      status: lossAnalysis.status,
      summary: lossAnalysis.summary,
      topLossZones: lossAnalysis.topLossZones,
      repairPriorities: lossAnalysis.repairPriorities,
    });

    if (
      finalDecision === "backtest_empty" ||
      finalDecision === "artifact_incomplete" ||
      finalDecision === "verification_fail" ||
      !finalArtifactBundle ||
      !finalTesterMetrics ||
      !finalObjectiveBreakdown
    ) {
      const recordedDecision =
        finalDecision === "artifact_incomplete" ||
        finalDecision === "verification_fail"
          ? finalDecision
          : "backtest_empty";
      const finalAnalysisSummary = synthesizeFinalAnalysis({
        decision: recordedDecision,
        pineAnalysis: currentPineAnalysis,
        lossAnalysis,
      });
      const objectiveArtifact =
        finalObjectiveBreakdown && finalTesterMetrics
          ? {
              ...buildObjectiveArtifact({
                candidateId: currentCandidate.artifact.candidateId,
                decision: recordedDecision,
                objectiveBreakdown: finalObjectiveBreakdown,
                strategyMetrics: finalTesterMetrics,
                attachDiagnostics: finalArtifactBundle?.attachDiagnostics,
                artifactValidation: finalArtifactValidation,
                verificationStatus: finalVerificationStatus,
                verificationFailureReason: finalVerificationFailureReason,
                verificationRuntimeFailureKind: finalVerificationRuntimeFailureKind,
                recoveryAttempts: finalRecoveryAttempts,
                fallbackEvaluation: finalFallbackEvaluation,
                promotionStatus: finalPromotionStatus,
                promotionReady: finalPromotionReady,
                screeningVsVerificationDiff: finalScreeningVsVerificationDiff,
                recordEra: "v2",
                pineAnalysisSummary: currentPineAnalysis,
                finalAnalysisSummary,
              }),
              evaluationStages: {
                primaryExecutor: input.executorName ?? null,
                promotionVerificationExecutor:
                  input.promotionVerificationExecutorName ?? null,
                primaryScreeningArtifact: screeningArtifactPath ?? null,
                promotionVerificationArtifact: verificationArtifactPath ?? null,
              },
            }
          : undefined;
      const artifactPaths = await writeIterationArtifacts({
        workspaceRoot: input.workspaceRoot,
        stateRoot,
        candidateId: currentCandidate.artifact.candidateId,
        iteration,
        syncArtifact: finalSyncArtifact,
        artifactBundle: finalArtifactBundle,
        objectiveArtifact,
        tradeContextArtifact,
        lossAnalysisArtifact: lossAnalysis,
        pineAnalysisArtifact: currentPineAnalysis,
        fallbackEvaluationArtifact,
      });
      const experiment = await appendExperimentRecord(stateRoot, {
        ...currentBaseExperiment,
        candidateScore: null,
        decision: recordedDecision,
        status:
          recordedDecision === "verification_fail"
            ? "verification_failed"
            : recordedDecision,
        compile: finalCompile,
        apply: finalApply,
        syncArtifact: finalSyncArtifact,
        artifactBundle: finalArtifactBundle,
        testerMetrics: finalTesterMetrics,
        pineAnalysisSummary: currentPineAnalysis,
        finalAnalysisSummary,
        lossAnalysisSummary: lossAnalysis,
        topLossZones: lossAnalysis.topLossZones,
        repairPriorities: lossAnalysis.repairPriorities,
        nextMutationHints: mergeHints(
          currentMutation.nextMutationHints,
          lossAnalysis.repairPriorities,
        ),
        artifactPaths: {
          ...(currentBaseExperiment.artifactPaths ?? {}),
          ...artifactPaths,
          ...executorArtifactPaths,
          ...(marketContextPath
            ? { marketContext: marketContextPath }
            : {}),
        },
        ...buildExperimentV2Fields({
          mutationParseStatus: currentMutationParseStatus,
          mutationProvenance: currentMutationProvenance(currentMutationParseStatus),
          executorCapability: finalExecutorCapability,
          artifactValidation: finalArtifactValidation,
          verificationStatus: finalVerificationStatus,
          verificationFailureReason: finalVerificationFailureReason,
          verificationRuntimeFailureKind: finalVerificationRuntimeFailureKind,
          recoveryAttempts: finalRecoveryAttempts,
          fallbackEvaluation: finalFallbackEvaluation,
          promotionStatus: finalPromotionStatus,
          promotionReady: finalPromotionReady,
          screeningVsVerificationDiff: finalScreeningVsVerificationDiff,
          candidateHash: currentCandidate.artifact.pineHash,
          baselineHash: seedStrategy.candidateHash,
          artifactBundle: finalArtifactBundle,
        }),
      });
      await rebuildIndexes(stateRoot);
      await logMonitor(input.monitor, "state.recorded", "Empty backtest recorded", {
        candidateId: currentCandidate.artifact.candidateId,
        decision: recordedDecision,
      });
      return {
        decision: recordedDecision,
        experiment,
        conditionContributions: [],
        hypothesis: {
          ...hypothesis,
          nextMutationDirection:
            lossAnalysis.repairPriorities.join(" ") ||
            hypothesis.nextMutationDirection,
        },
      };
    }

    await logMonitor(input.monitor, "evaluation.objective", "Objective evaluated", {
      decision: finalDecision,
      score: finalObjectiveBreakdown.score,
      hardGatesPassed: finalObjectiveBreakdown.hardGatesPassed,
      softGuardrailBreached: finalObjectiveBreakdown.softGuardrailBreached,
      executor:
        verificationArtifactPath != null
          ? input.promotionVerificationExecutorName ?? null
          : input.executorName ?? null,
    });

    let conditionContributions: ConditionContribution[] = [];
    if (
      shouldComputeConditionContributions({
        decision: finalDecision,
        candidateScore: finalObjectiveBreakdown.score,
        hardGatesPassed: finalObjectiveBreakdown.hardGatesPassed,
        acceptedHeadScore,
      })
    ) {
      const evaluateVariantMetrics = async (variantSource: string) => {
        const expectedStudyTitle =
          currentCandidate.artifact.studyTitle ??
          extractStudyTitle(currentCandidate.candidateSource) ??
          extractStudyTitle(variantSource);
        const normalizedVariantSource = enforceStudyTitle(
          variantSource,
          expectedStudyTitle,
        );

        try {
          await contributionExecutor.updateStrategySource(normalizedVariantSource);
          const variantCompile = await contributionExecutor.compileStrategy();
          if (!variantCompile.ok) {
            return null;
          }

          const variantApply = await contributionExecutor.applyStrategy({
            expectedStudyTitle,
          });
          if (!variantApply.ok) {
            return null;
          }

          const variantBundle = await contributionExecutor.readArtifactBundle({
            expectedStudyTitle,
            maxTrades: input.maxTrades,
          });
          return variantBundle.strategy;
        } finally {
          await contributionExecutor.updateStrategySource(currentCandidate.candidateSource);
          const restoreCompile = await contributionExecutor.compileStrategy();
          if (restoreCompile.ok) {
            await contributionExecutor.applyStrategy({
              expectedStudyTitle: currentCandidate.artifact.studyTitle,
            });
          }
        }
      };

      conditionContributions = await computeConditionContributions(
        currentCandidate.artifact.inventory,
        finalTesterMetrics,
        objective,
        acceptedHeadScore,
        async (condition) => {
          const directAblationMetrics =
            (await contributionExecutor.evaluateAblation?.({
              condition,
              source: currentCandidate.candidateSource,
            })) ?? null;
          if (directAblationMetrics) {
            return directAblationMetrics;
          }

          try {
            const ablationResponse =
              await input.llmClient.generateConditionAblation({
                brief,
                candidatePine: currentCandidate.candidateSource,
                condition,
                candidateSummary: currentMutation.candidateSummary,
                inventory: currentCandidate.artifact.inventory,
              });
            const parsedAblation = parseMutationResponseStrict(ablationResponse);
            return await evaluateVariantMetrics(parsedAblation.pineScript);
          } catch (error) {
            await logMonitor(
              input.monitor,
              "evaluation.ablation_failed",
              "Condition ablation evaluation failed",
              {
                conditionId: condition.conditionId,
                error: error instanceof Error ? error.message : String(error),
              },
            );
            return null;
          }
        },
      );
      await logMonitor(
        input.monitor,
        "evaluation.contributions",
        "Condition contributions computed",
        {
          contributionCount: conditionContributions.length,
        },
      );
    } else {
      await logMonitor(
        input.monitor,
        "evaluation.contributions_skipped",
        "Condition contributions skipped for non-frontier candidate",
        {
          decision: finalDecision,
          score: finalObjectiveBreakdown.score,
          hardGatesPassed: finalObjectiveBreakdown.hardGatesPassed,
          acceptedHeadScore,
        },
      );
    }

    const finalAnalysisSummary = synthesizeFinalAnalysis({
      decision: finalDecision,
      pineAnalysis: currentPineAnalysis,
      lossAnalysis,
      conditionContributions,
    });
    const objectiveArtifact = {
      ...buildObjectiveArtifact({
        candidateId: currentCandidate.artifact.candidateId,
        decision: finalDecision,
        objectiveBreakdown: finalObjectiveBreakdown,
        strategyMetrics: finalTesterMetrics,
        attachDiagnostics: finalArtifactBundle.attachDiagnostics,
        artifactValidation: finalArtifactValidation,
        verificationStatus: finalVerificationStatus,
        verificationFailureReason: finalVerificationFailureReason,
        verificationRuntimeFailureKind: finalVerificationRuntimeFailureKind,
        recoveryAttempts: finalRecoveryAttempts,
        fallbackEvaluation: finalFallbackEvaluation,
        promotionStatus: finalPromotionStatus,
        promotionReady: finalPromotionReady,
        screeningVsVerificationDiff: finalScreeningVsVerificationDiff,
        recordEra: "v2",
        pineAnalysisSummary: currentPineAnalysis,
        finalAnalysisSummary,
      }),
      evaluationStages: {
        primaryExecutor: input.executorName ?? null,
        promotionVerificationExecutor:
          input.promotionVerificationExecutorName ?? null,
        primaryScreeningArtifact: screeningArtifactPath ?? null,
        promotionVerificationArtifact: verificationArtifactPath ?? null,
      },
    };
    const artifactPaths = await writeIterationArtifacts({
      workspaceRoot: input.workspaceRoot,
      stateRoot,
      candidateId: currentCandidate.artifact.candidateId,
      iteration,
      syncArtifact: finalSyncArtifact,
      artifactBundle: finalArtifactBundle,
      objectiveArtifact,
      tradeContextArtifact,
      lossAnalysisArtifact: lossAnalysis,
      pineAnalysisArtifact: currentPineAnalysis,
      fallbackEvaluationArtifact,
    });

    const experiment = await appendExperimentRecord(stateRoot, {
      ...currentBaseExperiment,
      candidateScore: finalObjectiveBreakdown.score,
      decision: finalDecision,
      status: "evaluated",
      compile: finalCompile,
      apply: finalApply,
      testerMetrics: finalTesterMetrics,
      syncArtifact: finalSyncArtifact,
      artifactBundle: finalArtifactBundle,
      objectiveBreakdown: finalObjectiveBreakdown,
      conditionContributions,
      pineAnalysisSummary: currentPineAnalysis,
      finalAnalysisSummary,
      lossAnalysisSummary: lossAnalysis,
      topLossZones: lossAnalysis.topLossZones,
      repairPriorities: lossAnalysis.repairPriorities,
      nextMutationHints: mergeHints(
        currentMutation.nextMutationHints,
        lossAnalysis.repairPriorities,
      ),
      artifactPaths: {
        ...(currentBaseExperiment.artifactPaths ?? {}),
        ...artifactPaths,
        ...executorArtifactPaths,
          ...(marketContextPath
            ? { marketContext: marketContextPath }
            : {}),
      },
        ...buildExperimentV2Fields({
          mutationParseStatus: currentMutationParseStatus,
          mutationProvenance: currentMutationProvenance(currentMutationParseStatus),
          executorCapability: finalExecutorCapability,
          artifactValidation: finalArtifactValidation,
          verificationStatus: finalVerificationStatus,
          verificationFailureReason: finalVerificationFailureReason,
          verificationRuntimeFailureKind: finalVerificationRuntimeFailureKind,
          recoveryAttempts: finalRecoveryAttempts,
          fallbackEvaluation: finalFallbackEvaluation,
          promotionStatus: finalPromotionStatus,
          promotionReady: finalPromotionReady,
          screeningVsVerificationDiff: finalScreeningVsVerificationDiff,
          candidateHash: currentCandidate.artifact.pineHash,
          baselineHash: seedStrategy.candidateHash,
          artifactBundle: finalArtifactBundle,
        }),
    });

    await rebuildIndexes(stateRoot);
    await logMonitor(
      input.monitor,
      "state.recorded",
      "Experiment recorded and indexes rebuilt",
      {
        candidateId: currentCandidate.artifact.candidateId,
        decision: finalDecision,
        score: finalObjectiveBreakdown.score,
      },
    );
    return {
      decision: finalDecision,
      experiment,
      conditionContributions,
      hypothesis: {
        ...hypothesis,
        nextMutationDirection:
          lossAnalysis.repairPriorities.join(" ") ||
          hypothesis.nextMutationDirection,
      },
    };
  } finally {
    await verificationExecutor?.close?.();
  }
}
