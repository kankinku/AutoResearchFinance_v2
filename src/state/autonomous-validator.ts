import path from "node:path";

import {
  archiveEventRecordSchema,
  calibrationEventRecordSchema,
  headEventRecordSchema,
  localConfidenceEventRecordSchema,
} from "../contracts/autonomous.js";
import { type ExperimentRecord } from "../contracts/types.js";
import { readJson, scanJsonlTolerant } from "../utils/fs.js";
import {
  readExperimentRecords,
  readLocalConfidenceEventRecords,
  readProblemEventRecords,
  readRepairAttemptRecords,
  readAutonomousBranchRecords,
  resolveStatePaths,
} from "./jsonl-store.js";
import { buildAutonomousViewPayloads } from "./autonomous-index-builder.js";
import { findActiveChampionRecord, selectAutonomousExperimentRecords } from "./autonomous-state.js";
import type { LedgerValidationIssue } from "./ledger-validator.js";

export async function validateAutonomousLedger(stateRoot: string): Promise<LedgerValidationIssue[]> {
  const issues: LedgerValidationIssue[] = [];
  const paths = resolveStatePaths(stateRoot);

  const headEventsResult = await readAutonomousLedgerRecords(
    paths.headEventsPath,
    headEventRecordSchema,
    "head-events",
  );
  const archiveEventsResult = await readAutonomousLedgerRecords(
    paths.archiveEventsPath,
    archiveEventRecordSchema,
    "archive-events",
  );
  const calibrationEventsResult = await readAutonomousLedgerRecords(
    paths.calibrationEventsPath,
    calibrationEventRecordSchema,
    "calibration-events",
  );
  const confidenceEventsResult = await readAutonomousLedgerRecords(
    paths.localConfidenceEventsPath,
    localConfidenceEventRecordSchema,
    "local-confidence-events",
  );

  issues.push(...headEventsResult.issues);
  issues.push(...archiveEventsResult.issues);
  issues.push(...calibrationEventsResult.issues);
  issues.push(...confidenceEventsResult.issues);

  let experiments: ExperimentRecord[];
  try {
    experiments = await readExperimentRecords(stateRoot);
  } catch {
    return issues;
  }
  const localRecords = selectAutonomousExperimentRecords(experiments);
  for (const record of localRecords) {
    if (
      record.recordKind === "local_evaluation" &&
      (record.decision === "tv_surface_failure" ||
        record.decision === "tv_executor_failure")
    ) {
      issues.push({
        severity: "error",
        scope: "autonomous",
        message:
          "External runtime failures must not be stored as local_evaluation records.",
        recordId: record.candidateId,
      });
    }
    if (
      record.recordKind === "local_evaluation" &&
      record.decision === "local_candidate_eligible" &&
      record.autoSelectionBreakdown?.eligible !== true
    ) {
      issues.push({
        severity: "error",
        scope: "autonomous",
        message: "local_candidate_eligible records must have autoSelectionBreakdown.eligible=true.",
        recordId: record.candidateId,
      });
    }
    if (
      record.recordKind === "local_evaluation" &&
      record.duplicateStatus?.classification !== "unique" &&
      record.autoSelectionBreakdown?.eligible === true
    ) {
      issues.push({
        severity: "error",
        scope: "autonomous",
        message: "Duplicate local evaluation records cannot be auto-selection eligible.",
        recordId: record.candidateId,
      });
    }
  }

  const activeChampion = findActiveChampionRecord({
    records: experiments,
    headEvents: headEventsResult.records,
  });
  if (activeChampion) {
    if (
      activeChampion.recordKind === "local_evaluation" &&
      (activeChampion.selectionPhase !== "bootstrap" ||
        activeChampion.bootstrapSource !== "local_compatible_seed" ||
        activeChampion.eligibility?.bootstrapEligible !== true)
    ) {
      issues.push({
        severity: "error",
        scope: "autonomous",
        message:
          "Local active champion records are only valid as local-compatible bootstrap seeds.",
        recordId: activeChampion.candidateId,
      });
    }
  }

  for (const event of calibrationEventsResult.records) {
    if (
      event.eventKind === "calibration_candidate_added" &&
      !localRecords.some(
        (record) =>
          record.recordKind === "local_evaluation" &&
          record.candidateId === event.candidateId,
      )
    ) {
      issues.push({
        severity: "warning",
        scope: "autonomous",
        message: "Calibration queue entry points to a candidate without a local evaluation record.",
        recordId: event.candidateId,
      });
    }
  }

  return issues;
}

export async function verifyAutonomousDerivedViews(
  stateRoot: string,
): Promise<LedgerValidationIssue[]> {
  const paths = resolveStatePaths(stateRoot);
  const issues: LedgerValidationIssue[] = [];
  let experiments: ExperimentRecord[];
  try {
    experiments = await readExperimentRecords(stateRoot);
  } catch {
    return issues;
  }
  const headEventsResult = await readAutonomousLedgerRecords(
    paths.headEventsPath,
    headEventRecordSchema,
    "head-events",
  );
  const archiveEventsResult = await readAutonomousLedgerRecords(
    paths.archiveEventsPath,
    archiveEventRecordSchema,
    "archive-events",
  );
  const calibrationEventsResult = await readAutonomousLedgerRecords(
    paths.calibrationEventsPath,
    calibrationEventRecordSchema,
    "calibration-events",
  );
  const confidenceEventsResult = await readAutonomousLedgerRecords(
    paths.localConfidenceEventsPath,
    localConfidenceEventRecordSchema,
    "local-confidence-events",
  );
  const problemEvents = await readProblemEventRecords(stateRoot);
  const confidenceEvents = await readLocalConfidenceEventRecords(stateRoot);
  const repairAttempts = await readRepairAttemptRecords(stateRoot);
  const branchRecords = await readAutonomousBranchRecords(stateRoot);
  const expected = buildAutonomousViewPayloads({
    experiments,
    headEvents: headEventsResult.records,
    archiveEvents: archiveEventsResult.records,
    calibrationEvents: calibrationEventsResult.records,
    confidenceEvents,
    problemEvents,
    repairAttempts,
    branchRecords,
  });

  const comparisons: Array<{
    scope: string;
    filePath: string;
    expected: unknown;
  }> = [
    {
      scope: "local-leaderboard",
      filePath: paths.localLeaderboardPath,
      expected: expected.localLeaderboard,
    },
    {
      scope: "champion-history",
      filePath: paths.championHistoryPath,
      expected: expected.championHistory,
    },
    {
      scope: "exploration-archive",
      filePath: paths.explorationArchivePath,
      expected: expected.explorationArchive,
    },
    {
      scope: "novelty-frontier",
      filePath: paths.noveltyFrontierPath,
      expected: expected.noveltyFrontier,
    },
    {
      scope: "robustness-frontier",
      filePath: paths.robustnessFrontierPath,
      expected: expected.robustnessFrontier,
    },
    {
      scope: "tv-surface-failures",
      filePath: paths.tvSurfaceFailuresPath,
      expected: expected.tvSurfaceFailures,
    },
    {
      scope: "local-promotion-queue",
      filePath: paths.tvCalibrationQueuePath,
      expected: expected.tvCalibrationQueue,
    },
    {
      scope: "local-tv-divergence",
      filePath: paths.localTvDivergencePath,
      expected: expected.localTvDivergence,
    },
    {
      scope: "auto-selection-decisions",
      filePath: paths.autoSelectionDecisionsPath,
      expected: expected.autoSelectionDecisions,
    },
    {
      scope: "duplicate-candidates",
      filePath: paths.duplicateCandidatesPath,
      expected: expected.duplicateCandidates,
    },
    {
      scope: "local-compatibility-summary",
      filePath: paths.localCompatibilitySummaryPath,
      expected: expected.localCompatibilitySummary,
    },
    {
      scope: "autonomous-state-summary",
      filePath: paths.autonomousStateSummaryPath,
      expected: expected.autonomousStateSummary,
    },
    {
      scope: "local-confidence-summary",
      filePath: paths.localConfidenceSummaryPath,
      expected: expected.localConfidenceSummary,
    },
    {
      scope: "failure-memory",
      filePath: paths.failureMemoryPath,
      expected: expected.failureMemory,
    },
    {
      scope: "branch-budget",
      filePath: path.join(path.dirname(paths.localLeaderboardPath), "autonomous", "branch-budget.json"),
      expected: expected.branchBudget,
    },
    {
      scope: "verified-promotion-readiness",
      filePath: path.join(
        path.dirname(paths.localLeaderboardPath),
        "autonomous",
        "verified-promotion-readiness.json",
      ),
      expected: expected.verifiedPromotionReadiness,
    },
  ];
  const autonomousDir = path.join(path.dirname(paths.localLeaderboardPath), "autonomous");
  comparisons.push(
    {
      scope: "autonomous/local-leaderboard",
      filePath: path.join(autonomousDir, "local-leaderboard.json"),
      expected: expected.localLeaderboard,
    },
    {
      scope: "autonomous/champion-history",
      filePath: path.join(autonomousDir, "champion-history.json"),
      expected: expected.championHistory,
    },
    {
      scope: "autonomous/exploration-archive",
      filePath: path.join(autonomousDir, "exploration-archive.json"),
      expected: expected.explorationArchive,
    },
    {
      scope: "autonomous/novelty-frontier",
      filePath: path.join(autonomousDir, "novelty-frontier.json"),
      expected: expected.noveltyFrontier,
    },
    {
      scope: "autonomous/robustness-frontier",
      filePath: path.join(autonomousDir, "robustness-frontier.json"),
      expected: expected.robustnessFrontier,
    },
    {
      scope: "autonomous/tv-surface-failures",
      filePath: path.join(autonomousDir, "tv-surface-failures.json"),
      expected: expected.tvSurfaceFailures,
    },
    {
      scope: "autonomous/local-promotion-queue",
      filePath: path.join(autonomousDir, "local-promotion-queue.json"),
      expected: expected.tvCalibrationQueue,
    },
    {
      scope: "autonomous/local-tv-divergence",
      filePath: path.join(autonomousDir, "local-tv-divergence.json"),
      expected: expected.localTvDivergence,
    },
    {
      scope: "autonomous/auto-selection-decisions",
      filePath: path.join(autonomousDir, "auto-selection-decisions.json"),
      expected: expected.autoSelectionDecisions,
    },
    {
      scope: "autonomous/duplicate-candidates",
      filePath: path.join(autonomousDir, "duplicate-candidates.json"),
      expected: expected.duplicateCandidates,
    },
    {
      scope: "autonomous/local-compatibility-summary",
      filePath: path.join(autonomousDir, "local-compatibility-summary.json"),
      expected: expected.localCompatibilitySummary,
    },
    {
      scope: "autonomous/autonomous-state-summary",
      filePath: path.join(autonomousDir, "autonomous-state-summary.json"),
      expected: expected.autonomousStateSummary,
    },
    {
      scope: "autonomous/local-confidence-summary",
      filePath: path.join(autonomousDir, "local-confidence-summary.json"),
      expected: expected.localConfidenceSummary,
    },
    {
      scope: "autonomous/failure-memory",
      filePath: path.join(autonomousDir, "failure-memory.json"),
      expected: expected.failureMemory,
    },
  );

  issues.push(...headEventsResult.issues);
  issues.push(...archiveEventsResult.issues);
  issues.push(...calibrationEventsResult.issues);
  issues.push(...confidenceEventsResult.issues);
  for (const comparison of comparisons) {
    const actual = await readJson<unknown>(comparison.filePath).catch(() => null);
    if (actual == null) {
      issues.push({
        severity: "error",
        scope: comparison.scope,
        message: "Derived autonomous view is missing.",
        filePath: comparison.filePath,
      });
      continue;
    }

    if (
      JSON.stringify(stripGeneratedAt(actual)) !==
      JSON.stringify(stripGeneratedAt(comparison.expected))
    ) {
      issues.push({
        severity: "error",
        scope: comparison.scope,
        message: "Derived autonomous view does not match ledger-derived expectations.",
        filePath: comparison.filePath,
      });
    }
  }

  return issues;
}

async function readAutonomousLedgerRecords<T>(
  filePath: string,
  schema: {
    safeParse: (
      value: unknown,
    ) => { success: boolean; data?: T; error?: { message: string } };
  },
  scope: string,
): Promise<{
  records: T[];
  issues: LedgerValidationIssue[];
}> {
  const scanned = await scanJsonlTolerant(filePath, (parsed) => {
    const result = schema.safeParse(parsed);
    if (result.success) {
      return {
        success: true as const,
        record: result.data ?? (parsed as T),
      };
    }

    return {
      success: false as const,
      message: result.error?.message ?? "schema_error",
      kind: "schema_error" as const,
    };
  });

  return {
    records: scanned.records,
    issues: scanned.issues.map((issue) => ({
      severity: "error",
      scope,
      message: issue.message,
      filePath,
      lineNumber: issue.lineNumber,
      rawLinePreview: issue.rawLinePreview,
      kind: issue.kind,
    })),
  };
}

function stripGeneratedAt(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(stripGeneratedAt);
  }
  if (value && typeof value === "object") {
    const output: Record<string, unknown> = {};
    for (const [key, child] of Object.entries(value)) {
      if (key === "generatedAt") {
        continue;
      }
      output[key] = stripGeneratedAt(child);
    }
    return output;
  }
  return value;
}
