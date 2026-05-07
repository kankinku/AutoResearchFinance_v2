import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { describe, expect, test } from "vitest";

import { type ArtifactBundle } from "../../src/contracts/types.js";
import {
  buildArtifactRetentionReport,
  buildSystemHealthReport,
  cleanupRuntime,
} from "../../src/state/operational-reports.js";
import { appendExperimentRecord } from "../../src/state/jsonl-store.js";

function createArtifactBundle(): ArtifactBundle {
  return {
    strategy: {
      netProfitPercent: 1,
      postFeeNetProfitPercent: -1,
      profitFactor: 0.8,
      maxStrategyDrawdownPercent: 12,
      percentProfitable: 40,
      totalTrades: 8,
      avgTradePercent: -0.1,
    },
    trades: [],
    equity: {
      available: false,
      unavailableReason: "test",
      pointsAvailable: false,
      pointCount: 0,
      finalEquity: null,
      maxDrawdownPercent: null,
      points: [],
    },
    rawReportHash: null,
    state: {},
  };
}

describe("operational reports", () => {
  test("builds report-first artifact retention entries without deleting artifacts", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-retention-report-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");
    const candidatePath = path.join(root, "cand-retention.pine");
    await writeFile(candidatePath, "//@version=5\nstrategy('retention')\n", "utf8");

    const appended = await appendExperimentRecord(stateRoot, {
      runId: "run-retention",
      iteration: 1,
      candidateId: "cand-retention",
      parentCandidateId: null,
      branchId: "main",
      acceptedHeadCandidateId: null,
      baselineCandidateId: "seed_primary",
      candidatePath,
      candidateHash: "cand-retention-hash",
      candidateScore: -0.2,
      decision: "hard_gate_fail",
      status: "evaluated",
      artifactBundle: createArtifactBundle(),
    });

    const report = await buildArtifactRetentionReport({ stateRoot });

    expect(report.summary.totalArtifacts).toBeGreaterThan(0);
    expect(report.entries[0].retentionClass).toBe("purge_candidate");
    expect(report.entries[0].compactArtifact.candidateId).toBe("cand-retention");
    expect(await readFile(appended.artifactBundleRef?.path ?? "", "utf8")).toContain(
      "strategy",
    );
  });

  test("keeps TradingView weights as manual review and deletes nothing in dry-run", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-runtime-cleanup-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");
    const profileRoot = path.join(
      stateRoot,
      "runtime",
      "tradingview-web-profile",
      "Default",
    );
    const cacheDir = path.join(profileRoot, "Cache");
    const weightsPath = path.join(profileRoot, "OptGuideOnDeviceModel", "weights.bin");
    await mkdir(cacheDir, { recursive: true });
    await mkdir(path.dirname(weightsPath), { recursive: true });
    await writeFile(path.join(cacheDir, "cache.bin"), "cache", "utf8");
    await writeFile(weightsPath, "weights", "utf8");

    const report = await cleanupRuntime({
      stateRoot,
      target: "tradingview-cache",
      dryRun: true,
    });

    expect(report.dryRun).toBe(true);
    expect(report.deletedCount).toBe(0);
    expect(report.candidates.some((entry) => entry.action === "manual_review")).toBe(true);
    expect(await readFile(weightsPath, "utf8")).toBe("weights");
    expect(await readFile(path.join(cacheDir, "cache.bin"), "utf8")).toBe("cache");
  });

  test("reports heartbeat read errors instead of treating them as stale", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-health-report-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");
    const heartbeatPath = path.join(
      stateRoot,
      "runtime",
      "autonomous-loop-heartbeat.json",
    );
    await mkdir(path.dirname(heartbeatPath), { recursive: true });
    await writeFile(heartbeatPath, "{", "utf8");

    const report = await buildSystemHealthReport({ stateRoot });

    expect(report.heartbeat.status).toBe("read_error");
    expect(report.heartbeat.error).toBeTruthy();
  });
});
