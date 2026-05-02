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
  buildSelectionEvidenceHash,
  compareAutonomousChampion,
  compareVerifiedPromotionCandidate,
  findActiveChampionRecord,
  isVerifiedPromotionEligible,
  selectLocalEvaluationRecords,
  selectBestChampionCandidate,
  selectTvVerificationRecords,
} from "../../state/autonomous-state.js";

export async function runAutoSelectionPhase(input: {
  stateRoot: string;
  runId: string;
  iteration: number;
  experiments: ExperimentRecord[];
  headEvents?: HeadEventRecord[];
}): Promise<{
  activeChampionChanged: boolean;
  selectedCandidateId: string | null;
}> {
  const headEvents = input.headEvents ?? (await readHeadEventRecords(input.stateRoot));
  const currentChampion = findActiveChampionRecord({
    records: input.experiments,
    headEvents,
  });
  const bootstrapTransitionCandidate = selectBootstrapTransitionCandidate({
    experiments: input.experiments,
    currentChampion,
  });
  const bootstrapTransitionApplied = bootstrapTransitionCandidate != null;
  const bestCandidate =
    bootstrapTransitionCandidate ??
    selectBestChampionCandidate(input.experiments) ??
    (!currentChampion
      ? [...selectLocalEvaluationRecords(input.experiments)]
          .filter((record) => record.eligibility?.bootstrapEligible === true)
          .sort(compareAutonomousChampion)[0] ?? null
      : null);
  const localRecords = selectLocalEvaluationRecords(input.experiments);
  if (
    !bestCandidate ||
    (!isVerifiedPromotionEligible({ record: bestCandidate, localRecords }) &&
      bestCandidate.eligibility?.bootstrapEligible !== true)
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
        ? "TradingView-verified candidate displaced the bootstrap baseline champion."
        : "Highest eligible verified promotion score displaced the current champion."
      : bestCandidate.selectionPhase === "bootstrap"
        ? "Bootstrap local-compatible seed established the first autonomous research baseline champion."
        : "First TradingView-verified autonomous candidate became the active champion.",
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

function selectBootstrapTransitionCandidate(input: {
  experiments: ExperimentRecord[];
  currentChampion: AutonomousExperimentRecord | null;
}): AutonomousExperimentRecord | null {
  if (input.currentChampion?.selectionPhase !== "bootstrap") {
    return null;
  }

  const localRecords = selectLocalEvaluationRecords(input.experiments);
  const bestSteadyStateCandidate = selectTvVerificationRecords(input.experiments)
    .filter(
      (record) =>
        record.candidateId !== input.currentChampion?.candidateId &&
        record.selectionPhase === "steady_state" &&
        isVerifiedPromotionEligible({ record, localRecords }),
    )
    .sort(compareVerifiedPromotionCandidate)[0];

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
