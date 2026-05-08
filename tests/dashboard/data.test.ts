import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { describe, expect, test } from "vitest";

import { buildDashboardStatus } from "../../src/dashboard/data.js";
import { resolveKnowledgePaths } from "../../src/state/knowledge-paths.js";

describe("buildDashboardStatus", () => {
  test("exposes verified autoresearch readiness fields from the autonomous summary", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-dashboard-status-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");
    const paths = resolveKnowledgePaths(stateRoot);
    await mkdir(paths.viewsDir, { recursive: true });
    await mkdir(paths.ledgerDir, { recursive: true });
    await mkdir(paths.runtimeDir, { recursive: true });
    await mkdir(paths.artifactDir, { recursive: true });
    await writeFile(
      paths.autonomousStateSummaryPath,
      JSON.stringify({
        activeChampionCandidateId: "cand-verified",
        activeChampionScore: 0.72,
        activeChampionDecision: "tv_verified",
        verifiedPromotionCandidateId: "cand-verified",
        verifiedPromotionScore: 0.72,
        parityStatus: "matched",
        parityStatusCounts: { matched: 1, major_drift: 1 },
        walkForwardStatus: "passed",
        walkForwardStatusCounts: { passed: 1, failed: 1 },
        researchStageCounts: {
          champion: 1,
          calibration_queued: 2,
          quarantined: 1,
        },
        quarantineCount: 1,
        trialPressure: {
          totalCandidatesTried: 42,
          familyTrials: 7,
          minimumRequiredScore: 0.62,
        },
        branchBudget: {
          totalBranches: 2,
          entries: [
            {
              branchKind: "champion_exploit",
              targetPct: 50,
              actualCount: 1,
              actualPct: 50,
              deficitPct: 0,
            },
          ],
        },
      }),
      "utf8",
    );
    await writeFile(
      paths.tvCalibrationQueuePath,
      JSON.stringify({
        entries: [
          {
            candidateId: "cand-queued",
            derivedStatus: "pending",
            queueState: "queued",
            queueReason: "novelty_frontier_candidate",
            recordedAt: "2026-04-27T00:00:00.000Z",
          },
        ],
      }),
      "utf8",
    );
    await writeFile(
      paths.localTvDivergencePath,
      JSON.stringify({
        entries: [
          {
            candidateId: "cand-drift",
            localConfidenceAfter: 0.6,
            parity: {
              status: "major_drift",
              netProfitPctDelta: -20,
              tradeCountDelta: -120,
            },
            recordedAt: "2026-04-27T01:00:00.000Z",
          },
        ],
      }),
      "utf8",
    );
    await writeFile(
      paths.experimentsPath,
      [
        {
          iteration: 1,
          candidateId: "cand-return-a",
          decision: "local_candidate_eligible",
          recordedAt: "2026-04-27T02:00:00.000Z",
          candidateScore: 0.61,
          testerMetrics: {
            netProfitPercent: 1,
            profitFactor: 1.2,
            maxStrategyDrawdownPercent: 8,
            percentProfitable: 51,
            totalTrades: 80,
            avgTradePercent: 0.05,
          },
        },
        {
          iteration: 2,
          candidateId: "cand-return-b",
          decision: "local_candidate_eligible",
          recordedAt: "2026-04-27T03:00:00.000Z",
          candidateScore: 0.64,
          testerMetrics: {
            netProfitPercent: 5,
            profitFactor: 1.35,
            maxStrategyDrawdownPercent: 7,
            percentProfitable: 53,
            totalTrades: 90,
            avgTradePercent: 0.08,
          },
        },
        {
          iteration: 3,
          candidateId: "cand-return-c",
          decision: "local_candidate_eligible",
          recordedAt: "2026-04-27T04:00:00.000Z",
          candidateScore: 0.59,
          testerMetrics: {
            netProfitPercent: -3,
            profitFactor: 0.92,
            maxStrategyDrawdownPercent: 12,
            percentProfitable: 47,
            totalTrades: 75,
            avgTradePercent: -0.04,
          },
        },
      ].map((record) => JSON.stringify(record)).join("\n") + "\n",
      "utf8",
    );

    const status = await buildDashboardStatus({
      workspaceRoot: root,
      stateRoot,
      autoProcessCalibration: false,
      promotionVerificationExecutor: "none",
      now: new Date("2026-04-28T00:00:00.000Z"),
    });

    expect(status.score.activeChampion).toEqual(
      expect.objectContaining({
        candidateId: "cand-verified",
        score: 0.72,
        decision: "tv_verified",
      }),
    );
    expect(status.verifiedAutoresearch).toEqual(
      expect.objectContaining({
        verifiedPromotionCandidateId: "cand-verified",
        verifiedPromotionScore: 0.72,
        parityStatus: "matched",
        walkForwardStatus: "passed",
        quarantineCount: 1,
      }),
    );
    expect(status.verifiedAutoresearch.researchStageCounts.champion).toBe(1);
    expect(status.verifiedAutoresearch.parityStatusCounts.major_drift).toBe(1);
    expect(status.verifiedAutoresearch.walkForwardStatusCounts.failed).toBe(1);
    expect(status.verifiedAutoresearch.trialPressure?.familyTrials).toBe(7);
    expect(status.verifiedAutoresearch.branchBudget?.totalBranches).toBe(2);
    expect(status.operatorBrief.mode).toBe("local_only");
    expect(status.operatorBrief.headline).toContain("TradingView는 수동");
    expect(status.operatorBrief.summary).toContain("수익률은 -3.00%");
    expect(status.score.returnProfile.latestPercent).toBe(-3);
    expect(status.score.returnProfile.recentBestPercent).toBe(5);
    expect(status.score.returnProfile.recentBestCandidateId).toBe("cand-return-b");
    expect(status.score.returnProfile.recentAveragePercent).toBeCloseTo(1);
    expect(status.externalValidation.pendingCount).toBe(1);
    expect(status.externalValidation.pendingCandidateIds).toEqual(["cand-queued"]);
    expect(status.externalValidation.latestDivergence).toEqual(
      expect.objectContaining({
        candidateId: "cand-drift",
        parityStatus: "major_drift",
        netProfitDelta: -20,
      }),
    );
  });

  test("exposes symbol mode context and matching strategy review directive", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-dashboard-mode-"));
    const stateRoot = path.join(root, "state", "btc-15m-autoresearch");
    const paths = resolveKnowledgePaths(stateRoot);
    await mkdir(paths.viewsDir, { recursive: true });
    await mkdir(path.dirname(paths.strategyReviewBoardPath), { recursive: true });
    await mkdir(paths.ledgerDir, { recursive: true });
    await mkdir(paths.runtimeDir, { recursive: true });
    await mkdir(paths.artifactDir, { recursive: true });
    await writeFile(
      path.join(paths.runtimeDir, "autonomous-loop-heartbeat.json"),
      JSON.stringify({
        pid: 12345,
        status: "running",
        researchSymbol: "BTCUSD",
        chartSymbol: "BTCUSD",
        chartTimeframe: "15",
        goalMode: "repair",
      }),
      "utf8",
    );
    await writeFile(
      paths.strategyReviewBoardPath,
      JSON.stringify({
        targets: [
          {
            targetId: "btc-15m-af",
            symbol: "BTCUSD",
            timeframe: "15",
            goalMode: "repair",
            latestReview: {
              reviewDecision: "repair_near_miss",
              confidence: 0.82,
              reviewMode: "deterministic",
              candidateId: "cand-near",
              mutationDirective: {
                branchKindBias: "near_miss_repair",
                parentCandidateId: "cand-near",
                requiredChanges: ["recover_trade_density"],
                forbiddenPatterns: ["broad_rewrite"],
                suppressedFamilies: ["family-a"],
                validationFocus: ["walk_forward"],
                reason: "repair repeated OOS failure",
              },
              recordedAt: "2026-05-08T00:00:00.000Z",
            },
            suppressedFamilies: ["family-a"],
            nextMutationFocus: ["recover_trade_density", "walk_forward"],
          },
        ],
        recentReviews: [],
      }),
      "utf8",
    );

    const status = await buildDashboardStatus({
      workspaceRoot: root,
      stateRoot,
      autoProcessCalibration: false,
      promotionVerificationExecutor: "none",
      now: new Date("2026-05-08T00:00:00.000Z"),
    });

    expect(status.researchMode).toEqual(
      expect.objectContaining({
        symbol: "BTCUSD",
        timeframe: "15",
        goalMode: "repair",
        goalProfileId: "repair/v1",
        branchKindBias: "near_miss_repair",
        criterionDirectiveSeed: "oos_robustness",
        calibrationPolicy: "target_default",
      }),
    );
    expect(status.researchMode.strategyReviewFocus).toContain("near_miss");
    expect(status.strategyReview).toEqual(
      expect.objectContaining({
        latestDecision: "repair_near_miss",
        latestCandidateId: "cand-near",
        confidence: 0.82,
        branchKindBias: "near_miss_repair",
        parentCandidateId: "cand-near",
        reason: "repair repeated OOS failure",
        suppressedFamilies: ["family-a"],
        nextMutationFocus: ["recover_trade_density", "walk_forward"],
      }),
    );
    expect(status.strategyReview.requiredChanges).toEqual(["recover_trade_density"]);
    expect(status.strategyReview.validationFocus).toEqual(["walk_forward"]);
  });
});
