import { access, mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { describe, expect, test } from "vitest";

import { type ArtifactBundle } from "../../src/contracts/types.js";
import { validateLedger } from "../../src/state/ledger-validator.js";
import {
  appendAutonomousIterationRecord,
  appendExperimentRecord,
  compactExperimentLedger,
  ensureStateRoot,
  readAutonomousIterationRecords,
  readExperimentRecords,
  readRecentAutonomousIterationRecords,
  readRecentExperimentRecords,
} from "../../src/state/jsonl-store.js";
import { resolveKnowledgePaths } from "../../src/state/knowledge-paths.js";

function createArtifactBundle(): ArtifactBundle {
  return {
    strategy: {
      netProfitPercent: 4.2,
      postFeeNetProfitPercent: 4.2,
      profitFactor: 1.8,
      maxStrategyDrawdownPercent: 2.1,
      percentProfitable: 55,
      totalTrades: 2,
      avgTradePercent: 0.3,
    },
    trades: [
      {
        entryComment: "L_1",
        entryPrice: 100,
        entryTime: "2026-04-01T00:00:00.000Z",
        exitComment: "X_1",
        exitPrice: 101,
        exitTime: "2026-04-01T02:00:00.000Z",
        qty: 1,
        profitValue: 1,
        profitPercent: 1,
        runupPercent: 1.2,
        drawdownPercent: 0.1,
      },
      {
        entryComment: "L_2",
        entryPrice: 102,
        entryTime: "2026-04-02T00:00:00.000Z",
        exitComment: "X_2",
        exitPrice: 101,
        exitTime: "2026-04-02T02:00:00.000Z",
        qty: 1,
        profitValue: -1,
        profitPercent: -1,
        runupPercent: 0.2,
        drawdownPercent: 1.4,
      },
    ],
    equity: {
      available: true,
      unavailableReason: null,
      pointsAvailable: true,
      pointCount: 2,
      finalEquity: 10050,
      maxDrawdownPercent: 2.1,
      points: [
        { time: "2026-04-01T00:00:00.000Z", value: 10000 },
        { time: "2026-04-02T02:00:00.000Z", value: 10050 },
      ],
    },
    rawReportHash: "raw-hash",
    state: {
      source: "test",
    },
  };
}

async function writeCandidate(root: string, candidateId: string): Promise<string> {
  const candidatePath = path.join(root, `${candidateId}.pine`);
  await writeFile(candidatePath, "//@version=5\nstrategy('Compact Test')\n", "utf8");
  return candidatePath;
}

describe("experiment JSONL compaction", () => {
  test("appendExperimentRecord stores artifact bundles by reference", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-jsonl-compact-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");
    const candidatePath = await writeCandidate(root, "cand-compact");

    const record = await appendExperimentRecord(stateRoot, {
      runId: "run-1",
      iteration: 1,
      candidateId: "cand-compact",
      parentCandidateId: null,
      branchId: "main",
      acceptedHeadCandidateId: null,
      baselineCandidateId: null,
      candidatePath,
      candidateHash: "candidate-hash",
      candidateScore: 0.42,
      decision: "local_candidate_eligible",
      status: "evaluated",
      artifactBundle: createArtifactBundle(),
    });

    expect(record.artifactBundle).toBeUndefined();
    expect(record.artifactBundleRef?.path).toBeTruthy();
    expect(record.artifactPaths?.backtestArtifact).toBe(record.artifactBundleRef?.path);
    expect(record.artifactPaths?.artifactBundle).toBe(record.artifactBundleRef?.path);
    expect(record.artifactSummary?.tradeCount).toBe(2);
    expect(record.tradeSummary?.winningTrades).toBe(1);
    expect(record.equitySummary?.pointCount).toBe(2);
    await expect(access(record.artifactBundleRef?.path ?? "")).resolves.toBeUndefined();

    const paths = resolveKnowledgePaths(stateRoot);
    const ledger = await readFile(paths.experimentsPath, "utf8");
    const stored = JSON.parse(ledger.trim()) as Record<string, unknown>;
    expect(stored.artifactBundle).toBeUndefined();
    expect(stored.artifactBundleRef).toBeTruthy();

    const records = await readExperimentRecords(stateRoot);
    const recent = await readRecentExperimentRecords(stateRoot, 1);
    expect(records).toHaveLength(1);
    expect(recent[0]?.candidateId).toBe("cand-compact");
  });

  test("appendExperimentRecord separates local backtest artifacts from external bundle refs", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-jsonl-tv-ref-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");
    const candidatePath = await writeCandidate(root, "cand-tv-ref");
    const localBacktestPath = path.join(root, "local-backtest.json");
    await writeFile(
      localBacktestPath,
      `${JSON.stringify(createArtifactBundle(), null, 2)}\n`,
      "utf8",
    );
    const tvBundle = {
      ...createArtifactBundle(),
      rawReportHash: "tv-raw-hash",
      strategy: {
        ...createArtifactBundle().strategy,
        netProfitPercent: 9.1,
      },
    };

    const record = await appendExperimentRecord(stateRoot, {
      runId: "run-1",
      iteration: 2,
      candidateId: "cand-tv-ref",
      parentCandidateId: null,
      branchId: "main",
      acceptedHeadCandidateId: null,
      baselineCandidateId: null,
      candidatePath,
      candidateHash: "candidate-hash",
      candidateScore: 0.61,
      decision: "tv_verified",
      status: "verified_diverged",
      artifactBundle: tvBundle,
      artifactPaths: {
        backtestArtifact: localBacktestPath,
      },
    });

    const refPath = record.artifactBundleRef?.path;
    expect(refPath).toBeTruthy();
    if (!refPath) {
      throw new Error("missing artifact bundle ref path");
    }
    expect(refPath).not.toBe(localBacktestPath);
    expect(record.artifactPaths?.backtestArtifact).toBe(refPath);
    expect(record.artifactPaths?.artifactBundle).toBe(refPath);
    expect(record.artifactPaths?.localBacktestArtifact).toBe(localBacktestPath);
    const storedBundle = JSON.parse(await readFile(refPath, "utf8")) as ArtifactBundle;
    expect(storedBundle.rawReportHash).toBe("tv-raw-hash");
  });

  test("compactExperimentLedger rewrites legacy heavy records and preserves validation", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-jsonl-migrate-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");
    const paths = resolveKnowledgePaths(stateRoot);
    const candidatePath = await writeCandidate(root, "cand-heavy");
    await ensureStateRoot(stateRoot);

    await writeFile(
      paths.experimentsPath,
      `${JSON.stringify({
        runId: "run-1",
        iteration: 1,
        candidateId: "cand-heavy",
        parentCandidateId: null,
        branchId: "main",
        acceptedHeadCandidateId: null,
        baselineCandidateId: null,
        candidatePath,
        candidateHash: "candidate-hash",
        candidateScore: 0.41,
        decision: "local_candidate_eligible",
        status: "evaluated",
        artifactBundle: createArtifactBundle(),
        recordMeta: {
          schemaVersion: "experiment/v3",
          recordHash: "legacy-hash",
          candidateHash: "candidate-hash",
          baselineHash: null,
          artifactBundleHash: null,
          pipelineVersion: "test",
        },
        recordedAt: "2026-05-01T00:00:00.000Z",
      })}\n`,
      "utf8",
    );

    const dryRun = await compactExperimentLedger(stateRoot, { dryRun: true });
    expect(dryRun.artifactBundlesStripped).toBe(1);
    expect(dryRun.compactedBytes).toBeGreaterThan(0);

    const result = await compactExperimentLedger(stateRoot, { backup: true });
    expect(result.backupPath).toBeTruthy();
    await expect(access(result.backupPath ?? "")).resolves.toBeUndefined();

    const compacted = await readExperimentRecords(stateRoot);
    expect(compacted[0]?.artifactBundle).toBeUndefined();
    expect(compacted[0]?.artifactBundleRef?.path).toBeTruthy();
    expect(compacted[0]?.recordMeta?.artifactBundleHash).toBeTruthy();
    expect((await validateLedger(stateRoot)).ok).toBe(true);
  });

  test("compactExperimentLedger normalizes existing bundle refs with local backtest aliases", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-jsonl-ref-normalize-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");
    const paths = resolveKnowledgePaths(stateRoot);
    const candidatePath = await writeCandidate(root, "cand-ref-normalize");
    const localBacktestPath = path.join(root, "local-backtest.json");
    const bundleRefPath = path.join(
      paths.artifactDir,
      "experiment-bundles",
      "3-cand-ref-normalize-tv-hash.json",
    );
    await ensureStateRoot(stateRoot);
    await mkdir(path.dirname(bundleRefPath), { recursive: true });
    await writeFile(
      localBacktestPath,
      `${JSON.stringify(createArtifactBundle(), null, 2)}\n`,
      "utf8",
    );
    await writeFile(
      bundleRefPath,
      `${JSON.stringify(
        {
          ...createArtifactBundle(),
          rawReportHash: "tv-raw-hash",
        },
        null,
        2,
      )}\n`,
      "utf8",
    );
    await writeFile(
      paths.experimentsPath,
      `${JSON.stringify({
        runId: "run-1",
        iteration: 3,
        candidateId: "cand-ref-normalize",
        parentCandidateId: null,
        branchId: "main",
        acceptedHeadCandidateId: null,
        baselineCandidateId: null,
        candidatePath,
        candidateHash: "candidate-hash",
        candidateScore: 0.41,
        decision: "tv_verified",
        status: "verified_diverged",
        artifactBundleRef: {
          path: bundleRefPath,
          hash: "tv-hash",
          storage: "file",
          schemaVersion: "artifact-bundle/v1",
        },
        artifactPaths: {
          backtestArtifact: localBacktestPath,
        },
        recordMeta: {
          schemaVersion: "experiment/v4",
          recordHash: "legacy-hash",
          candidateHash: "candidate-hash",
          baselineHash: null,
          artifactBundleHash: "tv-hash",
          pipelineVersion: "test",
        },
        recordedAt: "2026-05-01T00:00:00.000Z",
      })}\n`,
      "utf8",
    );

    await compactExperimentLedger(stateRoot);

    const records = await readExperimentRecords(stateRoot);
    expect(records[0]?.artifactPaths?.backtestArtifact).toBe(bundleRefPath);
    expect(records[0]?.artifactPaths?.artifactBundle).toBe(bundleRefPath);
    expect(records[0]?.artifactPaths?.localBacktestArtifact).toBe(localBacktestPath);
  });
});

describe("autonomous iteration learning records", () => {
  test("append and tail-read compact iteration learning records", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-iteration-records-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");

    await appendAutonomousIterationRecord(stateRoot, {
      runId: "run-1",
      iteration: 1,
      acceptedHeadCandidateId: "cand-head",
      candidateId: "cand-a",
      briefHash: "brief-a",
      repairMode: "exploration_breakout",
      routeId: "time_boxed_event_rotation",
      variantId: null,
      hypothesis: "Try a broader event window.",
      methodSummary: "Use wide post-event windows and simple time exits.",
      resultSummary: "decision=local_candidate_rejected | trades=31 | oosTrades=7",
      lessonForNextHypothesis:
        "Do not repeat sparse event windows without a materially broader entry.",
      decision: "local_candidate_rejected",
      score: 0.42,
      eligible: false,
      totalTrades: 31,
      oosTrades: 7,
      postFeeNetProfitPercent: 2.1,
      oosPostFeeNetProfitPercent: 1.4,
      blockingReasons: ["oos_trade_count_fail: observed 7 below 15"],
      championChanged: false,
      activeChampionCandidateId: "cand-head",
    });
    await appendAutonomousIterationRecord(stateRoot, {
      runId: "run-2",
      iteration: 2,
      acceptedHeadCandidateId: "cand-head",
      candidateId: "cand-b",
      briefHash: "brief-b",
      repairMode: "exploration_breakout",
      routeId: "event_reclaim_reversal",
      variantId: null,
      hypothesis: "Try a reclaim route with broad participation.",
      methodSummary: "Use reclaim event and simple exits.",
      resultSummary: "decision=local_candidate_eligible | trades=755",
      lessonForNextHypothesis:
        "Eligible but not promoted; preserve trade count and improve OOS score.",
      decision: "local_candidate_eligible",
      score: 0.49,
      eligible: true,
      totalTrades: 755,
      oosTrades: 120,
      postFeeNetProfitPercent: 3.4,
      oosPostFeeNetProfitPercent: 0.8,
      blockingReasons: [],
      championChanged: false,
      activeChampionCandidateId: "cand-head",
    });

    const all = await readAutonomousIterationRecords(stateRoot);
    const recent = await readRecentAutonomousIterationRecords(stateRoot, 1);

    expect(all).toHaveLength(2);
    expect(recent).toHaveLength(1);
    expect(recent[0]?.candidateId).toBe("cand-b");
  });
});
