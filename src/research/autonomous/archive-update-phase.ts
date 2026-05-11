import { type AutonomousExperimentRecord } from "../../contracts/autonomous.js";
import { appendArchiveEventRecord } from "../../state/jsonl-store.js";

export async function runArchiveUpdatePhase(input: {
  stateRoot: string;
  runId: string;
  iteration: number;
  evaluation: AutonomousExperimentRecord;
  shouldArchive: boolean;
}): Promise<void> {
  const bootstrapArchive =
    input.evaluation.selectionPhase === "bootstrap" &&
    input.evaluation.eligibility?.bootstrapEligible === true;
  if (
    !input.shouldArchive &&
    !bootstrapArchive &&
    input.evaluation.decision === "local_candidate_eligible"
  ) {
    return;
  }

  if (input.shouldArchive || bootstrapArchive) {
    await appendArchiveEventRecord(input.stateRoot, {
      runId: input.runId,
      iteration: input.iteration,
      eventKind: "archive_added",
      candidateId: input.evaluation.candidateId,
      score: input.evaluation.autoSelectionScore,
      noveltyScore: input.evaluation.autoSelectionBreakdown?.noveltyScore ?? null,
      robustnessScore:
        input.evaluation.autoSelectionBreakdown?.robustnessScore ?? null,
      reason: buildArchiveReason({
        evaluation: input.evaluation,
        bootstrapArchive,
      }),
    });
  } else if ((input.evaluation.eligibility?.blockingReasons.length ?? 0) > 0) {
    await appendArchiveEventRecord(input.stateRoot, {
      runId: input.runId,
      iteration: input.iteration,
      eventKind: "failure_archive_added",
      candidateId: input.evaluation.candidateId,
      score: input.evaluation.autoSelectionScore,
      noveltyScore: input.evaluation.autoSelectionBreakdown?.noveltyScore ?? null,
      robustnessScore:
        input.evaluation.autoSelectionBreakdown?.robustnessScore ?? null,
      reason: input.evaluation.eligibility?.blockingReasons
        .map((reason) => `${reason.kind}:${reason.message}`)
        .join(" | ") ?? "Rejected local candidate captured for failure memory.",
    });
    return;
  }

  if ((input.evaluation.autoSelectionBreakdown?.noveltyScore ?? 0) >= 0.15) {
    await appendArchiveEventRecord(input.stateRoot, {
      runId: input.runId,
      iteration: input.iteration,
      eventKind: "novelty_frontier_added",
      candidateId: input.evaluation.candidateId,
      score: input.evaluation.autoSelectionScore,
      noveltyScore: input.evaluation.autoSelectionBreakdown?.noveltyScore ?? null,
      robustnessScore:
        input.evaluation.autoSelectionBreakdown?.robustnessScore ?? null,
      reason: "Novelty score crossed the frontier threshold.",
    });
  }

  if (
    input.shouldArchive &&
    input.evaluation.splitEvaluation?.oosPassed &&
    (input.evaluation.autoSelectionBreakdown?.robustnessScore ?? 0) >= 0.1
  ) {
    await appendArchiveEventRecord(input.stateRoot, {
      runId: input.runId,
      iteration: input.iteration,
      eventKind: "robustness_frontier_added",
      candidateId: input.evaluation.candidateId,
      score: input.evaluation.autoSelectionScore,
      noveltyScore: input.evaluation.autoSelectionBreakdown?.noveltyScore ?? null,
      robustnessScore:
        input.evaluation.autoSelectionBreakdown?.robustnessScore ?? null,
      reason: "Out-of-sample gate passed with robustness frontier score.",
    });
  }
}

function buildArchiveReason(input: {
  evaluation: AutonomousExperimentRecord;
  bootstrapArchive: boolean;
}): string {
  if (input.bootstrapArchive) {
    return "bootstrap local-compatible seed established the first fresh research baseline archive candidate.";
  }

  if (input.evaluation.autoSelectionBreakdown?.eligible === true) {
    return "local hard gates passed with complete local artifact evidence.";
  }

  const breakdown = input.evaluation.autoSelectionBreakdown;
  const blockingReasons =
    input.evaluation.eligibility?.blockingReasons
      .map((reason) => reason.kind)
      .join(", ") || "unknown";
  return [
    "specialist candidate retained despite promotion blockers",
    `score=${formatScore(input.evaluation.autoSelectionScore ?? breakdown?.totalScore)}`,
    `performance=${formatScore(breakdown?.performanceScore ?? breakdown?.baseObjectiveScore)}`,
    `novelty=${formatScore(breakdown?.noveltyScore)}`,
    `robustness=${formatScore(breakdown?.robustnessScore)}`,
    `blocking=${blockingReasons}`,
  ].join(" | ");
}

function formatScore(score: number | null | undefined): string {
  return typeof score === "number" && Number.isFinite(score)
    ? score.toFixed(4)
    : "n/a";
}
