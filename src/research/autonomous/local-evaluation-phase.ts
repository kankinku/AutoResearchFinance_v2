import {
  type LocalCompatibilityIssue,
  type ObjectiveConfig,
} from "../../contracts/types.js";
import {
  type AutonomousEligibility,
  type AutonomousExperimentRecord,
  type AutonomousLocalCompatibility,
  type AutonomousResearchStage,
  type LocalConfidenceEventRecord,
  type LocalEvaluationBlockingReason,
  type NoveltyFingerprint,
  type ProblemEventRecord,
  type RepairAttemptRecord,
} from "../../contracts/autonomous.js";
import { type PineEvaluationExecutor } from "../../automation/common/executor.js";
import { validateArtifactBundle } from "../../evaluation/artifact-validation.js";
import {
  type AutonomousCalibrationSignal,
  buildAutoSelectionBreakdown,
  buildParameterNeighborhoodFromStrategySpec,
  buildNoveltyFingerprint,
  classifyDuplicateStatus,
  evaluateLocalSplit,
  estimateHistoricalLocalConfidence,
  getAutonomousSelectionPolicyVersion,
  getObjectivePolicyVersion,
  type AutonomousScoringReferenceRecord,
} from "../../evaluation/autonomous-scoring.js";
import { evaluateObjective } from "../../evaluation/objective.js";
import { computeAfConditionAttribution } from "../../evaluation/af-condition-attribution.js";
import { buildObjectiveArtifact, writeIterationArtifacts } from "../artifact-writer.js";
import { type MutationProvenance, type ParsedMutationResponse } from "../../contracts/types.js";
import { appendExperimentRecord, appendProblemEventRecord } from "../../state/jsonl-store.js";
import { type ExperimentRecord } from "../../contracts/types.js";
import { createCandidateId, fileExists, sha256 } from "../../utils/fs.js";
import { autonomousExperimentSchema } from "../../contracts/autonomous.js";
import {
  AUTORESEARCH_CONTRACT_VERSION,
  STRATEGY_SPEC_MUTATION_AUTHORITY,
} from "../../policy/autoresearch-contract.js";
import {
  resolveLocalConfidenceSignal,
  resolveStructureFamilyHash,
} from "./divergence-update-phase.js";
import {
  buildCompatibilityBlockingReasons,
  buildLocalCompatibilityStatus,
} from "./local-compatibility-phase.js";

interface MonitorLike {
  log: (
    event: string,
    message: string,
    details?: Record<string, unknown>,
  ) => Promise<void>;
}

export interface LocalEvaluationPhaseResult {
  record: AutonomousExperimentRecord;
  shouldArchive: boolean;
  shouldQueueCalibration: boolean;
  problemEvent: ProblemEventRecord | null;
}

const STANDOUT_REFERENCE_MIN_COUNT = 20;
const STANDOUT_ABSOLUTE_THRESHOLDS = {
  autoSelectionScore: 0.85,
  performanceScore: 0.72,
  noveltyScore: 0.24,
  robustnessScore: 0.12,
} as const;
const STANDOUT_RELATIVE_GAPS = {
  autoSelectionScore: 0.08,
  performanceScore: 0.05,
  noveltyScore: 0.04,
  robustnessScore: 0.03,
} as const;

export async function runLocalEvaluationPhase(input: {
  workspaceRoot: string;
  stateRoot: string;
  targetId?: string | null;
  symbol?: string | null;
  timeframe?: string | null;
  goalMode?: AutonomousExperimentRecord["goalMode"];
  goalProfileId?: string | null;
  runId: string;
  iteration: number;
  executor: PineEvaluationExecutor;
  objective: ObjectiveConfig;
  parsedMutation: ParsedMutationResponse;
  candidateArtifact: {
    candidateId: string;
    parentId: string | null;
    branchId: string;
    pinePath: string;
    pineHash: string;
    specPath?: string | null;
    specHash?: string | null;
    studyTitle: string | null;
    inventory: ParsedMutationResponse["inventory"];
    candidateSummary: string;
    nextMutationHints: string[];
  };
  mutationProvenance: MutationProvenance;
  previousExperiments: ExperimentRecord[];
  previousConfidenceEvents?: LocalConfidenceEventRecord[];
  previousProblemEvents?: ProblemEventRecord[];
  previousRepairAttempts?: RepairAttemptRecord[];
  bootstrapMetadata?: {
    source: "local_compatible_seed";
    reason: string;
  };
  signal?: AbortSignal;
  monitor?: MonitorLike;
}): Promise<LocalEvaluationPhaseResult> {
  const pineScript = input.parsedMutation.pineScript;
  const candidatePathExists = await fileExists(input.candidateArtifact.pinePath);
  const specAuthorityStatus = buildSpecAuthorityStatus({
    strategySpec: input.parsedMutation.strategySpec,
    specPath: input.candidateArtifact.specPath ?? null,
    specHash: input.candidateArtifact.specHash ?? null,
  });
  const chartTarget = {
    symbol: input.objective.symbol,
    timeframe: input.objective.timeframe,
    chartType: "candles",
  };
  const executorCapability = input.executor.getCapability();
  const scoringReferences = input.previousExperiments
    .map((record) => {
      const noveltyFingerprint = (record as Record<string, unknown>)
        .noveltyFingerprint as NoveltyFingerprint | undefined;
      return {
        candidateId: record.candidateId,
        candidateHash: record.candidateHash ?? null,
        noveltyFingerprint,
      } satisfies AutonomousScoringReferenceRecord;
    });
  const fingerprintResult = buildNoveltyFingerprint(input.parsedMutation);
  const parameterNeighborhood = buildParameterNeighborhoodFromStrategySpec(
    input.parsedMutation.strategySpec,
  );
  const structureFamilyHash = resolveStructureFamilyHash({
    noveltyFingerprint: fingerprintResult.fingerprint,
    candidateId: input.candidateArtifact.candidateId,
    conditionInventory: input.candidateArtifact.inventory,
  });
  const directLocalConfidenceSignal = resolveLocalConfidenceSignal({
    confidenceEvents: input.previousConfidenceEvents ?? [],
    structureFamilyHash,
  });
  const inheritedLocalConfidenceSignal =
    directLocalConfidenceSignal.currentConfidence == null
      ? resolveInheritedConfidenceSignal({
          confidenceEvents: input.previousConfidenceEvents ?? [],
          experiments: input.previousExperiments,
          parentCandidateId: input.candidateArtifact.parentId,
        })
      : null;
  const localConfidenceSignal =
    directLocalConfidenceSignal.currentConfidence != null
      ? directLocalConfidenceSignal
      : inheritedLocalConfidenceSignal ?? directLocalConfidenceSignal;
  const estimatedLocalConfidence = estimateHistoricalLocalConfidence({
    experiments: input.previousExperiments,
    fingerprintFamily: fingerprintResult.fingerprint.fingerprintFamily,
  });
  const resolvedLocalConfidence =
    localConfidenceSignal.currentConfidence ?? estimatedLocalConfidence;

  const baseRecord = {
    targetId: input.targetId ?? null,
    symbol: input.symbol ?? input.objective.symbol,
    timeframe: input.timeframe ?? input.objective.timeframe,
    goalMode: input.goalMode,
    goalProfileId: input.goalProfileId ?? undefined,
    runId: input.runId,
    iteration: input.iteration,
    candidateId: input.candidateArtifact.candidateId,
    parentCandidateId: input.candidateArtifact.parentId,
    branchId: input.candidateArtifact.branchId,
    acceptedHeadCandidateId: null,
    baselineCandidateId: null,
    candidatePath: input.candidateArtifact.pinePath,
    candidateHash: input.candidateArtifact.pineHash,
    contractVersion: AUTORESEARCH_CONTRACT_VERSION,
    mutationAuthority: specAuthorityStatus.valid
      ? STRATEGY_SPEC_MUTATION_AUTHORITY
      : null,
    specPath: input.candidateArtifact.specPath ?? null,
    specHash: input.candidateArtifact.specHash ?? null,
    studyTitle: input.candidateArtifact.studyTitle,
    mutationBriefSummary: input.candidateArtifact.candidateSummary,
    conditionInventory: input.candidateArtifact.inventory,
    mutationProvenance: input.mutationProvenance,
    recordKind: "local_evaluation" as const,
    executorRole: "primary_local_backtest" as const,
    evidenceAuthority: "local_model" as const,
    evaluationMode: "local_primary" as const,
    objectivePolicyVersion: getObjectivePolicyVersion(),
    selectionPolicyVersion: getAutonomousSelectionPolicyVersion(),
    selectionPhase: input.bootstrapMetadata ? "bootstrap" : "steady_state",
    bootstrapSource: input.bootstrapMetadata?.source ?? null,
    bootstrapReason: input.bootstrapMetadata?.reason ?? null,
    researchStage: "candidate" as const,
    localConfidence: resolvedLocalConfidence,
    tvCalibrationStatus: "not_requested" as const,
    localTvParity: null,
    structureFamilyHash,
    fingerprintFamily: fingerprintResult.fingerprint.fingerprintFamily,
    parameterNeighborhood,
    recordMeta: {
      schemaVersion: "experiment/v3",
      recordHash: "",
      candidateHash: input.candidateArtifact.pineHash,
      baselineHash: null,
      artifactBundleHash: null,
      pipelineVersion: "af-autonomous-spec-authority/v4",
    },
  };

  if (!specAuthorityStatus.valid) {
    const blockingReasons: LocalEvaluationBlockingReason[] = [
      {
        kind: "missing_strategy_spec",
        message: specAuthorityStatus.message,
        evidence: {
          reason: specAuthorityStatus.reason,
          hasStrategySpec: input.parsedMutation.strategySpec != null,
          specPath: input.candidateArtifact.specPath ?? null,
          specHash: input.candidateArtifact.specHash ?? null,
        },
        suggestedRepairKind: "schema_repair",
      },
    ];
    const eligibility = buildEligibilityStatus({
      autoSelectionEligible: false,
      bootstrapEligible: false,
      archiveEligible: false,
      calibrationEligible: false,
      blockingReasons,
    });
    const duplicateStatus = classifyDuplicateStatus({
      candidateId: input.candidateArtifact.candidateId,
      candidateHash: input.candidateArtifact.pineHash,
      noveltyFingerprint: fingerprintResult.fingerprint,
      references: scoringReferences,
    });
    const record = await appendLocalRecord(input.stateRoot, {
      ...baseRecord,
      decision: "local_spec_authority_missing",
      status: "rejected",
      candidateScore: null,
      artifactValidation: undefined,
      testerMetrics: undefined,
      objectiveBreakdown: undefined,
      splitEvaluation: null,
      noveltyFingerprint: fingerprintResult.fingerprint,
      duplicateStatus,
      localFrontierScore: null,
      autoSelectionScore: null,
      autoSelectionBreakdown: null,
      localCompatibility: buildLocalCompatibilityStatus({
        compatible: false,
        reason: specAuthorityStatus.message,
        issues: [],
      }),
      eligibility,
      artifactPaths: buildCandidateArtifactPaths(input.candidateArtifact),
    });
    const failureSignatureHash = sha256(
      JSON.stringify({
        problemKind: "mutation_generation_fail",
        reason: specAuthorityStatus.reason,
        structureFamily: structureFamilyHash,
      }),
    );
    const problemEvent = await appendProblemEventRecord(input.stateRoot, {
      problemEventId: createCandidateId("problem"),
      runId: input.runId,
      iteration: input.iteration,
      candidateId: input.candidateArtifact.candidateId,
      problemKind: "mutation_generation_fail",
      diagnosis: specAuthorityStatus.message,
      evidenceHash: sha256(
        JSON.stringify({
          reason: specAuthorityStatus.reason,
          specPath: input.candidateArtifact.specPath ?? null,
          specHash: input.candidateArtifact.specHash ?? null,
        }),
      ),
      suggestedRepairKind: "schema_repair",
      failureSignatureHash,
      structureFamily: structureFamilyHash,
    });
    return {
      record,
      shouldArchive: false,
      shouldQueueCalibration: false,
      problemEvent,
    };
  }

  const compatibility =
    (await input.executor.assessCompatibility?.({
      source: pineScript,
      chartTarget,
    })) ?? {
      supported: true,
      reasonCode: null,
      detail: null,
      issues: [],
    };
  throwIfAborted(input.signal);

  if (!compatibility.supported) {
    const localCompatibility = buildLocalCompatibilityStatus({
      compatible: false,
      reason: compatibility.detail ?? compatibility.reasonCode ?? null,
      issues: compatibility.issues ?? [],
    });
    const blockingReasons = buildCompatibilityBlockingReasons({
      reason: compatibility.detail ?? compatibility.reasonCode ?? null,
      issues: compatibility.issues ?? [],
    });
    const eligibility = buildEligibilityStatus({
      autoSelectionEligible: false,
      bootstrapEligible: false,
      archiveEligible: false,
      calibrationEligible: false,
      blockingReasons,
    });
    const failureSignatureHash = buildFailureSignatureHash({
        problemKind: "local_unsupported",
        structureFamily: structureFamilyHash,
        blockingReasons,
        gateReasons: [],
      });
    throwIfAborted(input.signal);
    const record = await appendLocalRecord(input.stateRoot, {
      ...baseRecord,
      decision: "local_unsupported",
      status: "unsupported",
      candidateScore: null,
      artifactValidation: undefined,
      testerMetrics: undefined,
      objectiveBreakdown: undefined,
      splitEvaluation: null,
      noveltyFingerprint: fingerprintResult.fingerprint,
      duplicateStatus: classifyDuplicateStatus({
        candidateId: input.candidateArtifact.candidateId,
        candidateHash: input.candidateArtifact.pineHash,
        noveltyFingerprint: fingerprintResult.fingerprint,
        references: scoringReferences,
      }),
      localFrontierScore: null,
      autoSelectionScore: null,
      autoSelectionBreakdown: null,
      localCompatibility,
      eligibility,
      artifactPaths: buildCandidateArtifactPaths(input.candidateArtifact),
    });
    throwIfAborted(input.signal);
    const problemEvent = await appendProblemEventRecord(input.stateRoot, {
      problemEventId: createCandidateId("problem"),
      runId: input.runId,
      iteration: input.iteration,
      candidateId: input.candidateArtifact.candidateId,
      problemKind: "local_unsupported",
      diagnosis: compatibility.detail ?? compatibility.reasonCode ?? "Local executor reported unsupported candidate.",
      evidenceHash: sha256(
        JSON.stringify({
          reasonCode: compatibility.reasonCode,
          detail: compatibility.detail,
          issues: compatibility.issues ?? [],
        }),
      ),
      suggestedRepairKind: determineSuggestedRepairKind({
        problemKind: "local_unsupported",
        failureSignatureHash,
        structureFamily: structureFamilyHash,
        blockingReasons,
        previousProblemEvents: input.previousProblemEvents ?? [],
        previousRepairAttempts: input.previousRepairAttempts ?? [],
      }),
      failureSignatureHash,
      structureFamily: structureFamilyHash,
    });
    return {
      record,
      shouldArchive: false,
      shouldQueueCalibration: false,
      problemEvent,
    };
  }

  await input.executor.prepareChart(chartTarget);
  await input.executor.updateStrategySource(pineScript);
  const compile = await input.executor.compileStrategy();
  throwIfAborted(input.signal);
  if (!compile.ok) {
    const localCompatibility = buildLocalCompatibilityStatus({
      compatible: true,
      reason: null,
      issues: [],
    });
    const eligibility = buildEligibilityStatus({
      autoSelectionEligible: false,
      bootstrapEligible: false,
      archiveEligible: false,
      calibrationEligible: false,
      blockingReasons: [
        {
          kind: "unknown",
          message: "Local compile failed before the candidate could be evaluated.",
          evidence: {
            decision: "local_compile_fail",
            errors: compile.errors,
          },
          suggestedRepairKind: "skip",
        },
      ],
    });
    throwIfAborted(input.signal);
    const record = await appendLocalRecord(input.stateRoot, {
      ...baseRecord,
      decision: "local_compile_fail",
      status: "compile_failed",
      candidateScore: null,
      artifactValidation: undefined,
      testerMetrics: undefined,
      objectiveBreakdown: undefined,
      splitEvaluation: null,
      noveltyFingerprint: fingerprintResult.fingerprint,
      duplicateStatus: classifyDuplicateStatus({
        candidateId: input.candidateArtifact.candidateId,
        candidateHash: input.candidateArtifact.pineHash,
        noveltyFingerprint: fingerprintResult.fingerprint,
        references: scoringReferences,
      }),
      localFrontierScore: null,
      autoSelectionScore: null,
      autoSelectionBreakdown: null,
      localCompatibility,
      eligibility,
      artifactPaths: buildCandidateArtifactPaths(input.candidateArtifact),
      compile,
    });
    throwIfAborted(input.signal);
    const problemEvent = await recordLocalBacktestProblem(input.stateRoot, {
      runId: input.runId,
      iteration: input.iteration,
      candidateId: input.candidateArtifact.candidateId,
      diagnosis: buildBacktestFailureDiagnosis("local_compile_fail", compile.errors),
      suggestedRepairKind: "pine_source_repair",
      evidence: {
        compile,
      },
      structureFamily: structureFamilyHash,
      gateReasons: ["local_compile_fail"],
      blockingReasons: eligibility.blockingReasons,
    });
    return {
      record,
      shouldArchive: false,
      shouldQueueCalibration: false,
      problemEvent,
    };
  }

  const apply = await input.executor.applyStrategy({
    expectedStudyTitle: input.candidateArtifact.studyTitle,
  });
  throwIfAborted(input.signal);
  if (!apply.ok) {
    const localCompatibility = buildLocalCompatibilityStatus({
      compatible: true,
      reason: null,
      issues: [],
    });
    const eligibility = buildEligibilityStatus({
      autoSelectionEligible: false,
      bootstrapEligible: false,
      archiveEligible: false,
      calibrationEligible: false,
      blockingReasons: [
        {
          kind: "unknown",
          message: "Local apply failed before the candidate could be evaluated.",
          evidence: {
            decision: "local_apply_fail",
            message: apply.message,
          },
          suggestedRepairKind: "skip",
        },
      ],
    });
    throwIfAborted(input.signal);
    const record = await appendLocalRecord(input.stateRoot, {
      ...baseRecord,
      decision: "local_apply_fail",
      status: "apply_failed",
      candidateScore: null,
      artifactValidation: undefined,
      testerMetrics: undefined,
      objectiveBreakdown: undefined,
      splitEvaluation: null,
      noveltyFingerprint: fingerprintResult.fingerprint,
      duplicateStatus: classifyDuplicateStatus({
        candidateId: input.candidateArtifact.candidateId,
        candidateHash: input.candidateArtifact.pineHash,
        noveltyFingerprint: fingerprintResult.fingerprint,
        references: scoringReferences,
      }),
      localFrontierScore: null,
      autoSelectionScore: null,
      autoSelectionBreakdown: null,
      localCompatibility,
      eligibility,
      artifactPaths: buildCandidateArtifactPaths(input.candidateArtifact),
      compile,
      apply,
    });
    throwIfAborted(input.signal);
    const problemEvent = await recordLocalBacktestProblem(input.stateRoot, {
      runId: input.runId,
      iteration: input.iteration,
      candidateId: input.candidateArtifact.candidateId,
      diagnosis: buildBacktestFailureDiagnosis("local_apply_fail", [apply.message]),
      suggestedRepairKind: "pine_source_repair",
      evidence: {
        apply,
      },
      structureFamily: structureFamilyHash,
      gateReasons: ["local_apply_fail"],
      blockingReasons: eligibility.blockingReasons,
    });
    return {
      record,
      shouldArchive: false,
      shouldQueueCalibration: false,
      problemEvent,
    };
  }

  const artifactBundle = await input.executor.readArtifactBundle({
    expectedStudyTitle: input.candidateArtifact.studyTitle,
  });
  throwIfAborted(input.signal);
  const artifactValidation = validateArtifactBundle({
    artifactBundle,
    executorCapability,
  });
  const testerMetrics = artifactBundle.strategy ?? null;
  const objectiveBreakdown =
    testerMetrics && testerMetrics.totalTrades > 0
      ? evaluateObjective(testerMetrics, input.objective)
      : null;
  const splitEvaluation = await evaluateLocalSplit({
    workspaceRoot: input.workspaceRoot,
    stateRoot: input.stateRoot,
    pineScript,
    strategySpec: input.parsedMutation.strategySpec,
    objective: input.objective,
    fullSampleArtifactBundle: artifactBundle,
  });
  throwIfAborted(input.signal);
  const duplicateStatus = classifyDuplicateStatus({
    candidateId: input.candidateArtifact.candidateId,
    candidateHash: input.candidateArtifact.pineHash,
    noveltyFingerprint: fingerprintResult.fingerprint,
    references: scoringReferences,
  });
    const bootstrapProvenanceOverride =
      Boolean(input.bootstrapMetadata) &&
      input.mutationProvenance.parseStatus === "valid" &&
      !!input.mutationProvenance.briefHash &&
      !!input.mutationProvenance.promptHash &&
      !!input.mutationProvenance.responseHash &&
      input.mutationProvenance.missingFields.length === 0;
    const provenanceValid =
      bootstrapProvenanceOverride ||
      (input.mutationProvenance.parseStatus === "valid" &&
        input.mutationProvenance.inventorySource === "llm" &&
        !!input.mutationProvenance.briefHash &&
        !!input.mutationProvenance.promptHash &&
        !!input.mutationProvenance.responseHash &&
        input.mutationProvenance.inferredFields.length === 0 &&
        input.mutationProvenance.missingFields.length === 0);
  const autoSelectionBreakdown = buildAutoSelectionBreakdown({
    objectiveBreakdown,
    artifactValidation,
    splitEvaluation,
    noveltyFingerprint: fingerprintResult.fingerprint,
    duplicateStatus,
    referenceFingerprints: scoringReferences.map((record) => record.noveltyFingerprint),
    referenceExperiments: input.previousExperiments,
    config: fingerprintResult.config,
    candidatePathExists,
    candidateHashExists: Boolean(input.candidateArtifact.pineHash),
    mutationProvenanceValid: provenanceValid && specAuthorityStatus.valid,
    localConfidenceSignal: mapConfidenceSignal(localConfidenceSignal),
  });
  const conditionContributions =
    testerMetrics && testerMetrics.totalTrades > 0
      ? await computeAfConditionAttribution({
          workspaceRoot: input.workspaceRoot,
          stateRoot: input.stateRoot,
          pineScript,
          strategySpec: input.parsedMutation.strategySpec,
          inventory: input.candidateArtifact.inventory,
          objective: input.objective,
          baseMetrics: testerMetrics,
        }).catch(() => [])
      : [];
  const decision =
    testerMetrics == null || testerMetrics.totalTrades <= 0
      ? "local_backtest_empty"
      : autoSelectionBreakdown.eligible
        ? "local_candidate_eligible"
        : "local_candidate_rejected";
  const localCompatibility = buildLocalCompatibilityStatus({
    compatible: true,
    reason: null,
    issues: [],
  });
  const blockingReasons = autoSelectionBreakdown.eligible
    ? []
    : buildRejectionBlockingReasons({
        rejectionReasons: autoSelectionBreakdown.rejectionReasons,
        testerMetrics,
        splitEvaluation,
        duplicateStatus,
        minimumTotalTrades: input.objective.hardGates.minimumTotalTrades,
      });
  const failureSignatureHash = autoSelectionBreakdown.eligible
    ? null
    : buildFailureSignatureHash({
        problemKind: "local_backtest_fail",
        structureFamily: structureFamilyHash,
        blockingReasons,
        gateReasons: splitEvaluation?.gateReasons ?? [],
      });
  const objectiveArtifact =
    objectiveBreakdown && testerMetrics
      ? buildObjectiveArtifact({
          candidateId: input.candidateArtifact.candidateId,
          decision,
          objectiveBreakdown,
          strategyMetrics: testerMetrics,
        })
      : undefined;
  throwIfAborted(input.signal);
  const artifactPaths = await writeIterationArtifacts({
    workspaceRoot: input.workspaceRoot,
    stateRoot: input.stateRoot,
    candidateId: input.candidateArtifact.candidateId,
    iteration: input.iteration,
    artifactBundle,
    objectiveArtifact,
  });
  throwIfAborted(input.signal);

  await input.monitor?.log("autonomous.local_evaluation", "Local autonomous evaluation completed", {
    candidateId: input.candidateArtifact.candidateId,
    score: autoSelectionBreakdown.totalScore,
    eligible: autoSelectionBreakdown.eligible,
    duplicateClassification: duplicateStatus.classification,
  });

  const standardArchive =
    autoSelectionBreakdown.eligible &&
    artifactValidation.hasMetrics &&
    artifactValidation.hasTrades &&
    artifactValidation.hasEquitySummary &&
    objectiveBreakdown?.hardGatesPassed === true &&
    duplicateStatus.classification === "unique";
  const standoutArchiveReasons = buildStandoutArchiveReasons({
    autoSelectionBreakdown,
    artifactValidation,
    duplicateStatus,
    previousExperiments: input.previousExperiments,
  });
  const shouldArchive = standardArchive || standoutArchiveReasons.length > 0;
  const shouldQueueCalibration =
    autoSelectionBreakdown.eligible ||
    autoSelectionBreakdown.noveltyScore >= 0.12;
  const bootstrapEligible =
    Boolean(input.bootstrapMetadata) &&
    artifactValidation.hasMetrics &&
    artifactValidation.hasTrades &&
    artifactValidation.hasEquitySummary &&
    duplicateStatus.classification === "unique" &&
    (testerMetrics?.totalTrades ?? 0) >= input.objective.hardGates.minimumTotalTrades &&
    (splitEvaluation?.outOfSample.metrics?.totalTrades ?? 0) >=
      splitEvaluation.minimumOosTrades;
  const eligibility = buildEligibilityStatus({
    autoSelectionEligible: autoSelectionBreakdown.eligible,
    bootstrapEligible,
    archiveEligible: shouldArchive || bootstrapEligible,
    calibrationEligible: shouldQueueCalibration || bootstrapEligible,
    blockingReasons,
  });

  throwIfAborted(input.signal);
  const record = await appendLocalRecord(input.stateRoot, {
    ...baseRecord,
    decision,
    status: decision === "local_candidate_eligible" ? "evaluated" : "rejected",
    candidateScore: autoSelectionBreakdown.totalScore,
    artifactValidation,
    testerMetrics,
    artifactBundle,
    conditionContributions,
    objectiveBreakdown,
    splitEvaluation,
    noveltyFingerprint: fingerprintResult.fingerprint,
    duplicateStatus,
    localFrontierScore: autoSelectionBreakdown.totalScore,
    autoSelectionScore: autoSelectionBreakdown.totalScore,
    autoSelectionBreakdown,
    localCompatibility,
    eligibility,
    researchStage: resolveLocalResearchStage({
      decision,
      eligibility,
      shouldArchive,
      shouldQueueCalibration,
    }),
    artifactPaths: {
      ...buildCandidateArtifactPaths(input.candidateArtifact),
      ...artifactPaths,
    },
    compile,
    apply,
  });
  let problemEvent: ProblemEventRecord | null = null;
  if (decision !== "local_candidate_eligible") {
    throwIfAborted(input.signal);
    problemEvent = await recordLocalBacktestProblem(input.stateRoot, {
      runId: input.runId,
      iteration: input.iteration,
      candidateId: input.candidateArtifact.candidateId,
      diagnosis: buildSelectionRejectionDiagnosis({
        decision,
        rejectionReasons: autoSelectionBreakdown.rejectionReasons,
        testerMetrics,
        splitEvaluation,
      }),
      suggestedRepairKind: determineSuggestedRepairKind({
        problemKind: "local_backtest_fail",
        failureSignatureHash,
        structureFamily: structureFamilyHash,
        blockingReasons,
        previousProblemEvents: input.previousProblemEvents ?? [],
        previousRepairAttempts: input.previousRepairAttempts ?? [],
      }),
      evidence: {
        decision,
        rejectionReasons: autoSelectionBreakdown.rejectionReasons,
        testerMetrics,
        splitEvaluation,
      },
      failureSignatureHash,
      structureFamily: structureFamilyHash,
      gateReasons: splitEvaluation?.gateReasons ?? [],
      blockingReasons,
    });
  }

  return {
    record,
    shouldArchive,
    shouldQueueCalibration,
    problemEvent,
  };
}

function resolveLocalResearchStage(input: {
  decision: string;
  eligibility: AutonomousEligibility;
  shouldArchive: boolean;
  shouldQueueCalibration: boolean;
}): AutonomousResearchStage {
  if (
    input.decision === "local_backtest_empty" ||
    input.decision === "local_candidate_rejected"
  ) {
    return "local_pass";
  }
  if (input.decision !== "local_candidate_eligible") {
    return "candidate";
  }
  if (input.eligibility.calibrationEligible || input.shouldQueueCalibration) {
    return "calibration_queued";
  }
  if (input.shouldArchive || input.eligibility.archiveEligible) {
    return "archive";
  }
  return "frontier";
}

function buildStandoutArchiveReasons(input: {
  autoSelectionBreakdown: AutonomousExperimentRecord["autoSelectionBreakdown"];
  artifactValidation: AutonomousExperimentRecord["artifactValidation"];
  duplicateStatus: AutonomousExperimentRecord["duplicateStatus"];
  previousExperiments: ExperimentRecord[];
}): string[] {
  const breakdown = input.autoSelectionBreakdown;
  if (
    !breakdown ||
    !input.artifactValidation?.hasMetrics ||
    !input.artifactValidation.hasTrades ||
    !input.artifactValidation.hasEquitySummary ||
    input.duplicateStatus?.classification !== "unique"
  ) {
    return [];
  }

  const references = input.previousExperiments
    .filter((record) => {
      const rawRecord = record as Record<string, unknown>;
      return rawRecord.recordKind === "local_evaluation";
    })
    .map((record) => (record as Record<string, unknown>).autoSelectionBreakdown)
    .filter(
      (value): value is NonNullable<AutonomousExperimentRecord["autoSelectionBreakdown"]> =>
        typeof value === "object" && value !== null,
    );

  const reasons: string[] = [];
  addAbsoluteStandoutReasons(reasons, breakdown);

  if (references.length >= STANDOUT_REFERENCE_MIN_COUNT) {
    addRelativeStandoutReason({
      reasons,
      metric: "autoSelectionScore",
      candidateScore: breakdown.totalScore,
      referenceScores: references.map((reference) => reference.totalScore),
      label: "overall",
    });
    addRelativeStandoutReason({
      reasons,
      metric: "performanceScore",
      candidateScore: breakdown.performanceScore ?? breakdown.baseObjectiveScore,
      referenceScores: references.map(
        (reference) => reference.performanceScore ?? reference.baseObjectiveScore,
      ),
      label: "performance",
    });
    addRelativeStandoutReason({
      reasons,
      metric: "noveltyScore",
      candidateScore: breakdown.noveltyScore,
      referenceScores: references.map((reference) => reference.noveltyScore),
      label: "novelty",
    });
    addRelativeStandoutReason({
      reasons,
      metric: "robustnessScore",
      candidateScore: breakdown.robustnessScore,
      referenceScores: references.map((reference) => reference.robustnessScore),
      label: "robustness",
    });
  }

  return reasons;
}

function addAbsoluteStandoutReasons(
  reasons: string[],
  breakdown: NonNullable<AutonomousExperimentRecord["autoSelectionBreakdown"]>,
): void {
  const metrics = [
    {
      metric: "autoSelectionScore" as const,
      label: "overall",
      value: breakdown.totalScore,
    },
    {
      metric: "performanceScore" as const,
      label: "performance",
      value: breakdown.performanceScore ?? breakdown.baseObjectiveScore,
    },
    {
      metric: "noveltyScore" as const,
      label: "novelty",
      value: breakdown.noveltyScore,
    },
    {
      metric: "robustnessScore" as const,
      label: "robustness",
      value: breakdown.robustnessScore,
    },
  ];

  for (const entry of metrics) {
    const threshold = STANDOUT_ABSOLUTE_THRESHOLDS[entry.metric];
    if (entry.value >= threshold) {
      reasons.push(
        `${entry.label}_score ${entry.value.toFixed(4)} crossed standalone archive threshold ${threshold.toFixed(4)}`,
      );
    }
  }
}

function addRelativeStandoutReason(input: {
  reasons: string[];
  metric: keyof typeof STANDOUT_RELATIVE_GAPS;
  candidateScore: number;
  referenceScores: number[];
  label: string;
}): void {
  if (!Number.isFinite(input.candidateScore)) {
    return;
  }
  const bestReferenceScore = input.referenceScores.reduce(
    (best, value) => (Number.isFinite(value) ? Math.max(best, value) : best),
    Number.NEGATIVE_INFINITY,
  );
  const minimumGap = STANDOUT_RELATIVE_GAPS[input.metric];
  if (
    bestReferenceScore !== Number.NEGATIVE_INFINITY &&
    input.candidateScore >= bestReferenceScore + minimumGap
  ) {
    input.reasons.push(
      `${input.label}_score ${input.candidateScore.toFixed(4)} beat the prior best ${bestReferenceScore.toFixed(4)} by at least ${minimumGap.toFixed(4)}`,
    );
  }
}

function mapConfidenceSignal(
  signal: ReturnType<typeof resolveLocalConfidenceSignal>,
): AutonomousCalibrationSignal | null {
  if (signal.currentConfidence == null) {
    return null;
  }
  return {
    currentConfidence: signal.currentConfidence,
    localConfidenceBonus: signal.localConfidenceBonus,
    divergencePenalty: signal.divergencePenalty,
  };
}

function throwIfAborted(signal: AbortSignal | undefined): void {
  if (!signal?.aborted) {
    return;
  }
  const reason = signal.reason;
  throw reason instanceof Error ? reason : new Error("Autonomous phase was aborted.");
}

function buildSpecAuthorityStatus(input: {
  strategySpec: unknown;
  specPath: string | null;
  specHash: string | null;
}):
  | { valid: true; reason: null; message: string }
  | { valid: false; reason: string; message: string } {
  if (input.strategySpec == null) {
    return {
      valid: false,
      reason: "strategy_spec_missing",
      message: "Autonomous local evaluation requires a strategySpec artifact.",
    };
  }
  if (!input.specPath) {
    return {
      valid: false,
      reason: "spec_path_missing",
      message: "Autonomous local evaluation requires a persisted specPath.",
    };
  }
  if (!input.specHash) {
    return {
      valid: false,
      reason: "spec_hash_missing",
      message: "Autonomous local evaluation requires a persisted specHash.",
    };
  }

  return {
    valid: true,
    reason: null,
    message: "Strategy spec artifact is present.",
  };
}

function buildCandidateArtifactPaths(input: {
  pinePath: string;
  specPath?: string | null;
}): Record<string, string> {
  return {
    candidate: input.pinePath,
    ...(input.specPath ? { spec: input.specPath } : {}),
  };
}

function resolveInheritedConfidenceSignal(input: {
  confidenceEvents: LocalConfidenceEventRecord[];
  experiments: ExperimentRecord[];
  parentCandidateId: string | null;
}): ReturnType<typeof resolveLocalConfidenceSignal> | null {
  if (!input.parentCandidateId) {
    return null;
  }
  const parentRecord = [...input.experiments]
    .reverse()
    .find((record) => {
      if (record.candidateId !== input.parentCandidateId) {
        return false;
      }
      return typeof (record as Record<string, unknown>).structureFamilyHash === "string";
    });
  const parentStructureFamilyHash =
    typeof (parentRecord as Record<string, unknown> | undefined)?.structureFamilyHash === "string"
      ? ((parentRecord as Record<string, unknown>).structureFamilyHash as string)
      : null;
  if (!parentStructureFamilyHash) {
    return null;
  }
  const parentSignal = resolveLocalConfidenceSignal({
    confidenceEvents: input.confidenceEvents,
    structureFamilyHash: parentStructureFamilyHash,
  });
  return parentSignal.currentConfidence == null ? null : parentSignal;
}

async function appendLocalRecord(
  stateRoot: string,
  record: Record<string, unknown>,
): Promise<AutonomousExperimentRecord> {
  const normalized = await appendExperimentRecord(
    stateRoot,
    record as Parameters<typeof appendExperimentRecord>[1],
  );
  return autonomousExperimentSchema.parse(normalized);
}

async function recordLocalBacktestProblem(
  stateRoot: string,
  input: {
    runId: string;
    iteration: number;
    candidateId: string;
    diagnosis: string;
    suggestedRepairKind:
      | "local_compatibility_repair"
      | "pine_source_repair"
      | "entry_frequency_repair"
      | "risk_logic_repair"
      | "mutation_prompt_adjustment"
      | "archive_gap_redirect";
    evidence: Record<string, unknown>;
    failureSignatureHash?: string | null;
    structureFamily?: string | null;
    gateReasons?: string[];
    blockingReasons?: LocalEvaluationBlockingReason[];
  },
): Promise<ProblemEventRecord> {
  const failureSignatureHash =
    input.failureSignatureHash ??
    buildFailureSignatureHash({
      problemKind: "local_backtest_fail",
      structureFamily: input.structureFamily ?? null,
      blockingReasons: input.blockingReasons ?? [],
      gateReasons: input.gateReasons ?? [],
    });
  return appendProblemEventRecord(stateRoot, {
    problemEventId: createCandidateId("problem"),
    runId: input.runId,
    iteration: input.iteration,
    candidateId: input.candidateId,
    problemKind: "local_backtest_fail",
    diagnosis: input.diagnosis,
    evidenceHash: sha256(JSON.stringify(input.evidence)),
    suggestedRepairKind: input.suggestedRepairKind,
    failureSignatureHash,
    structureFamily: input.structureFamily ?? null,
  });
}

function buildFailureSignatureHash(input: {
  problemKind: "local_backtest_fail" | "local_unsupported";
  structureFamily: string | null;
  blockingReasons: LocalEvaluationBlockingReason[];
  gateReasons: string[];
}): string {
  return sha256(
    JSON.stringify({
      problemKind: input.problemKind,
      structureFamily: input.structureFamily,
      blockingKinds: input.blockingReasons.map((reason) => reason.kind).sort(),
      gateReasons: [...input.gateReasons].sort(),
    }),
  );
}

function determineSuggestedRepairKind(input: {
  problemKind: "local_backtest_fail" | "local_unsupported";
  failureSignatureHash: string | null;
  structureFamily: string | null;
  blockingReasons: LocalEvaluationBlockingReason[];
  previousProblemEvents: ProblemEventRecord[];
  previousRepairAttempts: RepairAttemptRecord[];
}):
  | "local_compatibility_repair"
  | "entry_frequency_repair"
  | "risk_logic_repair"
  | "mutation_prompt_adjustment"
  | "archive_gap_redirect" {
  if (
    input.blockingReasons.some((reason) => reason.kind === "duplicate_candidate")
  ) {
    return "archive_gap_redirect";
  }

  const previousMatchingProblems = input.failureSignatureHash
    ? input.previousProblemEvents.filter(
        (event) => event.failureSignatureHash === input.failureSignatureHash,
      )
    : [];
  const previousMatchingProblemIds = new Set(
    previousMatchingProblems.map((event) => event.problemEventId),
  );
  const priorRepairCount = input.previousRepairAttempts.filter((attempt) =>
    previousMatchingProblemIds.has(attempt.problemEventId),
  ).length;

  if (input.problemKind === "local_unsupported") {
    return previousMatchingProblems.length >= 2 && priorRepairCount > 0
      ? "archive_gap_redirect"
      : "local_compatibility_repair";
  }

  if (previousMatchingProblems.length >= 2 && priorRepairCount > 0) {
    return "archive_gap_redirect";
  }

  if (
    input.blockingReasons.some(
      (reason) =>
        reason.kind === "low_trade_count" || reason.kind === "oos_trade_count_fail",
    )
  ) {
    return "entry_frequency_repair";
  }

  if (
    input.blockingReasons.some(
      (reason) =>
        reason.kind === "drawdown_limit_fail" ||
        reason.kind === "robustness_fail",
    )
  ) {
    return "risk_logic_repair";
  }

  return "mutation_prompt_adjustment";
}

function buildEligibilityStatus(input: {
  autoSelectionEligible: boolean;
  bootstrapEligible: boolean;
  archiveEligible: boolean;
  calibrationEligible: boolean;
  blockingReasons: LocalEvaluationBlockingReason[];
}): AutonomousEligibility {
  return {
    autoSelectionEligible: input.autoSelectionEligible,
    bootstrapEligible: input.bootstrapEligible,
    archiveEligible: input.archiveEligible,
    calibrationEligible: input.calibrationEligible,
    blockingReasons: input.blockingReasons,
  };
}

function buildRejectionBlockingReasons(input: {
  rejectionReasons: string[];
  testerMetrics: NonNullable<AutonomousExperimentRecord["testerMetrics"]> | null;
  splitEvaluation: AutonomousExperimentRecord["splitEvaluation"];
  duplicateStatus: AutonomousExperimentRecord["duplicateStatus"];
  minimumTotalTrades: number;
}): LocalEvaluationBlockingReason[] {
  const reasons: LocalEvaluationBlockingReason[] = [];
  const metrics = input.testerMetrics;
  const split = input.splitEvaluation;

  for (const rejectionReason of input.rejectionReasons) {
    switch (rejectionReason) {
      case "exact_duplicate":
      case "structural_duplicate":
        reasons.push({
          kind: "duplicate_candidate",
          message: `Rejected as ${rejectionReason}.`,
          evidence: {
            classification: input.duplicateStatus?.classification ?? null,
            duplicateFingerprint: input.duplicateStatus?.duplicateFingerprint ?? null,
          },
          suggestedRepairKind: "novelty_redirect",
        });
        break;
      case "minimum_oos_trades":
        reasons.push({
          kind: "oos_trade_count_fail",
          message: "Out-of-sample trade count fell below the required floor.",
          evidence: {
            minimumOosTrades: split?.minimumOosTrades ?? null,
            observedOosTrades: split?.outOfSample.metrics?.totalTrades ?? null,
          },
          suggestedRepairKind: "entry_frequency_repair",
        });
        break;
      case "oos_hard_gate_fail":
      case "positive_oos_post_fee_profit":
      case "oos_gate_fail":
        reasons.push({
          kind: "robustness_fail",
          message: `Out-of-sample robustness gate failed: ${rejectionReason}.`,
          evidence: {
            gateReasons: split?.gateReasons ?? [],
            oosPostFeeNetProfitPercent:
              split?.outOfSample.metrics?.postFeeNetProfitPercent ?? null,
          },
          suggestedRepairKind: "risk_logic_repair",
        });
        break;
      case "objective_hard_gate_fail":
        if ((metrics?.totalTrades ?? 0) < input.minimumTotalTrades) {
          reasons.push({
            kind: "low_trade_count",
            message: "Full-sample trade count fell below the objective floor.",
            evidence: {
              totalTrades: metrics?.totalTrades ?? null,
              minimumTotalTrades: input.minimumTotalTrades,
            },
            suggestedRepairKind: "entry_frequency_repair",
          });
        } else {
          reasons.push({
            kind: "unknown",
            message: "Objective hard gate failed for a non-trade-count reason.",
            evidence: {
              totalTrades: metrics?.totalTrades ?? null,
              postFeeNetProfitPercent: metrics?.postFeeNetProfitPercent ?? null,
            },
            suggestedRepairKind: "risk_logic_repair",
          });
        }
        break;
      case "local_artifact_incomplete":
      case "equity_summary_missing":
      case "candidate_source_missing":
      case "candidate_hash_missing":
      case "invalid_mutation_provenance":
        reasons.push({
          kind: "unknown",
          message: `Evaluation evidence was incomplete: ${rejectionReason}.`,
          evidence: {
            rejectionReason,
          },
          suggestedRepairKind: "skip",
        });
        break;
      default:
        break;
    }
  }

  if (
    metrics &&
    metrics.maxStrategyDrawdownPercent > 15 &&
    !reasons.some((reason) => reason.kind === "drawdown_limit_fail")
  ) {
    reasons.push({
      kind: "drawdown_limit_fail",
      message: "Strategy drawdown exceeded the soft guardrail.",
      evidence: {
        maxStrategyDrawdownPercent: metrics.maxStrategyDrawdownPercent,
      },
      suggestedRepairKind: "risk_logic_repair",
    });
  }

  if (reasons.length === 0) {
    reasons.push({
      kind: "unknown",
      message: "Candidate was rejected without a mapped blocking reason.",
      evidence: {
        rejectionReasons: input.rejectionReasons,
      },
      suggestedRepairKind: "skip",
    });
  }

  return reasons;
}

function buildBacktestFailureDiagnosis(decision: string, details: string[]): string {
  const normalizedDetails = details.filter((detail) => detail.trim().length > 0);
  if (normalizedDetails.length === 0) {
    return decision;
  }
  return `${decision}: ${normalizedDetails.join(" | ")}`;
}

function buildSelectionRejectionDiagnosis(input: {
  decision: string;
  rejectionReasons: string[];
  testerMetrics: NonNullable<AutonomousExperimentRecord["testerMetrics"]> | null;
  splitEvaluation: AutonomousExperimentRecord["splitEvaluation"];
}): string {
  const metrics = input.testerMetrics;
  const oosTrades = input.splitEvaluation?.outOfSample.metrics?.totalTrades ?? null;
  const oosProfit =
    input.splitEvaluation?.outOfSample.metrics?.postFeeNetProfitPercent ?? null;
  const parts = [
    input.decision,
    ...input.rejectionReasons,
    metrics ? `full_sample_trades=${metrics.totalTrades}` : null,
    oosTrades != null ? `oos_trades=${oosTrades}` : null,
    oosProfit != null ? `oos_post_fee_profit=${oosProfit}` : null,
  ].filter((part): part is string => part != null);
  return parts.join(" | ");
}
