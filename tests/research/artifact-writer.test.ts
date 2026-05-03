import { access, mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { describe, expect, test } from "vitest";

import { type ArtifactBundle } from "../../src/contracts/types.js";
import { writeIterationArtifacts } from "../../src/research/artifact-writer.js";

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
    trades: [],
    equity: {
      available: true,
      unavailableReason: null,
      pointsAvailable: true,
      pointCount: 0,
      finalEquity: 10050,
      maxDrawdownPercent: 2.1,
      points: [],
    },
    rawReportHash: "raw-hash",
    state: {
      source: "test",
    },
  };
}

describe("writeIterationArtifacts", () => {
  test("writes immutable objective artifacts and latest aliases", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-artifact-writer-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");

    const paths = await writeIterationArtifacts({
      workspaceRoot: root,
      stateRoot,
      candidateId: "cand-test",
      iteration: 7,
      artifactBundle: createArtifactBundle(),
      objectiveArtifact: {
        candidateId: "cand-test",
        score: 0.42,
      },
    });

    const objectivePath = paths.objectiveArtifact;
    const latestObjectivePath = paths.latestObjectiveArtifact;
    const backtestPath = paths.backtestArtifact;
    const latestBacktestPath = paths.latestBacktestArtifact;
    expect(objectivePath).toBeTruthy();
    expect(latestObjectivePath).toBeTruthy();
    expect(backtestPath).toBeTruthy();
    expect(latestBacktestPath).toBeTruthy();
    if (!objectivePath || !latestObjectivePath || !backtestPath || !latestBacktestPath) {
      throw new Error("missing artifact path");
    }

    expect(path.basename(objectivePath)).toBe("pi-loop-objective-07-cand-test.json");
    expect(path.basename(latestObjectivePath)).toBe("tester-pi-objective.json");
    expect(path.basename(backtestPath)).toBe("pi-loop-backtest-07-cand-test.json");
    expect(path.basename(latestBacktestPath)).toBe("tester-full-backtest.json");
    expect(objectivePath).not.toBe(latestObjectivePath);

    await expect(access(objectivePath)).resolves.toBeUndefined();
    await expect(access(latestObjectivePath)).resolves.toBeUndefined();
    await expect(access(backtestPath)).resolves.toBeUndefined();
    await expect(access(latestBacktestPath)).resolves.toBeUndefined();

    const objective = JSON.parse(await readFile(objectivePath, "utf8")) as {
      score?: number;
    };
    const latestObjective = JSON.parse(
      await readFile(latestObjectivePath, "utf8"),
    ) as {
      score?: number;
    };
    expect(objective.score).toBe(0.42);
    expect(latestObjective.score).toBe(0.42);
  });
});
