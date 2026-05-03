import { readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

import {
  type BacktestMetrics,
  type CandidateLedgerRecord,
  type ExperimentRecord,
  type MutationBriefRecord,
} from "../contracts/types.js";
import {
  type ProblemEventRecord,
  type RepairAttemptRecord,
} from "../contracts/autonomous.js";
import { resolveStatePaths } from "../state/jsonl-store.js";
import { fileExists, readJson, readJsonlTail } from "../utils/fs.js";

export interface DashboardStatusPayload {
  generatedAt: string;
  project: {
    workspaceRoot: string;
    stateRoot: string;
    localOnly: true;
  };
  operatorBrief: {
    mode: "local_only" | "external_auto";
    headline: string;
    summary: string;
    evidence: DashboardEvidenceItem[];
    nextActions: string[];
    warnings: string[];
    commands: DashboardCommandHint[];
  };
  runtime: {
    heartbeat: Record<string, unknown> | null;
    nodeMemory: Record<string, unknown> | null;
    running: boolean;
    stopRequested: boolean;
    pid: number | null;
    logFile: string | null;
  };
  score: {
    latest: DashboardCandidatePoint | null;
    activeChampion: DashboardLeaderboardEntry | null;
    bestEligible: DashboardLeaderboardEntry | null;
    bestOverall: DashboardLeaderboardEntry | null;
    latestEligibleStreak: number;
    recentEligibleCount: number;
    recentSparseProblemCount: number;
    recentPreflightRepairCount: number;
    ledgerSizeMB: number;
    artifactSizeMB: number;
  };
  trend: DashboardCandidatePoint[];
  recentCandidates: DashboardCandidatePoint[];
  bestStrategy: DashboardStrategyAnalysis | null;
  hypothesis: DashboardHypothesis | null;
  improvement: {
    status: "improving" | "watch" | "blocked";
    summary: string;
    nextFocus: string[];
  };
  verifiedAutoresearch: {
    researchStageCounts: Record<string, number>;
    quarantineCount: number;
    verifiedPromotionCandidateId: string | null;
    verifiedPromotionScore: number | null;
    parityStatus: string | null;
    parityStatusCounts: Record<string, number>;
    walkForwardStatus: string | null;
    walkForwardStatusCounts: Record<string, number>;
    trialPressure: Record<string, unknown> | null;
    branchBudget: Record<string, unknown> | null;
  };
  externalValidation: {
    autoProcessCalibration: boolean;
    promotionVerificationExecutor: string;
    pendingCount: number;
    pendingCandidateIds: string[];
    recentEvents: DashboardExternalValidationEvent[];
    latestDivergence: DashboardExternalDivergence | null;
  };
  failureMemory: {
    recentProblems: DashboardProblem[];
    recentRepairs: DashboardRepair[];
  };
}

export interface DashboardEvidenceItem {
  label: string;
  value: string;
  status: "good" | "watch" | "bad" | "neutral";
}

export interface DashboardCommandHint {
  label: string;
  command: string;
}

export interface DashboardCandidatePoint {
  iteration: number;
  candidateId: string;
  decision: string;
  recordedAt: string | null;
  score: number | null;
  eligible: boolean;
  metrics: DashboardMetrics | null;
}

export interface DashboardMetrics {
  netProfitPercent: number;
  profitFactor: number;
  maxDrawdownPercent: number;
  percentProfitable: number;
  totalTrades: number;
  avgTradePercent: number;
}

export interface DashboardLeaderboardEntry {
  candidateId: string;
  score: number | null;
  autoSelectionScore: number | null;
  performanceScore: number | null;
  noveltyScore: number | null;
  robustnessScore: number | null;
  decision: string | null;
  iteration: number | null;
  rank: number | null;
}

export interface DashboardStrategyAnalysis {
  candidateId: string;
  title: string | null;
  summary: string | null;
  sourcePath: string | null;
  routeInputs: Record<string, number | null>;
  features: string[];
  entryShape: string;
  exitShape: string;
  riskShape: string;
}

export interface DashboardHypothesis {
  hypothesis: string;
  expectedEffect: string;
  invalidIf: string;
  nextMutationDirection: string;
  repairMode: string;
  route: {
    preferred: string[];
    suppressed: string[];
    sparsePatterns: string[];
    variant: string | null;
    escalationLevel: number | null;
  };
}

export interface DashboardProblem {
  iteration: number | null;
  candidateId: string | null;
  problemKind: string;
  diagnosis: string;
  suggestedRepairKind: string | null;
  recordedAt: string | null;
}

export interface DashboardRepair {
  iteration: number | null;
  candidateId: string | null;
  repairedCandidateId: string | null;
  repairKind: string;
  result: string;
  summary: string;
  recordedAt: string | null;
}

export interface DashboardExternalValidationEvent {
  candidateId: string;
  status: string;
  reason: string | null;
  parityStatus: string | null;
  tvDecision: string | null;
  recordedAt: string | null;
}

export interface DashboardExternalDivergence {
  candidateId: string;
  parityStatus: string;
  netProfitDelta: number | null;
  tradeCountDelta: number | null;
  confidenceAfter: number | null;
  recordedAt: string | null;
}

interface DashboardBuildInput {
  workspaceRoot: string;
  stateRoot: string;
  now?: Date;
  autoProcessCalibration?: boolean;
  promotionVerificationExecutor?: string;
}

interface LocalLeaderboardView {
  entries?: Array<Record<string, unknown>>;
}

interface ExplorationArchiveView {
  entries?: Array<Record<string, unknown>>;
}

interface TvCalibrationQueueView {
  entries?: Array<Record<string, unknown>>;
}

interface LocalTvDivergenceView {
  entries?: Array<Record<string, unknown>>;
}

export async function buildDashboardStatus(
  input: DashboardBuildInput,
): Promise<DashboardStatusPayload> {
  const now = input.now ?? new Date();
  const paths = resolveStatePaths(input.stateRoot);
  const runtimeDir = path.join(input.stateRoot, "runtime");
  const [
    recentExperiments,
    candidates,
    mutationBriefs,
    problemEvents,
    repairAttempts,
    localLeaderboard,
    explorationArchive,
    heartbeat,
    nodeMemory,
    autonomousSummary,
    tvCalibrationQueue,
    localTvDivergence,
    ledgerBytes,
    artifactBytes,
  ] = await Promise.all([
    readJsonlTail<ExperimentRecord>(paths.experimentsPath, 48, 16 * 1024 * 1024),
    readJsonlTail<CandidateLedgerRecord>(paths.candidatesPath, 200, 8 * 1024 * 1024),
    readJsonlTail<MutationBriefRecord>(paths.mutationBriefsPath, 60, 8 * 1024 * 1024),
    readJsonlTail<ProblemEventRecord>(paths.problemEventsPath, 120, 8 * 1024 * 1024),
    readJsonlTail<RepairAttemptRecord>(paths.repairAttemptsPath, 120, 8 * 1024 * 1024),
    readJsonSafe<LocalLeaderboardView>(paths.localLeaderboardPath),
    readJsonSafe<ExplorationArchiveView>(paths.explorationArchivePath),
    readJsonSafe<Record<string, unknown>>(path.join(runtimeDir, "autonomous-loop-heartbeat.json")),
    readJsonSafe<Record<string, unknown>>(path.join(runtimeDir, "node-memory-telemetry.json")),
    readJsonSafe<Record<string, unknown>>(paths.autonomousStateSummaryPath),
    readJsonSafe<TvCalibrationQueueView>(paths.tvCalibrationQueuePath),
    readJsonSafe<LocalTvDivergenceView>(paths.localTvDivergencePath),
    getFileSize(paths.experimentsPath),
    getDirectorySize(path.join(input.stateRoot, "artifacts")),
  ]);

  const stopRequested = await fileExists(
    path.join(runtimeDir, "STOP_AUTONOMOUS_LOOP"),
  );
  const pid = numberValue(heartbeat?.pid) ?? null;
  const recentCandidatePoints = recentExperiments
    .map(toCandidatePoint)
    .filter((point): point is DashboardCandidatePoint => point != null)
    .sort((a, b) => a.iteration - b.iteration);
  const archiveTrend = buildArchiveTrend(explorationArchive);
  const trend = recentCandidatePoints.length >= 6
    ? recentCandidatePoints.slice(-40)
    : archiveTrend.slice(-40);
  const latest = [...recentCandidatePoints].reverse().find(
    (point) => point.metrics != null || point.score != null,
  ) ?? null;
  const activeChampion = buildActiveChampion(autonomousSummary);
  const bestOverall = buildLeaderboardEntry(
    localLeaderboard?.entries?.[0],
  );
  const bestEligible = findBestEligible({
    localLeaderboard,
    explorationArchive,
    activeChampion,
  });
  const candidateById = new Map(candidates.map((candidate) => [candidate.candidateId, candidate]));
  const strategyCandidateId =
    bestEligible?.candidateId ??
    activeChampion?.candidateId ??
    bestOverall?.candidateId ??
    latest?.candidateId ??
    null;
  const latestBrief = mutationBriefs.at(-1) ?? null;
  const recentProblems = problemEvents.slice(-12).map(toDashboardProblem);
  const recentRepairs = repairAttempts.slice(-10).map(toDashboardRepair);
  const recentSparseProblemCount = problemEvents
    .slice(-20)
    .filter((event) => isSparseTradeDiagnosis(event.diagnosis)).length;
  const recentPreflightRepairCount = repairAttempts
    .slice(-20)
    .filter((attempt) =>
      attempt.repairKind === "pine_source_repair" &&
      /deterministic time-boxed preflight repair/i.test(attempt.summary),
    ).length;
  const recentEligibleCount = recentCandidatePoints
    .slice(-10)
    .filter((point) => point.eligible).length;
  const latestEligibleStreak = countLatestEligibleStreak(recentCandidatePoints);
  const improvement = buildImprovementStatus({
    recentCandidatePoints,
    recentSparseProblemCount,
    recentPreflightRepairCount,
    latest,
  });
  const runtime = {
    heartbeat: heartbeat ?? null,
    nodeMemory: nodeMemory ?? null,
    running: pid != null && isPidAlive(pid),
    stopRequested,
    pid,
    logFile: stringValue(heartbeat?.logFile),
  };
  const externalValidation = buildExternalValidationDashboard({
    autoProcessCalibration:
      input.autoProcessCalibration ??
      booleanValue(autonomousSummary?.calibrationAutoProcess) ??
      false,
    promotionVerificationExecutor:
      input.promotionVerificationExecutor ??
      stringValue(autonomousSummary?.promotionVerificationExecutor) ??
      "none",
    tvCalibrationQueue,
    localTvDivergence,
  });
  const operatorBrief = buildOperatorBrief({
    runtime,
    improvement,
    latest,
    bestEligible,
    activeChampion,
    externalValidation,
  });

  return {
    generatedAt: now.toISOString(),
    project: {
      workspaceRoot: input.workspaceRoot,
      stateRoot: input.stateRoot,
      localOnly: true,
    },
    operatorBrief,
    runtime,
    score: {
      latest,
      activeChampion,
      bestEligible,
      bestOverall,
      latestEligibleStreak,
      recentEligibleCount,
      recentSparseProblemCount,
      recentPreflightRepairCount,
      ledgerSizeMB: roundMb(ledgerBytes),
      artifactSizeMB: roundMb(artifactBytes),
    },
    trend,
    recentCandidates: recentCandidatePoints.slice(-12).reverse(),
    bestStrategy: strategyCandidateId
      ? await analyzeStrategyCandidate({
          workspaceRoot: input.workspaceRoot,
          candidateId: strategyCandidateId,
          candidateRecord: candidateById.get(strategyCandidateId) ?? null,
        })
      : null,
    hypothesis: latestBrief ? toDashboardHypothesis(latestBrief) : null,
    improvement,
    verifiedAutoresearch: buildVerifiedAutoresearchDashboard(autonomousSummary),
    externalValidation,
    failureMemory: {
      recentProblems,
      recentRepairs,
    },
  };
}

function buildExternalValidationDashboard(input: {
  autoProcessCalibration: boolean;
  promotionVerificationExecutor: string;
  tvCalibrationQueue: TvCalibrationQueueView | null;
  localTvDivergence: LocalTvDivergenceView | null;
}): DashboardStatusPayload["externalValidation"] {
  const queueEntries = [...(input.tvCalibrationQueue?.entries ?? [])].sort(
    compareRecordedAtAscending,
  );
  const pendingEntries = queueEntries.filter((entry) => {
    const status = stringValue(entry.derivedStatus) ?? stringValue(entry.queueState);
    return status === "pending" || status === "deferred" || status === "queued";
  });
  const recentEvents = queueEntries.slice(-10).reverse().map((entry) => ({
    candidateId: stringValue(entry.candidateId) ?? "-",
    status: stringValue(entry.derivedStatus) ?? stringValue(entry.queueState) ?? "-",
    reason: stringValue(entry.queueReason),
    parityStatus: stringValue(recordValue(entry.parity)?.status),
    tvDecision: stringValue(entry.tvDecision),
    recordedAt: stringValue(entry.recordedAt),
  }));

  const divergenceEntries = [...(input.localTvDivergence?.entries ?? [])].sort(
    compareRecordedAtAscending,
  );
  const latestDivergenceEntry = [...divergenceEntries].reverse().find((entry) => {
    const status = stringValue(recordValue(entry.parity)?.status);
    return status === "major_drift" || status === "minor_drift";
  });
  const latestParity = recordValue(latestDivergenceEntry?.parity);
  return {
    autoProcessCalibration: input.autoProcessCalibration,
    promotionVerificationExecutor: input.promotionVerificationExecutor,
    pendingCount: pendingEntries.length,
    pendingCandidateIds: pendingEntries
      .map((entry) => stringValue(entry.candidateId))
      .filter((candidateId): candidateId is string => candidateId != null)
      .slice(-8),
    recentEvents,
    latestDivergence: latestDivergenceEntry && latestParity
      ? {
          candidateId: stringValue(latestDivergenceEntry.candidateId) ?? "-",
          parityStatus: stringValue(latestParity.status) ?? "-",
          netProfitDelta: numberValue(latestParity.netProfitPctDelta),
          tradeCountDelta: numberValue(latestParity.tradeCountDelta),
          confidenceAfter: numberValue(latestDivergenceEntry.localConfidenceAfter),
          recordedAt: stringValue(latestDivergenceEntry.recordedAt),
        }
      : null,
  };
}

function buildOperatorBrief(input: {
  runtime: DashboardStatusPayload["runtime"];
  improvement: DashboardStatusPayload["improvement"];
  latest: DashboardCandidatePoint | null;
  bestEligible: DashboardLeaderboardEntry | null;
  activeChampion: DashboardLeaderboardEntry | null;
  externalValidation: DashboardStatusPayload["externalValidation"];
}): DashboardStatusPayload["operatorBrief"] {
  const manualExternal =
    !input.externalValidation.autoProcessCalibration &&
    input.externalValidation.promotionVerificationExecutor === "none";
  const mode = manualExternal ? "local_only" : "external_auto";
  const latestScore = input.latest?.score == null ? "no score" : input.latest.score.toFixed(4);
  const bestScore = input.bestEligible?.score == null ? "no eligible score" : input.bestEligible.score.toFixed(4);
  const pending = input.externalValidation.pendingCount;
  const headline = manualExternal
    ? "Local research is active; TradingView is manual."
    : "External validation is enabled; watch TradingView surface health.";
  const summary = [
    input.runtime.running
      ? `Loop is running with latest local score ${latestScore}.`
      : input.runtime.stopRequested
        ? `Loop is stopped by request; latest local score is ${latestScore}.`
        : `Loop is not running; latest local score is ${latestScore}.`,
    `Best local eligible score is ${bestScore}.`,
    pending > 0
      ? `${pending} candidates are waiting for manual TV calibration.`
      : "No urgent manual TV calibration is pending.",
  ].join(" ");
  const warnings: string[] = [];
  if (input.improvement.status === "blocked") {
    warnings.push(input.improvement.summary);
  }
  if (input.externalValidation.latestDivergence?.parityStatus === "major_drift") {
    warnings.push(
      `Latest TV divergence was major_drift on ${input.externalValidation.latestDivergence.candidateId}.`,
    );
  }
  if (input.externalValidation.autoProcessCalibration) {
    warnings.push("TradingView queue auto-processing is enabled.");
  }

  return {
    mode,
    headline,
    summary,
    evidence: [
      {
        label: "Loop",
        value: input.runtime.running
          ? `running pid ${input.runtime.pid}`
          : input.runtime.stopRequested
            ? "stop requested"
            : "stopped",
        status: input.runtime.running ? "good" : input.runtime.stopRequested ? "watch" : "neutral",
      },
      {
        label: "Local trend",
        value: input.improvement.status,
        status:
          input.improvement.status === "improving"
            ? "good"
            : input.improvement.status === "blocked"
              ? "bad"
              : "watch",
      },
      {
        label: "Best local",
        value: input.bestEligible?.candidateId
          ? `${input.bestEligible.candidateId} / ${bestScore}`
          : "none",
        status: input.bestEligible ? "good" : "watch",
      },
      {
        label: "Active champion",
        value: input.activeChampion?.candidateId ?? "none",
        status: input.activeChampion ? "good" : "neutral",
      },
      {
        label: "TV mode",
        value: manualExternal ? "manual" : "auto-enabled",
        status: manualExternal ? "good" : "watch",
      },
      {
        label: "TV queue",
        value: `${pending} pending`,
        status: pending > 0 ? "watch" : "good",
      },
    ],
    nextActions: [
      ...input.improvement.nextFocus.slice(0, 2),
      pending > 0
        ? "When the local candidate set looks worth checking, run one manual TV calibration candidate."
        : "Let the local loop gather more evidence before spending attention on TradingView.",
    ],
    warnings,
    commands: [
      {
        label: "Local loop",
        command:
          "powershell -ExecutionPolicy Bypass -File scripts/run-autonomous-forever.ps1",
      },
      {
        label: "Inspect TV queue",
        command: "node dist/cli/index.js inspect-calibration-queue",
      },
      {
        label: "Manual TV check",
        command: "node dist/cli/index.js process-tv-calibration-queue --max-candidates 1",
      },
    ],
  };
}

function buildVerifiedAutoresearchDashboard(
  summary: Record<string, unknown> | null,
): DashboardStatusPayload["verifiedAutoresearch"] {
  return {
    researchStageCounts: recordNumberMap(summary?.researchStageCounts),
    quarantineCount: numberValue(summary?.quarantineCount) ?? 0,
    verifiedPromotionCandidateId: stringValue(summary?.verifiedPromotionCandidateId),
    verifiedPromotionScore: numberValue(summary?.verifiedPromotionScore),
    parityStatus: stringValue(summary?.parityStatus),
    parityStatusCounts: recordNumberMap(summary?.parityStatusCounts),
    walkForwardStatus: stringValue(summary?.walkForwardStatus),
    walkForwardStatusCounts: recordNumberMap(summary?.walkForwardStatusCounts),
    trialPressure: recordValue(summary?.trialPressure),
    branchBudget: recordValue(summary?.branchBudget),
  };
}

async function readJsonSafe<T>(filePath: string): Promise<T | null> {
  try {
    return await readJson<T>(filePath);
  } catch {
    return null;
  }
}

async function getFileSize(filePath: string): Promise<number> {
  try {
    return (await stat(filePath)).size;
  } catch {
    return 0;
  }
}

async function getDirectorySize(dirPath: string): Promise<number> {
  try {
    const entries = await readdir(dirPath, { withFileTypes: true });
    const sizes = await Promise.all(
      entries.map((entry) => {
        const entryPath = path.join(dirPath, entry.name);
        return entry.isDirectory() ? getDirectorySize(entryPath) : getFileSize(entryPath);
      }),
    );
    return sizes.reduce((sum, size) => sum + size, 0);
  } catch {
    return 0;
  }
}

function roundMb(bytes: number): number {
  return Math.round((bytes / 1024 / 1024) * 100) / 100;
}

function toCandidatePoint(record: ExperimentRecord): DashboardCandidatePoint | null {
  const score = numberValue(record.candidateScore ?? record.objectiveBreakdown?.score);
  const metrics = toDashboardMetrics(
    record.testerMetrics ??
      record.artifactSummary?.strategy ??
      record.artifactBundle?.strategy,
  );
  if (score == null && metrics == null) {
    return null;
  }

  return {
    iteration: record.iteration,
    candidateId: record.candidateId,
    decision: record.decision,
    recordedAt: record.recordedAt ?? null,
    score,
    eligible: record.decision === "local_candidate_eligible",
    metrics,
  };
}

function toDashboardMetrics(metrics: BacktestMetrics | null | undefined): DashboardMetrics | null {
  if (!metrics) {
    return null;
  }

  return {
    netProfitPercent: metrics.netProfitPercent,
    profitFactor: metrics.profitFactor,
    maxDrawdownPercent: metrics.maxStrategyDrawdownPercent,
    percentProfitable: metrics.percentProfitable,
    totalTrades: metrics.totalTrades,
    avgTradePercent: metrics.avgTradePercent,
  };
}

function buildArchiveTrend(view: ExplorationArchiveView | null): DashboardCandidatePoint[] {
  return (view?.entries ?? []).flatMap((entry) => {
    const candidateId = stringValue(entry.candidateId);
    const score = numberValue(entry.score);
    if (!candidateId || score == null) {
      return [];
    }

    return [{
      iteration: 0,
      candidateId,
      decision: "local_candidate_eligible",
      recordedAt: stringValue(entry.recordedAt),
      score,
      eligible: true,
      metrics: null,
    }];
  });
}

function buildActiveChampion(summary: Record<string, unknown> | null): DashboardLeaderboardEntry | null {
  if (!summary) {
    return null;
  }

  const candidateId = stringValue(summary.activeChampionCandidateId);
  if (!candidateId) {
    return null;
  }

  return {
    candidateId,
    score: numberValue(summary.activeChampionScore),
    autoSelectionScore: numberValue(summary.activeChampionScore),
    performanceScore: null,
    noveltyScore: null,
    robustnessScore: null,
    decision: stringValue(summary.activeChampionDecision),
    iteration: null,
    rank: null,
  };
}

function buildLeaderboardEntry(entry: Record<string, unknown> | undefined): DashboardLeaderboardEntry | null {
  if (!entry) {
    return null;
  }

  const candidateId = stringValue(entry.candidateId);
  if (!candidateId) {
    return null;
  }

  return {
    candidateId,
    score: numberValue(entry.autoSelectionScore ?? entry.score),
    autoSelectionScore: numberValue(entry.autoSelectionScore ?? entry.score),
    performanceScore: numberValue(entry.performanceScore),
    noveltyScore: numberValue(entry.noveltyScore),
    robustnessScore: numberValue(entry.robustnessScore),
    decision: stringValue(entry.decision),
    iteration: numberValue(entry.iteration),
    rank: numberValue(entry.rank),
  };
}

function findBestEligible(input: {
  localLeaderboard: LocalLeaderboardView | null;
  explorationArchive: ExplorationArchiveView | null;
  activeChampion: DashboardLeaderboardEntry | null;
}): DashboardLeaderboardEntry | null {
  const eligibleLeaderboard = (input.localLeaderboard?.entries ?? [])
    .filter((entry) =>
      entry.eligible === true ||
      entry.archiveEligible === true ||
      stringValue(entry.decision) === "local_candidate_eligible",
    )
    .map(buildLeaderboardEntry)
    .filter((entry): entry is DashboardLeaderboardEntry => entry != null);
  const archiveEntries = (input.explorationArchive?.entries ?? [])
    .map((entry) => ({
      candidateId: stringValue(entry.candidateId),
      score: numberValue(entry.score),
      noveltyScore: numberValue(entry.noveltyScore),
      robustnessScore: numberValue(entry.robustnessScore),
      recordedAt: stringValue(entry.recordedAt),
    }))
    .filter((entry): entry is {
      candidateId: string;
      score: number;
      noveltyScore: number | null;
      robustnessScore: number | null;
      recordedAt: string | null;
    } => entry.candidateId != null && entry.score != null)
    .map((entry) => ({
      candidateId: entry.candidateId,
      score: entry.score,
      autoSelectionScore: entry.score,
      performanceScore: null,
      noveltyScore: entry.noveltyScore,
      robustnessScore: entry.robustnessScore,
      decision: "local_candidate_eligible",
      iteration: null,
      rank: null,
    }));

  return [...eligibleLeaderboard, ...archiveEntries, ...(input.activeChampion ? [input.activeChampion] : [])]
    .sort((a, b) => (b.score ?? -Infinity) - (a.score ?? -Infinity))[0] ?? null;
}

async function analyzeStrategyCandidate(input: {
  workspaceRoot: string;
  candidateId: string;
  candidateRecord: CandidateLedgerRecord | null;
}): Promise<DashboardStrategyAnalysis | null> {
  const sourcePath =
    input.candidateRecord?.candidatePath ??
    path.join(input.workspaceRoot, "strategies", "candidates", `${input.candidateId}.pine`);
  let source: string;
  try {
    source = await readFile(sourcePath, "utf8");
  } catch {
    return {
      candidateId: input.candidateId,
      title: null,
      summary: input.candidateRecord?.candidateSummary ?? null,
      sourcePath,
      routeInputs: {},
      features: ["Source file is not available locally."],
      entryShape: "Unknown",
      exitShape: "Unknown",
      riskShape: "Unknown",
    };
  }

  const routeInputs = {
    eventFloorBars: extractNumericAssignment(source, "eventFloorBars"),
    eventWindowBars: extractNumericAssignment(source, "eventWindowBars") ??
      extractNumericAssignment(source, "entryWindowBars"),
    maxHoldBars: extractNumericAssignment(source, "maxHoldBars") ??
      extractNumericAssignment(source, "holdBars4"),
    bullContinueWindow: extractNumericAssignment(source, "bullContinueWindow"),
    bearReboundWindow: extractNumericAssignment(source, "bearReboundWindow"),
  };

  return {
    candidateId: input.candidateId,
    title: extractStrategyTitle(source),
    summary: input.candidateRecord?.candidateSummary ?? null,
    sourcePath,
    routeInputs,
    features: inferStrategyFeatures(source),
    entryShape: inferEntryShape(source),
    exitShape: inferExitShape(source),
    riskShape: inferRiskShape(source),
  };
}

function extractStrategyTitle(source: string): string | null {
  return source.match(/\bstrategy\s*\(\s*["']([^"']+)["']/i)?.[1] ?? null;
}

function extractNumericAssignment(source: string, name: string): number | null {
  const inputMatch = source.match(
    new RegExp(`\\b${escapeForRegex(name)}\\s*=\\s*input\\.(?:int|float)\\s*\\(\\s*(-?\\d+(?:\\.\\d+)?)`, "i"),
  );
  if (inputMatch?.[1]) {
    return Number.parseFloat(inputMatch[1]);
  }

  const constantMatch = source.match(
    new RegExp(`^\\s*(?:int\\s+|float\\s+)?${escapeForRegex(name)}\\s*=\\s*(-?\\d+(?:\\.\\d+)?)`, "im"),
  );
  return constantMatch?.[1] ? Number.parseFloat(constantMatch[1]) : null;
}

function inferStrategyFeatures(source: string): string[] {
  const features: string[] = [];
  if (/\beventFloorBars\b|\bearlyBullEvent\b/i.test(source)) {
    features.push("dense event floor");
  }
  if (/\bprimaryEntryTrigger\b.*postBullEventWindow|postBullEventWindow\b[\s\S]*postBearReboundWindow/i.test(source)) {
    features.push("dual post-event windows");
  }
  if (/\bentryWindowBars\b|\bwindowBars\b|\brotationWindowEnd\b/i.test(source)) {
    features.push("rotation window aliases");
  }
  if (/\bmaxHoldBars\b|\bholdBars[1-4]\b|ageHeld\s*>=/i.test(source)) {
    features.push("simple time exit");
  }
  if (/\bf_find_weakest_idx\b|\buseReplacement\b/i.test(source)) {
    features.push("slot replacement");
  }
  if (/\benableWeakRangeExit\b/i.test(source)) {
    features.push("weak range exit");
  }
  if (/\buseSupertrendFilter\b/i.test(source)) {
    features.push("optional supertrend filter");
  }
  return features.slice(0, 7);
}

function inferEntryShape(source: string): string {
  if (/\bentryPass\s*=\s*primaryEntryTrigger\s+and\s+not\s+riskOff/i.test(source)) {
    return "primaryEntryTrigger with one risk-off exclusion";
  }
  if (/\bentrySignal\b/i.test(source)) {
    return "entrySignal rotation path";
  }
  if (/\bprimaryEntryTrigger\b/i.test(source)) {
    return "primaryEntryTrigger route";
  }
  return "AF seed event entry";
}

function inferExitShape(source: string): string {
  if (/\bmaxHoldBars\b|\bholdBars[1-4]\b/i.test(source)) {
    return "fixed slot-age time exit plus bearish reductions";
  }
  if (/\benableWeakRangeExit\b/i.test(source)) {
    return "weak-range loser cleanup";
  }
  return "seed bearish event exits";
}

function inferRiskShape(source: string): string {
  if (/\briskOff\b[\s\S]{0,120}\bbaseEMA\b/i.test(source)) {
    return "base EMA / RSI risk-off gate";
  }
  if (/\bsupertrendRiskOffEnabled\b/i.test(source)) {
    return "optional supertrend risk-off";
  }
  return "minimal local risk controls";
}

function toDashboardHypothesis(record: MutationBriefRecord): DashboardHypothesis {
  const brief = record.brief;
  const outcomeMemory = brief.breakoutOutcomeMemory;
  const variant = brief.breakoutVariantDirective;
  return {
    hypothesis: brief.analysisGuidance.hypothesis,
    expectedEffect: brief.analysisGuidance.expectedEffect,
    invalidIf: brief.analysisGuidance.invalidIf,
    nextMutationDirection: brief.nextMutationDirection,
    repairMode: brief.repairMode,
    route: {
      preferred: outcomeMemory?.preferredRoutes ?? [],
      suppressed: outcomeMemory?.suppressedRoutes ?? [],
      sparsePatterns: outcomeMemory?.dominantSparsePatterns ?? [],
      variant: variant?.variantId ?? null,
      escalationLevel: variant?.escalationLevel ?? null,
    },
  };
}

function toDashboardProblem(event: ProblemEventRecord): DashboardProblem {
  return {
    iteration: event.iteration ?? null,
    candidateId: event.candidateId ?? null,
    problemKind: event.problemKind,
    diagnosis: event.diagnosis,
    suggestedRepairKind: event.suggestedRepairKind ?? null,
    recordedAt: event.recordedAt ?? null,
  };
}

function toDashboardRepair(attempt: RepairAttemptRecord): DashboardRepair {
  return {
    iteration: attempt.iteration ?? null,
    candidateId: attempt.candidateId ?? null,
    repairedCandidateId: attempt.repairedCandidateId ?? null,
    repairKind: attempt.repairKind,
    result: attempt.result,
    summary: attempt.summary,
    recordedAt: attempt.recordedAt ?? null,
  };
}

function buildImprovementStatus(input: {
  recentCandidatePoints: DashboardCandidatePoint[];
  recentSparseProblemCount: number;
  recentPreflightRepairCount: number;
  latest: DashboardCandidatePoint | null;
}): DashboardStatusPayload["improvement"] {
  const recent = input.recentCandidatePoints.slice(-6);
  const eligibleCount = recent.filter((point) => point.eligible).length;
  const sparseStillHigh = input.recentSparseProblemCount >= 3;
  const preflightStillHigh = input.recentPreflightRepairCount >= 3;
  if (eligibleCount >= 3 && !sparseStillHigh) {
    return {
      status: preflightStillHigh ? "watch" : "improving",
      summary: preflightStillHigh
        ? "Trade-count stagnation is broken, but sparse-source preflight repair is still carrying the route."
        : "Recent candidates are clearing local eligibility and the 31/7 cluster is no longer dominant.",
      nextFocus: preflightStillHigh
        ? [
            "Reduce sparse-source generation so deterministic repair is a fallback, not the main path.",
            "Keep explicit eventFloorBars/eventWindowBars/maxHoldBars route inputs in generated Pine.",
          ]
        : [
            "Compare high-trade eligible candidates against the active champion for promotion readiness.",
            "Watch drawdown and profit-factor stability before widening the route again.",
          ],
    };
  }

  if (sparseStillHigh) {
    return {
      status: "blocked",
      summary: "Recent failures still include repeated sparse 31/7-style trade-count collapses.",
      nextFocus: [
        "Suppress route shapes that do not expose route-aware inputs.",
        "Force canonical dense event-floor entry before local evaluation.",
      ],
    };
  }

  return {
    status: "watch",
    summary: input.latest
      ? "The loop is producing evaluable candidates, but recent eligibility density is not yet stable."
      : "The loop is running, but there is not enough fresh local-evaluation evidence in the tail window.",
    nextFocus: [
      "Collect a few more local candidates.",
      "Keep local candidates in frontier/calibration until verified promotion evidence arrives.",
    ],
  };
}

function countLatestEligibleStreak(points: DashboardCandidatePoint[]): number {
  let count = 0;
  for (const point of [...points].reverse()) {
    if (!point.eligible) {
      break;
    }
    count += 1;
  }
  return count;
}

function isSparseTradeDiagnosis(diagnosis: string): boolean {
  return /31\s*(?:total\s*)?(?:trades)?\s*\/\s*7|full_sample_trades=31|oos_trades=7|sparse_oos_trade_cluster/i.test(
    diagnosis,
  );
}

function isPidAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function recordValue(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function recordNumberMap(value: unknown): Record<string, number> {
  const record = recordValue(value);
  if (!record) {
    return {};
  }
  return Object.fromEntries(
    Object.entries(record)
      .map(([key, raw]) => [key, numberValue(raw)] as const)
      .filter((entry): entry is readonly [string, number] => entry[1] != null),
  );
}

function booleanValue(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}

function compareRecordedAtAscending(
  left: Record<string, unknown>,
  right: Record<string, unknown>,
): number {
  return dateMs(stringValue(left.recordedAt)) - dateMs(stringValue(right.recordedAt));
}

function dateMs(value: string | null): number {
  return value ? Date.parse(value) || 0 : 0;
}

function escapeForRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
