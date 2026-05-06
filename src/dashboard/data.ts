import { readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

import {
  type BacktestMetrics,
  type CandidateLedgerRecord,
  type ExperimentRecord,
  type IndicatorArtifactRecord,
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
    returnProfile: DashboardReturnProfile;
  };
  trend: DashboardCandidatePoint[];
  recentCandidates: DashboardCandidatePoint[];
  bestStrategy: DashboardStrategyAnalysis | null;
  bestReturnStrategy: DashboardStrategyAnalysis | null;
  hypothesis: DashboardHypothesis | null;
  improvement: {
    status: "improving" | "watch" | "blocked";
    summary: string;
    nextFocus: string[];
  };
  researchMode: {
    mode: string;
    activeCriterion: string | null;
    nextPlannedActionReason: string | null;
    latestIndicatorArtifact: Record<string, unknown> | null;
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

export interface DashboardReturnProfile {
  latestPercent: number | null;
  recentBestPercent: number | null;
  recentBestCandidateId: string | null;
  recentAveragePercent: number | null;
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
  researchModeConfig?: Record<string, unknown>;
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
    indicatorArtifacts,
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
    readJsonlTail<IndicatorArtifactRecord>(
      paths.indicatorArtifactsPath,
      10,
      1024 * 1024,
    ),
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
  const returnProfile = buildReturnProfile({
    recentCandidatePoints,
    latest,
  });
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
    returnProfile,
  });
  const bestStrategy = strategyCandidateId
    ? await analyzeStrategyCandidate({
        workspaceRoot: input.workspaceRoot,
        candidateId: strategyCandidateId,
        candidateRecord: candidateById.get(strategyCandidateId) ?? null,
      })
    : null;
  const bestReturnStrategy = returnProfile.recentBestCandidateId
    ? returnProfile.recentBestCandidateId === bestStrategy?.candidateId
      ? bestStrategy
      : await analyzeStrategyCandidate({
          workspaceRoot: input.workspaceRoot,
          candidateId: returnProfile.recentBestCandidateId,
          candidateRecord: candidateById.get(returnProfile.recentBestCandidateId) ?? null,
        })
    : null;

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
      returnProfile,
    },
    trend,
    recentCandidates: recentCandidatePoints.slice(-12).reverse(),
    bestStrategy,
    bestReturnStrategy,
    hypothesis: latestBrief ? toDashboardHypothesis(latestBrief) : null,
    improvement,
    researchMode: buildResearchModeDashboard({
      autonomousSummary,
      researchModeConfig: input.researchModeConfig,
      indicatorArtifacts,
    }),
    verifiedAutoresearch: buildVerifiedAutoresearchDashboard(autonomousSummary),
    externalValidation,
    failureMemory: {
      recentProblems,
      recentRepairs,
    },
  };
}

function buildResearchModeDashboard(input: {
  autonomousSummary: Record<string, unknown> | null;
  researchModeConfig?: Record<string, unknown>;
  indicatorArtifacts: IndicatorArtifactRecord[];
}): DashboardStatusPayload["researchMode"] {
  const researchMode =
    recordValue(input.autonomousSummary?.researchMode) ??
    input.researchModeConfig ??
    null;
  const latestIndicatorArtifact =
    recordValue(input.autonomousSummary?.latestIndicatorArtifact) ??
    input.indicatorArtifacts
      .slice()
      .sort(
        (left, right) =>
          Date.parse(right.createdAt ?? "") - Date.parse(left.createdAt ?? ""),
      )[0] ??
    null;
  return {
    mode: stringValue(researchMode?.mode) ?? "continuous_improvement",
    activeCriterion: stringValue(input.autonomousSummary?.activeCriterion),
    nextPlannedActionReason: stringValue(
      input.autonomousSummary?.nextPlannedActionReason,
    ),
    latestIndicatorArtifact: latestIndicatorArtifact
      ? {
          indicatorId: stringValue(latestIndicatorArtifact.indicatorId),
          goal: stringValue(latestIndicatorArtifact.goal),
          pinePath: stringValue(latestIndicatorArtifact.pinePath),
          validationStatus: stringValue(latestIndicatorArtifact.validationStatus),
          createdAt: stringValue(latestIndicatorArtifact.createdAt),
        }
      : null,
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
  returnProfile: DashboardReturnProfile;
}): DashboardStatusPayload["operatorBrief"] {
  const manualExternal =
    !input.externalValidation.autoProcessCalibration &&
    input.externalValidation.promotionVerificationExecutor === "none";
  const mode = manualExternal ? "local_only" : "external_auto";
  const latestScore = input.latest?.score == null ? "점수 없음" : input.latest.score.toFixed(4);
  const latestReturn = formatBriefPercent(input.returnProfile.latestPercent);
  const bestScore = input.bestEligible?.score == null ? "적격 점수 없음" : input.bestEligible.score.toFixed(4);
  const bestReturn = formatBriefPercent(input.returnProfile.recentBestPercent);
  const pending = input.externalValidation.pendingCount;
  const headline = manualExternal
    ? "로컬 연구가 기준이며 TradingView는 수동 검증입니다."
    : "외부 검증이 켜져 있으므로 TradingView 표면 상태를 같이 봐야 합니다.";
  const summary = [
    input.runtime.running
      ? `루프 실행 중입니다. 최신 로컬 점수는 ${latestScore}, 수익률은 ${latestReturn}입니다.`
      : input.runtime.stopRequested
        ? `사용자 요청으로 루프가 멈춰 있습니다. 최신 로컬 점수는 ${latestScore}, 수익률은 ${latestReturn}입니다.`
        : `루프는 실행 중이 아닙니다. 최신 로컬 점수는 ${latestScore}, 수익률은 ${latestReturn}입니다.`,
    `최고 로컬 적격 점수는 ${bestScore}, 최근 최고 수익률은 ${bestReturn}입니다.`,
    pending > 0
      ? `${pending}개 후보가 수동 TradingView 검증을 기다립니다.`
      : "긴급한 수동 TradingView 검증 대기는 없습니다.",
  ].join(" ");
  const warnings: string[] = [];
  if (input.improvement.status === "blocked") {
    warnings.push(input.improvement.summary);
  }
  if (input.externalValidation.latestDivergence?.parityStatus === "major_drift") {
    warnings.push(
      `최근 TV 비교에서 ${input.externalValidation.latestDivergence.candidateId}가 major_drift였습니다.`,
    );
  }
  if (input.externalValidation.autoProcessCalibration) {
    warnings.push("TradingView 큐 자동 처리가 켜져 있습니다.");
  }

  return {
    mode,
    headline,
    summary,
    evidence: [
      {
        label: "루프",
        value: input.runtime.running
          ? `실행 중 pid ${input.runtime.pid}`
          : input.runtime.stopRequested
            ? "중지 요청됨"
            : "중지됨",
        status: input.runtime.running ? "good" : input.runtime.stopRequested ? "watch" : "neutral",
      },
      {
        label: "로컬 추세",
        value: translateImprovementStatus(input.improvement.status),
        status:
          input.improvement.status === "improving"
            ? "good"
            : input.improvement.status === "blocked"
              ? "bad"
              : "watch",
      },
      {
        label: "최고 로컬",
        value: input.bestEligible?.candidateId
          ? `${input.bestEligible.candidateId} / ${bestScore}`
          : "없음",
        status: input.bestEligible ? "good" : "watch",
      },
      {
        label: "최신 수익률",
        value: latestReturn,
        status: (input.returnProfile.latestPercent ?? 0) > 0 ? "good" : "watch",
      },
      {
        label: "최근 최고 수익률",
        value: input.returnProfile.recentBestCandidateId
          ? `${bestReturn} / ${input.returnProfile.recentBestCandidateId}`
          : bestReturn,
        status: (input.returnProfile.recentBestPercent ?? 0) > 0 ? "good" : "watch",
      },
      {
        label: "활성 챔피언",
        value: input.activeChampion?.candidateId ?? "없음",
        status: input.activeChampion ? "good" : "neutral",
      },
      {
        label: "TV 모드",
        value: manualExternal ? "수동" : "자동 켜짐",
        status: manualExternal ? "good" : "watch",
      },
      {
        label: "TV 큐",
        value: `${pending}개 대기`,
        status: pending > 0 ? "watch" : "good",
      },
    ],
    nextActions: [
      ...input.improvement.nextFocus.slice(0, 2),
      pending > 0
        ? "로컬 후보 품질이 충분히 좋아 보일 때 수동 TV 검증을 1개만 실행합니다."
        : "TradingView에 시간을 쓰기 전에 로컬 루프 증거를 더 모읍니다.",
    ],
    warnings,
    commands: [
      {
        label: "로컬 루프",
        command:
          "powershell -ExecutionPolicy Bypass -File scripts/run-autonomous-forever.ps1",
      },
      {
        label: "TV 큐 확인",
        command: "node dist/cli/index.js inspect-calibration-queue",
      },
      {
        label: "수동 TV 검증",
        command: "node dist/cli/index.js process-tv-calibration-queue --max-candidates 1",
      },
    ],
  };
}

function buildReturnProfile(input: {
  recentCandidatePoints: DashboardCandidatePoint[];
  latest: DashboardCandidatePoint | null;
}): DashboardReturnProfile {
  const returns = input.recentCandidatePoints
    .filter((point) => point.metrics?.netProfitPercent != null)
    .map((point) => ({
      candidateId: point.candidateId,
      value: point.metrics!.netProfitPercent,
    }));
  const recentTail = returns.slice(-12);
  const best = [...recentTail].sort((a, b) => b.value - a.value)[0] ?? null;
  const average = recentTail.length > 0
    ? recentTail.reduce((sum, point) => sum + point.value, 0) / recentTail.length
    : null;
  return {
    latestPercent: input.latest?.metrics?.netProfitPercent ?? null,
    recentBestPercent: best?.value ?? null,
    recentBestCandidateId: best?.candidateId ?? null,
    recentAveragePercent: average,
  };
}

function formatBriefPercent(value: number | null): string {
  return value == null ? "수익률 없음" : `${value.toFixed(2)}%`;
}

function translateImprovementStatus(
  status: DashboardStatusPayload["improvement"]["status"],
): string {
  switch (status) {
    case "improving":
      return "개선 중";
    case "blocked":
      return "막힘";
    case "watch":
    default:
      return "관찰";
  }
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
        ? "거래 수 정체는 깨졌지만, 아직 희소 소스 사전 수리가 경로를 많이 보조하고 있습니다."
        : "최근 후보가 로컬 적격 기준을 통과하고 있으며 31/7 거래 수 붕괴가 더 이상 지배적이지 않습니다.",
      nextFocus: preflightStillHigh
        ? [
            "희소 소스 생성을 줄여 결정적 수리가 주 경로가 아니라 예외 처리로만 쓰이게 합니다.",
            "생성 Pine에는 eventFloorBars/eventWindowBars/maxHoldBars 입력을 계속 명시합니다.",
          ]
        : [
            "거래 수가 충분한 적격 후보를 활성 챔피언과 비교해 승격 가능성을 확인합니다.",
            "경로를 다시 넓히기 전에 낙폭과 수익 팩터 안정성을 봅니다.",
          ],
    };
  }

  if (sparseStillHigh) {
    return {
      status: "blocked",
      summary: "최근 실패에 31/7 형태의 거래 수 붕괴가 반복적으로 포함되어 있습니다.",
      nextFocus: [
        "경로 인식 입력을 노출하지 않는 형태를 억제합니다.",
        "로컬 평가 전에 표준 dense event-floor 진입을 강제합니다.",
      ],
    };
  }

  return {
    status: "watch",
    summary: input.latest
      ? "루프가 평가 가능한 후보를 만들고 있지만 최근 적격 밀도는 아직 안정적이지 않습니다."
      : "루프 상태는 확인되지만 tail window 안의 최신 로컬 평가 증거가 충분하지 않습니다.",
    nextFocus: [
      "로컬 후보를 몇 개 더 모읍니다.",
      "검증된 승격 증거가 생길 때까지 후보를 frontier/calibration 단계에 둡니다.",
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
