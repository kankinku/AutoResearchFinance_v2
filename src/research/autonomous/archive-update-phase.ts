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
      reason: bootstrapArchive
        ? "bootstrap local-compatible seed established the first fresh research baseline archive candidate."
        : "local hard gates passed with complete local artifact evidence.",
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
