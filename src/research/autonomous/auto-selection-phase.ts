import { type ExperimentRecord } from "../../contracts/types.js";
import {
  type AutonomousExperimentRecord,
  type HeadEventRecord,
} from "../../contracts/autonomous.js";
import {
  appendHeadEventRecord,
  readHeadEventRecords,
} from "../../state/jsonl-store.js";
import {
  collectSuppressedFamiliesFromReviews,
} from "./strategy-review-phase.js";
import { type StrategyReviewRecord } from "../../contracts/strategy-review.js";
import {
  buildSelectionEvidenceHash,
  compareAutonomousChampion,
  findActiveChampionRecord,
  isVerifiedPromotionEligible,
  selectLocalEvaluationRecords,
  selectBestChampionCandidate,
} from "../../state/autonomous-state.js";

export async function runAutoSelectionPhase(input: {
  stateRoot: string;
  runId: string;
  iteration: number;
  experiments: ExperimentRecord[];
  headEvents?: HeadEventRecord[];
  targetId?: string;
  strategyReviewRecords?: StrategyReviewRecord[];
  strategyReviewQuarantineConfidence?: number;
}): Promise<{
  activeChampionChanged: boolean;
  selectedCandidateId: string | null;
}> {
  const headEvents = input.headEvents ?? (await readHeadEventRecords(input.stateRoot));
  const suppressedFamilies = collectSuppressedFamiliesFromReviews({
    records: input.strategyReviewRecords ?? [],
    targetId: input.targetId,
    quarantineConfidence: input.strategyReviewQuarantineConfidence,
  });
  const selectableExperiments = filterSuppressedFamilyExperiments(
    input.experiments,
    suppressedFamilies,
  );
  const currentChampion = findActiveChampionRecord({
    records: input.experiments,
    headEvents,
  });
  const bootstrapTransitionCandidate = selectBootstrapTransitionCandidate({
    experiments: selectableExperiments,
    currentChampion,
  });
  const bootstrapTransitionApplied = bootstrapTransitionCandidate != null;
  const bestCandidate =
    bootstrapTransitionCandidate ??
    selectBestChampionCandidate(selectableExperiments) ??
    (!currentChampion
      ? [...selectLocalEvaluationRecords(selectableExperiments)]
          .filter((record) => record.eligibility?.bootstrapEligible === true)
          .sort(compareAutonomousChampion)[0] ?? null
      : null);
  const localRecords = selectLocalEvaluationRecords(selectableExperiments);
  const bestCandidateIsVerified =
    bestCandidate != null &&
    isVerifiedPromotionEligible({ record: bestCandidate, localRecords });
  const bestCandidateIsLocalPromotion =
    bestCandidate != null &&
    bestCandidate.recordKind === "local_evaluation" &&
    bestCandidate.selectionPhase === "steady_state" &&
    bestCandidate.eligibility?.autoSelectionEligible === true;
  const bestCandidateIsBootstrapSeed =
    bestCandidate != null &&
    isBootstrapSeedCandidate({
      record: bestCandidate,
      currentChampion,
    });
  if (
    !bestCandidate ||
    (!bestCandidateIsVerified &&
      !bestCandidateIsLocalPromotion &&
      !bestCandidateIsBootstrapSeed)
  ) {
    return {
      activeChampionChanged: false,
      selectedCandidateId: currentChampion?.candidateId ?? null,
    };
  }

  if (
    currentChampion &&
    !bootstrapTransitionApplied &&
    getChampionScore(currentChampion) >= getChampionScore(bestCandidate)
  ) {
    return {
      activeChampionChanged: false,
      selectedCandidateId: currentChampion.candidateId,
    };
  }

  const selectionEvidenceHash = buildSelectionEvidenceHash(bestCandidate, {
    previousChampionId: currentChampion?.candidateId ?? null,
    policyVersion: bestCandidate.selectionPolicyVersion,
  });
  const researchMaturity =
    bestCandidate.selectionPhase === "bootstrap"
      ? ("bootstrap" as const)
      : ("steady_state" as const);
  const commonFields = {
    runId: input.runId,
    iteration: input.iteration,
    candidateId: bestCandidate.candidateId,
    previousChampionId: currentChampion?.candidateId ?? null,
    selectedBy: "auto_policy" as const,
    policyVersion: bestCandidate.selectionPolicyVersion,
    headAuthority: bestCandidateIsVerified
      ? ("verified_promotion" as const)
      : bestCandidateIsLocalPromotion
        ? ("local_promotion" as const)
      : ("bootstrap_seed" as const),
    selectionPhase: bestCandidate.selectionPhase,
    bootstrapSource: bestCandidate.bootstrapSource ?? null,
    bootstrapReason: bestCandidate.bootstrapReason ?? null,
    researchMaturity,
    performanceScore:
      bestCandidate.verifiedPromotion?.scoreBreakdown?.tvPerformanceScore ??
      bestCandidate.autoSelectionBreakdown?.performanceScore ??
      bestCandidate.autoSelectionBreakdown?.baseObjectiveScore ??
      null,
    objectiveScore: bestCandidate.autoSelectionBreakdown?.baseObjectiveScore ?? null,
    noveltyScore: bestCandidate.autoSelectionBreakdown?.noveltyScore ?? null,
    robustnessScore: bestCandidate.autoSelectionBreakdown?.robustnessScore ?? null,
    autoSelectionScore:
      bestCandidate.verifiedPromotionScore ??
      bestCandidate.autoSelectionScore ??
      null,
    diversityScore: bestCandidate.autoSelectionBreakdown?.diversityScore ?? 0,
    diversityContribution: bestCandidate.autoSelectionBreakdown?.diversityScore ?? 0,
    localConfidenceBonus:
      bestCandidate.autoSelectionBreakdown?.localConfidenceBonus ?? 0,
    riskPenalty: bestCandidate.autoSelectionBreakdown?.riskPenalty ?? 0,
    overfitPenalty: bestCandidate.autoSelectionBreakdown?.overfitPenalty ?? 0,
    duplicatePenalty: bestCandidate.autoSelectionBreakdown?.duplicatePenalty ?? 0,
    divergencePenalty:
      bestCandidate.autoSelectionBreakdown?.divergencePenalty ?? 0,
    complexityPenalty: bestCandidate.autoSelectionBreakdown?.complexityPenalty ?? 0,
    selectionReason: currentChampion
      ? bootstrapTransitionApplied
        ? "Local promotion candidate displaced the bootstrap baseline champion."
        : bestCandidateIsLocalPromotion
          ? "Highest eligible local promotion score displaced the current champion."
          : "Highest eligible verified promotion score displaced the current champion."
      : bestCandidate.selectionPhase === "bootstrap"
        ? "Bootstrap local-compatible seed established the first autonomous research baseline champion."
        : "First local promotion candidate became the active champion.",
    selectionEvidenceHash,
    humanOverride: false as const,
  };

  await appendHeadEventRecord(input.stateRoot, {
    ...commonFields,
    eventKind: "auto_selected_head",
  });
  await appendHeadEventRecord(input.stateRoot, {
    ...commonFields,
    eventKind: "champion_updated",
  });

  return {
    activeChampionChanged: true,
    selectedCandidateId: bestCandidate.candidateId,
  };
}

function isBootstrapSeedCandidate(input: {
  record: AutonomousExperimentRecord;
  currentChampion: AutonomousExperimentRecord | null;
}): boolean {
  return (
    input.currentChampion == null &&
    input.record.recordKind === "local_evaluation" &&
    input.record.selectionPhase === "bootstrap" &&
    input.record.bootstrapSource === "local_compatible_seed" &&
    input.record.eligibility?.bootstrapEligible === true
  );
}

function selectBootstrapTransitionCandidate(input: {
  experiments: ExperimentRecord[];
  currentChampion: AutonomousExperimentRecord | null;
}): AutonomousExperimentRecord | null {
  if (input.currentChampion?.selectionPhase !== "bootstrap") {
    return null;
  }

  const localRecords = selectLocalEvaluationRecords(input.experiments);
  const bestSteadyStateCandidate = localRecords
    .filter(
      (record) =>
        record.candidateId !== input.currentChampion?.candidateId &&
        record.selectionPhase === "steady_state" &&
        record.eligibility?.autoSelectionEligible === true,
    )
    .sort(compareAutonomousChampion)[0];

  if (!bestSteadyStateCandidate) {
    return null;
  }

  return bestSteadyStateCandidate;
}

function getChampionScore(record: AutonomousExperimentRecord): number {
  return (
    record.verifiedPromotionScore ??
    record.verifiedPromotion?.score ??
    record.autoSelectionScore ??
    Number.NEGATIVE_INFINITY
  );
}

function filterSuppressedFamilyExperiments(
  experiments: ExperimentRecord[],
  suppressedFamilies: string[],
): ExperimentRecord[] {
  if (suppressedFamilies.length === 0) {
    return experiments;
  }
  const suppressed = new Set(suppressedFamilies);
  return experiments.filter((record) => {
    const raw = record as Record<string, unknown>;
    const structureFamilyHash =
      typeof raw.structureFamilyHash === "string" ? raw.structureFamilyHash : null;
    const fingerprintFamily =
      typeof raw.fingerprintFamily === "string" ? raw.fingerprintFamily : null;
    return !(
      (structureFamilyHash && suppressed.has(structureFamilyHash)) ||
      (fingerprintFamily && suppressed.has(fingerprintFamily))
    );
  });
}
