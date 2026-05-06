import path from "node:path";

export interface KnowledgePaths {
  root: string;
  policyDir: string;
  evidenceDir: string;
  artifactDir: string;
  ledgerDir: string;
  viewsDir: string;
  taxonomyDir: string;
  runtimeDir: string;
  tracesDir: string;
  desktopRunsDir: string;
  resultsDir: string;
  researchDir: string;
  qqqTwoHourContextPath: string;
  experimentsPath: string;
  incidentsPath: string;
  runsPath: string;
  taskBatchesPath: string;
  tasksPath: string;
  mutationBriefsPath: string;
  autonomousIterationRecordsPath: string;
  indicatorArtifactsPath: string;
  candidatesPath: string;
  researchKnowledgePath: string;
  headEventsPath: string;
  archiveEventsPath: string;
  calibrationEventsPath: string;
  localConfidenceEventsPath: string;
  problemEventsPath: string;
  repairAttemptsPath: string;
  branchesPath: string;
  leaderboardPath: string;
  lineagePath: string;
  frontierPath: string;
  failureSummaryPath: string;
  taskBoardPath: string;
  verificationFailuresPath: string;
  fallbackEvidenceBoardPath: string;
  screeningBoardPath: string;
  invalidRecordsPath: string;
  runtimeFailureSummaryPath: string;
  localTvDivergenceSummaryPath: string;
  verificationQueuePath: string;
  lossPatternSummaryPath: string;
  researchSummaryPath: string;
  localLeaderboardPath: string;
  championHistoryPath: string;
  explorationArchivePath: string;
  noveltyFrontierPath: string;
  robustnessFrontierPath: string;
  tvSurfaceFailuresPath: string;
  tvCalibrationQueuePath: string;
  localTvDivergencePath: string;
  autoSelectionDecisionsPath: string;
  duplicateCandidatesPath: string;
  localCompatibilitySummaryPath: string;
  autonomousStateSummaryPath: string;
  stage6ReadinessPath: string;
  localConfidenceSummaryPath: string;
  failureMemoryPath: string;
  objectivePolicyPath: string;
  decisionCodesPath: string;
  incidentTypesPath: string;
  knowledgeTypesPath: string;
  knowledgeCatalogPath: string;
}

export function resolveKnowledgePaths(stateRoot: string): KnowledgePaths {
  const policyDir = path.join(stateRoot, "policy");
  const evidenceDir = path.join(stateRoot, "evidence");
  const artifactDir = path.join(stateRoot, "artifacts");
  const ledgerDir = path.join(stateRoot, "ledger");
  const viewsDir = path.join(stateRoot, "views");
  const taxonomyDir = path.join(stateRoot, "taxonomy");
  const runtimeDir = path.join(stateRoot, "runtime");
  const tracesDir = path.join(stateRoot, "traces");
  const desktopRunsDir = path.join(artifactDir, "desktop-runs");
  const resultsDir = path.join(artifactDir, "results");
  const researchDir = path.join(evidenceDir, "research");

  return {
    root: stateRoot,
    policyDir,
    evidenceDir,
    artifactDir,
    ledgerDir,
    viewsDir,
    taxonomyDir,
    runtimeDir,
    tracesDir,
    desktopRunsDir,
    resultsDir,
    researchDir,
    qqqTwoHourContextPath: path.join(resultsDir, "qqq-2h-context.json"),
    experimentsPath: path.join(ledgerDir, "experiments.jsonl"),
    incidentsPath: path.join(ledgerDir, "incidents.jsonl"),
    runsPath: path.join(ledgerDir, "runs.jsonl"),
    taskBatchesPath: path.join(ledgerDir, "task-batches.jsonl"),
    tasksPath: path.join(ledgerDir, "tasks.jsonl"),
    mutationBriefsPath: path.join(ledgerDir, "mutation-briefs.jsonl"),
    autonomousIterationRecordsPath: path.join(
      ledgerDir,
      "autonomous-iteration-records.jsonl",
    ),
    indicatorArtifactsPath: path.join(ledgerDir, "indicator-artifacts.jsonl"),
    candidatesPath: path.join(ledgerDir, "candidates.jsonl"),
    researchKnowledgePath: path.join(ledgerDir, "research-knowledge.jsonl"),
    headEventsPath: path.join(ledgerDir, "head-events.jsonl"),
    archiveEventsPath: path.join(ledgerDir, "archive-events.jsonl"),
    calibrationEventsPath: path.join(ledgerDir, "calibration-events.jsonl"),
    localConfidenceEventsPath: path.join(
      ledgerDir,
      "calibration-confidence-events.jsonl",
    ),
    problemEventsPath: path.join(ledgerDir, "problem-events.jsonl"),
    repairAttemptsPath: path.join(ledgerDir, "repair-attempts.jsonl"),
    branchesPath: path.join(ledgerDir, "branches.jsonl"),
    leaderboardPath: path.join(viewsDir, "leaderboard.json"),
    lineagePath: path.join(viewsDir, "lineage.json"),
    frontierPath: path.join(viewsDir, "frontier.json"),
    failureSummaryPath: path.join(viewsDir, "failure-summary.json"),
    taskBoardPath: path.join(viewsDir, "task-board.json"),
    verificationFailuresPath: path.join(viewsDir, "verification-failures.json"),
    fallbackEvidenceBoardPath: path.join(viewsDir, "fallback-evidence-board.json"),
    screeningBoardPath: path.join(viewsDir, "screening-board.json"),
    invalidRecordsPath: path.join(viewsDir, "invalid-records.json"),
    runtimeFailureSummaryPath: path.join(viewsDir, "runtime-failure-summary.json"),
    localTvDivergenceSummaryPath: path.join(viewsDir, "local-tv-divergence-summary.json"),
    verificationQueuePath: path.join(viewsDir, "verification-queue.json"),
    lossPatternSummaryPath: path.join(viewsDir, "loss-pattern-summary.json"),
    researchSummaryPath: path.join(viewsDir, "research-summary.json"),
    localLeaderboardPath: path.join(viewsDir, "local-leaderboard.json"),
    championHistoryPath: path.join(viewsDir, "champion-history.json"),
    explorationArchivePath: path.join(viewsDir, "exploration-archive.json"),
    noveltyFrontierPath: path.join(viewsDir, "novelty-frontier.json"),
    robustnessFrontierPath: path.join(viewsDir, "robustness-frontier.json"),
    tvSurfaceFailuresPath: path.join(viewsDir, "tv-surface-failures.json"),
    tvCalibrationQueuePath: path.join(viewsDir, "tv-calibration-queue.json"),
    localTvDivergencePath: path.join(viewsDir, "local-tv-divergence.json"),
    autoSelectionDecisionsPath: path.join(viewsDir, "auto-selection-decisions.json"),
    duplicateCandidatesPath: path.join(viewsDir, "duplicate-candidates.json"),
    localCompatibilitySummaryPath: path.join(
      viewsDir,
      "local-compatibility-summary.json",
    ),
    autonomousStateSummaryPath: path.join(viewsDir, "autonomous-state-summary.json"),
    stage6ReadinessPath: path.join(viewsDir, "autonomous", "stage6-readiness.json"),
    localConfidenceSummaryPath: path.join(
      viewsDir,
      "local-confidence-summary.json",
    ),
    failureMemoryPath: path.join(viewsDir, "failure-memory.json"),
    objectivePolicyPath: path.join(policyDir, "objective.current.json"),
    decisionCodesPath: path.join(taxonomyDir, "decision-codes.json"),
    incidentTypesPath: path.join(taxonomyDir, "incident-types.json"),
    knowledgeTypesPath: path.join(taxonomyDir, "knowledge-types.json"),
    knowledgeCatalogPath: path.join(taxonomyDir, "knowledge-catalog.json"),
  };
}
