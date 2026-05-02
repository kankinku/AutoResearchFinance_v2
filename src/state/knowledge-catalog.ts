import path from "node:path";
import { copyFile, readdir, readFile } from "node:fs/promises";

import {
  knowledgeCatalogSchema,
  type KnowledgeCatalogEntry,
  type ObjectiveConfig,
} from "../contracts/types.js";
import { ensureDir, fileExists, writeJson } from "../utils/fs.js";
import { resolveKnowledgePaths } from "./knowledge-paths.js";

export function buildKnowledgeCatalogEntries(stateRoot: string): KnowledgeCatalogEntry[] {
  const paths = resolveKnowledgePaths(stateRoot);

  return [
    {
      id: "policy.objective.current",
      storageClass: "policy",
      relativePath: relativeToRoot(paths.objectivePolicyPath, stateRoot),
      format: "json",
      sourceOfTruth: true,
      producer: "workspace.initialize/syncKnowledgeCatalog",
      consumers: ["evaluation.objective", "mutation.brief"],
      rebuildRule: "overwrite from config/objective.qqq-120m.json on bootstrap and iteration",
      retention: "keep latest current objective snapshot",
      description: "Current objective and guardrail policy snapshot used by runtime evaluation.",
    },
    {
      id: "evidence.traces",
      storageClass: "evidence",
      relativePath: relativeToRoot(paths.tracesDir, stateRoot),
      format: "directory",
      sourceOfTruth: true,
      producer: "cli.monitor",
      consumers: ["operator review", "knowledge.audit"],
      rebuildRule: "append-only per CLI run",
      retention: "keep all traces unless manually pruned",
      description: "Human-monitorable CLI step traces for every command execution.",
    },
    {
      id: "evidence.desktop_runs",
      storageClass: "evidence",
      relativePath: relativeToRoot(paths.desktopRunsDir, stateRoot),
      format: "directory",
      sourceOfTruth: true,
      producer: "research.artifact-writer",
      consumers: ["operator review", "experiment inspection"],
      rebuildRule: "append/update per iteration",
      retention: "keep all sync/backtest artifacts",
      description: "Raw Pine evaluation executor sync and backtest evidence artifacts.",
    },
    {
      id: "evidence.results",
      storageClass: "evidence",
      relativePath: relativeToRoot(paths.resultsDir, stateRoot),
      format: "directory",
      sourceOfTruth: false,
      producer: "research.artifact-writer",
      consumers: ["operator review", "latest result inspection"],
      rebuildRule: "overwrite latest result summaries on each evaluation",
      retention: "keep latest snapshots",
      description: "Latest objective and backtest summaries derived from the latest evaluation.",
    },
    {
      id: "evidence.research",
      storageClass: "evidence",
      relativePath: relativeToRoot(paths.researchDir, stateRoot),
      format: "directory",
      sourceOfTruth: true,
      producer: "research.research-knowledge",
      consumers: ["mutation.brief", "operator review"],
      rebuildRule: "append raw extracted text per ingested research item",
      retention: "keep all ingested research source extracts",
      description: "Raw PDF/text extracts and manual knowledge payloads attached to AF.",
    },
    {
      id: "evidence.qqq_2h_context",
      storageClass: "evidence",
      relativePath: relativeToRoot(paths.qqqTwoHourContextPath, stateRoot),
      format: "json",
      sourceOfTruth: true,
      producer: "research.market-context",
      consumers: ["research.trade-context", "research.loss-analysis"],
      rebuildRule: "refresh from Yahoo chart data or reuse cached copy",
      retention: "keep latest context cache",
      description: "QQQ 2-hour market context cache used to enrich AF trade records.",
    },
    {
      id: "ledger.runs",
      storageClass: "ledger",
      relativePath: relativeToRoot(paths.runsPath, stateRoot),
      format: "jsonl",
      sourceOfTruth: true,
      producer: "cli.iterate",
      consumers: ["knowledge.audit", "run inspection"],
      rebuildRule: "append per run",
      retention: "append-only",
      description: "Run-level execution ledger across iteration batches.",
    },
    {
      id: "ledger.task_batches",
      storageClass: "ledger",
      relativePath: relativeToRoot(paths.taskBatchesPath, stateRoot),
      format: "jsonl",
      sourceOfTruth: true,
      producer: "research.task-batch-runner",
      consumers: ["views.task-board", "operator review"],
      rebuildRule: "append per task batch lifecycle update",
      retention: "append-only",
      description: "Constrained task batch ledger for bounded autonomous runs.",
    },
    {
      id: "ledger.tasks",
      storageClass: "ledger",
      relativePath: relativeToRoot(paths.tasksPath, stateRoot),
      format: "jsonl",
      sourceOfTruth: true,
      producer: "research.task-batch-runner",
      consumers: ["views.task-board", "operator review"],
      rebuildRule: "append per completed or failed task",
      retention: "append-only",
      description: "Per-task hypothesis, execution, and analysis ledger.",
    },
    {
      id: "ledger.mutation_briefs",
      storageClass: "ledger",
      relativePath: relativeToRoot(paths.mutationBriefsPath, stateRoot),
      format: "jsonl",
      sourceOfTruth: true,
      producer: "research.iteration-runner",
      consumers: ["mutation analysis", "knowledge.audit"],
      rebuildRule: "append per iteration before mutation request",
      retention: "append-only",
      description: "Structured mutation brief history used to drive candidate generation.",
    },
    {
      id: "ledger.candidates",
      storageClass: "ledger",
      relativePath: relativeToRoot(paths.candidatesPath, stateRoot),
      format: "jsonl",
      sourceOfTruth: true,
      producer: "mutation.candidate-store",
      consumers: ["lineage analysis", "knowledge.audit"],
      rebuildRule: "append per candidate persist",
      retention: "append-only",
      description: "Candidate-level ledger describing persisted strategy variants.",
    },
    {
      id: "ledger.research_knowledge",
      storageClass: "ledger",
      relativePath: relativeToRoot(paths.researchKnowledgePath, stateRoot),
      format: "jsonl",
      sourceOfTruth: true,
      producer: "research.research-knowledge",
      consumers: ["mutation.brief", "views.research-summary", "operator review"],
      rebuildRule: "append per ingested research item",
      retention: "append-only",
      description: "Structured external research knowledge attached to AF for hypothesis generation.",
    },
    {
      id: "ledger.experiments",
      storageClass: "ledger",
      relativePath: relativeToRoot(paths.experimentsPath, stateRoot),
      format: "jsonl",
      sourceOfTruth: true,
      producer: "research.iteration-runner",
      consumers: ["views.index-builder", "mutation analysis"],
      rebuildRule: "append per evaluated candidate",
      retention: "append-only",
      description: "Canonical experiment ledger and the primary source of truth for derived views.",
    },
    {
      id: "ledger.incidents",
      storageClass: "ledger",
      relativePath: relativeToRoot(paths.incidentsPath, stateRoot),
      format: "jsonl",
      sourceOfTruth: true,
      producer: "research.iteration-runner",
      consumers: ["views.failure-summary", "operator review"],
      rebuildRule: "append per failure or noteworthy runtime incident",
      retention: "append-only",
      description: "Runtime and evaluation incident ledger.",
    },
    {
      id: "views.leaderboard",
      storageClass: "view",
      relativePath: relativeToRoot(paths.leaderboardPath, stateRoot),
      format: "json",
      sourceOfTruth: false,
      producer: "state.index-builder",
      consumers: ["operator review"],
      rebuildRule: "rebuild from ledger.experiments",
      retention: "latest only",
      description: "Ranked candidate summary derived from experiments.",
    },
    {
      id: "views.lineage",
      storageClass: "view",
      relativePath: relativeToRoot(paths.lineagePath, stateRoot),
      format: "json",
      sourceOfTruth: false,
      producer: "state.index-builder",
      consumers: ["operator review"],
      rebuildRule: "rebuild from ledger.experiments",
      retention: "latest only",
      description: "Candidate lineage graph derived from experiments.",
    },
    {
      id: "views.frontier",
      storageClass: "view",
      relativePath: relativeToRoot(paths.frontierPath, stateRoot),
      format: "json",
      sourceOfTruth: false,
      producer: "state.index-builder",
      consumers: ["operator review"],
      rebuildRule: "rebuild from ledger.experiments",
      retention: "latest only",
      description: "Accepted frontier view derived from experiments.",
    },
    {
      id: "views.failure_summary",
      storageClass: "view",
      relativePath: relativeToRoot(paths.failureSummaryPath, stateRoot),
      format: "json",
      sourceOfTruth: false,
      producer: "state.index-builder",
      consumers: ["operator review", "mutation policy tuning"],
      rebuildRule: "rebuild from ledger.incidents and ledger.experiments",
      retention: "latest only",
      description: "Failure and incident aggregates derived from ledgers.",
    },
    {
      id: "views.task_board",
      storageClass: "view",
      relativePath: relativeToRoot(paths.taskBoardPath, stateRoot),
      format: "json",
      sourceOfTruth: false,
      producer: "state.index-builder",
      consumers: ["operator review"],
      rebuildRule: "rebuild from ledger.task_batches and ledger.tasks",
      retention: "latest only",
      description: "Batch progress board showing task-level hypothesis, execution, and analysis state.",
    },
    {
      id: "views.verification_failures",
      storageClass: "view",
      relativePath: relativeToRoot(paths.verificationFailuresPath, stateRoot),
      format: "json",
      sourceOfTruth: false,
      producer: "state.index-builder",
      consumers: ["operator review"],
      rebuildRule: "rebuild from ledger.experiments",
      retention: "latest only",
      description: "Verification failure board with runtime and metric-regression outcomes.",
    },
    {
      id: "views.fallback_evidence_board",
      storageClass: "view",
      relativePath: relativeToRoot(paths.fallbackEvidenceBoardPath, stateRoot),
      format: "json",
      sourceOfTruth: false,
      producer: "state.index-builder",
      consumers: ["operator review", "mutation policy tuning"],
      rebuildRule: "rebuild from ledger.experiments",
      retention: "latest only",
      description: "Local fallback evidence collected after authoritative runtime failures.",
    },
    {
      id: "views.screening_board",
      storageClass: "view",
      relativePath: relativeToRoot(paths.screeningBoardPath, stateRoot),
      format: "json",
      sourceOfTruth: false,
      producer: "state.index-builder",
      consumers: ["operator review"],
      rebuildRule: "rebuild from ledger.experiments",
      retention: "latest only",
      description: "Canonical screening-only board for local and non-promoted records.",
    },
    {
      id: "views.invalid_records",
      storageClass: "view",
      relativePath: relativeToRoot(paths.invalidRecordsPath, stateRoot),
      format: "json",
      sourceOfTruth: false,
      producer: "state.index-builder",
      consumers: ["operator review", "knowledge.audit"],
      rebuildRule: "rebuild from ledger.experiments",
      retention: "latest only",
      description: "Quarantined current records that violate verified, promotion, or promoted-head contracts.",
    },
    {
      id: "views.runtime_failure_summary",
      storageClass: "view",
      relativePath: relativeToRoot(paths.runtimeFailureSummaryPath, stateRoot),
      format: "json",
      sourceOfTruth: false,
      producer: "state.index-builder",
      consumers: ["operator review"],
      rebuildRule: "rebuild from ledger.experiments",
      retention: "latest only",
      description: "Aggregate counts of authoritative runtime failure kinds.",
    },
    {
      id: "views.local_tv_divergence_summary",
      storageClass: "view",
      relativePath: relativeToRoot(paths.localTvDivergenceSummaryPath, stateRoot),
      format: "json",
      sourceOfTruth: false,
      producer: "state.index-builder",
      consumers: ["operator review", "mutation policy tuning"],
      rebuildRule: "rebuild from ledger.experiments",
      retention: "latest only",
      description: "Prepared local-versus-TradingView divergence report structure.",
    },
    {
      id: "views.verification_queue",
      storageClass: "view",
      relativePath: relativeToRoot(paths.verificationQueuePath, stateRoot),
      format: "json",
      sourceOfTruth: false,
      producer: "state.index-builder",
      consumers: ["operator review"],
      rebuildRule: "rebuild from ledger.experiments",
      retention: "latest only",
      description: "Candidates waiting on re-verification after authoritative runtime failures.",
    },
    {
      id: "views.loss_pattern_summary",
      storageClass: "view",
      relativePath: relativeToRoot(paths.lossPatternSummaryPath, stateRoot),
      format: "json",
      sourceOfTruth: false,
      producer: "state.index-builder",
      consumers: ["operator review", "mutation policy tuning"],
      rebuildRule: "rebuild from ledger.experiments",
      retention: "latest only",
      description: "Aggregated recurring loss zones and repair priorities derived from experiments.",
    },
    {
      id: "views.research_summary",
      storageClass: "view",
      relativePath: relativeToRoot(paths.researchSummaryPath, stateRoot),
      format: "json",
      sourceOfTruth: false,
      producer: "state.index-builder",
      consumers: ["operator review", "mutation policy tuning"],
      rebuildRule: "rebuild from ledger.research_knowledge",
      retention: "latest only",
      description: "Summary of attached research knowledge and its dominant problem and strategy tags.",
    },
    {
      id: "taxonomy.knowledge_types",
      storageClass: "taxonomy",
      relativePath: relativeToRoot(paths.knowledgeTypesPath, stateRoot),
      format: "json",
      sourceOfTruth: true,
      producer: "state.knowledge-catalog",
      consumers: ["knowledge.audit"],
      rebuildRule: "overwrite on bootstrap and migration",
      retention: "latest only",
      description: "Knowledge storage classes supported by AF.",
    },
    {
      id: "taxonomy.decision_codes",
      storageClass: "taxonomy",
      relativePath: relativeToRoot(paths.decisionCodesPath, stateRoot),
      format: "json",
      sourceOfTruth: true,
      producer: "state.knowledge-catalog",
      consumers: ["knowledge.audit", "operator review"],
      rebuildRule: "overwrite on bootstrap and migration",
      retention: "latest only",
      description: "Recognized experiment decision codes.",
    },
    {
      id: "taxonomy.incident_types",
      storageClass: "taxonomy",
      relativePath: relativeToRoot(paths.incidentTypesPath, stateRoot),
      format: "json",
      sourceOfTruth: true,
      producer: "state.knowledge-catalog",
      consumers: ["knowledge.audit", "operator review"],
      rebuildRule: "overwrite on bootstrap and migration",
      retention: "latest only",
      description: "Recognized runtime and evaluation incident types.",
    },
    {
      id: "taxonomy.knowledge_catalog",
      storageClass: "taxonomy",
      relativePath: relativeToRoot(paths.knowledgeCatalogPath, stateRoot),
      format: "json",
      sourceOfTruth: true,
      producer: "state.knowledge-catalog",
      consumers: ["knowledge.audit", "operator review"],
      rebuildRule: "overwrite on bootstrap and migration",
      retention: "latest only",
      description: "Machine-readable inventory of AF knowledge artifacts.",
    },
    {
      id: "asset.strategy_candidates",
      storageClass: "asset",
      relativePath: path.join("..", "..", "strategies", "candidates").replace(/\\/g, "/"),
      format: "directory",
      sourceOfTruth: true,
      producer: "mutation.candidate-store",
      consumers: ["research.iteration-runner", "operator review"],
      rebuildRule: "append per candidate generation",
      retention: "keep all candidate files",
      description: "Persisted Pine candidate source files outside the state tree.",
    },
    {
      id: "asset.strategy_source",
      storageClass: "asset",
      relativePath: path.join("..", "..", "strategies", "source").replace(/\\/g, "/"),
      format: "directory",
      sourceOfTruth: true,
      producer: "workspace.initialize",
      consumers: ["research.iteration-runner", "operator review"],
      rebuildRule: "baseline static, runtime target overwritten per iteration",
      retention: "keep baseline and current runtime target",
      description: "Baseline and runtime Pine strategy sources outside the state tree.",
    },
  ];
}

export async function syncKnowledgeCatalog(
  workspaceRoot: string,
  objective: ObjectiveConfig,
): Promise<void> {
  const stateRoot = path.join(workspaceRoot, "state", "pi-autoresearch");
  const paths = resolveKnowledgePaths(stateRoot);
  const entries = buildKnowledgeCatalogEntries(stateRoot);

  await ensureDir(paths.policyDir);
  await ensureDir(paths.taxonomyDir);
  await writeJson(paths.objectivePolicyPath, objective);
  await writeJson(paths.knowledgeTypesPath, {
    generatedAt: new Date().toISOString(),
    storageClasses: ["policy", "evidence", "ledger", "view", "taxonomy", "asset"],
  });
  await writeJson(paths.decisionCodesPath, {
    generatedAt: new Date().toISOString(),
    decisionCodes: [
      "compile_fail",
      "mutation_generation_fail",
      "apply_fail",
      "backtest_empty",
      "hard_gate_fail",
      "soft_regress",
      "accepted_improvement",
      "accepted_no_improvement",
    ],
  });
  await writeJson(paths.incidentTypesPath, {
    generatedAt: new Date().toISOString(),
      incidentTypes: [
        "compile_fail",
        "mutation_generation_fail",
        "apply_fail",
        "backtest_empty",
        "hard_gate_fail",
        "soft_regress",
        "stale_attach_detected",
        "mutation_request_failed",
        "mutation_parse_failed",
        "mutation_preflight_blocked",
        "mutation_preflight_repair_failed",
        "mutation_preflight_failed",
        "market_context_load_failed",
        "compile_repair_failed",
        "task_runtime_failure",
        "research_refresh_failed",
        "research_refresh_runner_failed",
      ],
    });
  await writeJson(
    paths.knowledgeCatalogPath,
    knowledgeCatalogSchema.parse({
      generatedAt: new Date().toISOString(),
      entries,
    }),
  );
}

export async function migrateLegacyKnowledgeLayout(workspaceRoot: string): Promise<{
  copied: string[];
}> {
  const stateRoot = path.join(workspaceRoot, "state", "pi-autoresearch");
  const paths = resolveKnowledgePaths(stateRoot);
  const copied: string[] = [];

  const legacyPairs = [
    [path.join(stateRoot, "experiments.jsonl"), paths.experimentsPath],
    [path.join(stateRoot, "incidents.jsonl"), paths.incidentsPath],
    [path.join(stateRoot, "leaderboard.json"), paths.leaderboardPath],
    [path.join(stateRoot, "lineage.json"), paths.lineagePath],
    [path.join(stateRoot, "frontier.json"), paths.frontierPath],
  ] as const;

  for (const [sourcePath, targetPath] of legacyPairs) {
    if ((await fileExists(sourcePath)) && !(await fileExists(targetPath))) {
      await ensureDir(path.dirname(targetPath));
      await copyFile(sourcePath, targetPath);
      copied.push(relativeToWorkspace(targetPath, workspaceRoot));
    }
  }

  await copyDirectoryIfMissing(path.join(stateRoot, "traces"), paths.tracesDir, copied, workspaceRoot);
  await copyDirectoryIfMissing(
    path.join(workspaceRoot, "artifacts", "desktop-runs"),
    paths.desktopRunsDir,
    copied,
    workspaceRoot,
  );
  await copyDirectoryIfMissing(
    path.join(workspaceRoot, "artifacts", "results"),
    paths.resultsDir,
    copied,
    workspaceRoot,
  );

  return { copied };
}

export async function auditKnowledgeTree(workspaceRoot: string): Promise<{
  ok: boolean;
  summary: {
    totalEntries: number;
    existingEntries: number;
    missingEntries: number;
    legacyRootArtifacts: string[];
  };
  missingEntries: string[];
}> {
  const stateRoot = path.join(workspaceRoot, "state", "pi-autoresearch");
  const paths = resolveKnowledgePaths(stateRoot);
  const catalog = knowledgeCatalogSchema.parse(
    JSON.parse(await readFile(paths.knowledgeCatalogPath, "utf8")),
  );
  const hasExperimentLedger = await fileExists(paths.experimentsPath);
  const hasIncidentLedger = await fileExists(paths.incidentsPath);
  const hasResearchKnowledgeLedger = await fileExists(paths.researchKnowledgePath);

  const missingEntries: string[] = [];
  for (const entry of catalog.entries) {
    const absolutePath = path.resolve(stateRoot, entry.relativePath);
    if ((await fileExists(absolutePath)) || !shouldRequireEntry(entry, {
      hasExperimentLedger,
      hasIncidentLedger,
      hasResearchKnowledgeLedger,
    })) {
      continue;
    }
    if (!(await fileExists(absolutePath))) {
      missingEntries.push(entry.id);
    }
  }

  const legacyCandidates = [
    "experiments.jsonl",
    "incidents.jsonl",
    "leaderboard.json",
    "lineage.json",
    "frontier.json",
    "mutations",
  ];
  const resolvedLegacyRootArtifacts: string[] = [];
  for (const artifactName of legacyCandidates) {
    if (await fileExists(path.join(stateRoot, artifactName))) {
      resolvedLegacyRootArtifacts.push(artifactName);
    }
  }

  return {
    ok: missingEntries.length === 0,
    summary: {
      totalEntries: catalog.entries.length,
      existingEntries: catalog.entries.length - missingEntries.length,
      missingEntries: missingEntries.length,
      legacyRootArtifacts: resolvedLegacyRootArtifacts,
    },
    missingEntries,
  };
}

function shouldRequireEntry(
  entry: KnowledgeCatalogEntry,
  input: {
    hasExperimentLedger: boolean;
    hasIncidentLedger: boolean;
    hasResearchKnowledgeLedger: boolean;
  },
): boolean {
  if (entry.format === "directory") {
    return true;
  }

  if (entry.storageClass === "taxonomy" || entry.storageClass === "policy") {
    return true;
  }

  if (entry.storageClass === "asset") {
    return true;
  }

  if (entry.storageClass === "view") {
    if (entry.id === "views.research_summary") {
      return input.hasResearchKnowledgeLedger;
    }
    return input.hasExperimentLedger || input.hasIncidentLedger;
  }

  if (entry.storageClass === "evidence") {
    return false;
  }

  return false;
}

async function copyDirectoryIfMissing(
  sourceDir: string,
  targetDir: string,
  copied: string[],
  workspaceRoot: string,
): Promise<void> {
  if (!(await fileExists(sourceDir))) {
    return;
  }

  await ensureDir(targetDir);
  const entries = await readdir(sourceDir, { withFileTypes: true });
  for (const entry of entries) {
    const sourcePath = path.join(sourceDir, entry.name);
    const targetPath = path.join(targetDir, entry.name);
    if (entry.isDirectory()) {
      await copyDirectoryIfMissing(sourcePath, targetPath, copied, workspaceRoot);
      continue;
    }
    if (!(await fileExists(targetPath))) {
      await copyFile(sourcePath, targetPath);
      copied.push(relativeToWorkspace(targetPath, workspaceRoot));
    }
  }
}

function relativeToRoot(targetPath: string, rootPath: string): string {
  return path.relative(rootPath, targetPath).replace(/\\/g, "/");
}

function relativeToWorkspace(targetPath: string, workspaceRoot: string): string {
  return path.relative(workspaceRoot, targetPath).replace(/\\/g, "/");
}
