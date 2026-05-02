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
  findActiveChampionRecord,
  isAutoSelectionEligible,
  selectLocalEvaluationRecords,
  selectBestAutonomousChampionCandidate,
} from "../../state/autonomous-state.js";

const BOOTSTRAP_TRANSITION_MAX_SCORE_DELTA = 0.15;

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
    selectBestAutonomousChampionCandidate(input.experiments) ??
    (!currentChampion
      ? [...selectLocalEvaluationRecords(input.experiments)]
          .filter((record) => record.eligibility?.bootstrapEligible === true)
          .sort(compareAutonomousChampion)[0] ?? null
      : null);
  if (
    !bestCandidate ||
    (!isAutoSelectionEligible(bestCandidate) &&
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
    (currentChampion.autoSelectionScore ?? Number.NEGATIVE_INFINITY) >=
      (bestCandidate.autoSelectionScore ?? Number.NEGATIVE_INFINITY)
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
      bestCandidate.autoSelectionBreakdown?.performanceScore ??
      bestCandidate.autoSelectionBreakdown?.baseObjectiveScore ??
      null,
    objectiveScore: bestCandidate.autoSelectionBreakdown?.baseObjectiveScore ?? null,
    noveltyScore: bestCandidate.autoSelectionBreakdown?.noveltyScore ?? null,
    robustnessScore: bestCandidate.autoSelectionBreakdown?.robustnessScore ?? null,
    autoSelectionScore: bestCandidate.autoSelectionScore ?? null,
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
        ? "Steady-state eligible candidate displaced the bootstrap baseline champion to advance autonomous research beyond the seed scaffold."
        : "Highest eligible autonomous selection score displaced the current champion."
      : bestCandidate.selectionPhase === "bootstrap"
        ? "Bootstrap local-compatible seed established the first autonomous research baseline champion."
        : "First eligible local-first autonomous candidate became the active champion.",
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

  const bestSteadyStateCandidate = [...selectLocalEvaluationRecords(input.experiments)]
    .filter(
      (record) =>
        record.candidateId !== input.currentChampion?.candidateId &&
        record.selectionPhase === "steady_state" &&
        isAutoSelectionEligible(record),
    )
    .sort(compareAutonomousChampion)[0];

  if (!bestSteadyStateCandidate) {
    return null;
  }

  return shouldTransitionFromBootstrapChampion({
    currentChampion: input.currentChampion,
    challenger: bestSteadyStateCandidate,
  })
    ? bestSteadyStateCandidate
    : null;
}

function shouldTransitionFromBootstrapChampion(input: {
  currentChampion: AutonomousExperimentRecord;
  challenger: AutonomousExperimentRecord;
}): boolean {
  const currentScore =
    input.currentChampion.autoSelectionScore ?? Number.NEGATIVE_INFINITY;
  const challengerScore =
    input.challenger.autoSelectionScore ?? Number.NEGATIVE_INFINITY;
  if (!Number.isFinite(challengerScore)) {
    return false;
  }

  if (!Number.isFinite(currentScore) || challengerScore >= currentScore) {
    return true;
  }

  const scoreDelta = currentScore - challengerScore;
  if (scoreDelta <= BOOTSTRAP_TRANSITION_MAX_SCORE_DELTA) {
    return true;
  }

  const challengerConfidenceBonus =
    input.challenger.autoSelectionBreakdown?.localConfidenceBonus ?? 0;
  return (
    challengerConfidenceBonus > 0 &&
    scoreDelta <= BOOTSTRAP_TRANSITION_MAX_SCORE_DELTA * 1.5
  );
}
