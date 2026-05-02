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

    const status = await buildDashboardStatus({
      workspaceRoot: root,
      stateRoot,
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
  });
});
