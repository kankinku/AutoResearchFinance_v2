import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { describe, expect, test } from "vitest";

import {
  DEFAULT_RESEARCH_TARGET_ID,
  loadAllResearchTargets,
  loadResearchTarget,
  resolveLegacySharedStateRoot,
  resolveTargetStateRoot,
} from "../../src/config/target-registry.js";

describe("target registry", () => {
  test("loads the default qqq 120 af research target", async () => {
    const projectRoot = process.cwd();
    const target = loadResearchTarget({
      projectRoot,
      targetId: DEFAULT_RESEARCH_TARGET_ID,
    });

    expect(target.id).toBe("qqq-120m-af");
    expect(target.symbol).toBe("QQQ");
    expect(target.timeframe).toBe("120");
    expect(target.primaryExecutor).toBe("local-af-backtest");

    const raw = await readFile(
      path.join(projectRoot, "config", "targets", "qqq-120m-af.json"),
      "utf8",
    );
    expect(raw).toContain("\"objectivePolicyFile\": \"objective.qqq-120m.json\"");
  });

  test("loads the second dry-run research target", async () => {
    const projectRoot = process.cwd();
    const target = loadResearchTarget({
      projectRoot,
      targetId: "qqq-60m-af-dryrun",
    });

    expect(target.id).toBe("qqq-60m-af-dryrun");
    expect(target.symbol).toBe("QQQ");
    expect(target.timeframe).toBe("60");
    expect(target.primaryExecutor).toBe("local-af-backtest");

    const raw = await readFile(
      path.join(projectRoot, "config", "targets", "qqq-60m-af-dryrun.json"),
      "utf8",
    );
    expect(raw).toContain("\"objectivePolicyFile\": \"objective.qqq-60m.json\"");
  });

  test("invalid target id fails with a clear diagnostic", () => {
    expect(() =>
      loadResearchTarget({
        projectRoot: process.cwd(),
        targetId: "missing-target",
      }),
    ).toThrowError(/Unable to load research target config for missing-target/i);
  });

  test("loads all configured research targets", () => {
    const targets = loadAllResearchTargets({
      projectRoot: process.cwd(),
    });

    expect(targets.map((target) => target.id)).toEqual(
      expect.arrayContaining(["btc-15m-af", "qqq-60m-af-dryrun", "qqq-120m-af"]),
    );
  });

  test("resolves target-scoped state roots separately from legacy shared state", () => {
    const workspaceRoot = path.join("C:", "af-workspace");

    expect(
      resolveTargetStateRoot({
        workspaceRoot,
        targetId: "btc-15m-af",
      }),
    ).toBe(path.join(workspaceRoot, "state", "targets", "btc-15m-af", "pi-autoresearch"));
    expect(resolveLegacySharedStateRoot(workspaceRoot)).toBe(
      path.join(workspaceRoot, "state", "pi-autoresearch"),
    );
  });

  test("workspace target definitions override project definitions when loading all", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-target-registry-"));
    const projectRoot = path.join(root, "project");
    const workspaceRoot = path.join(root, "workspace");
    const projectTargetDir = path.join(projectRoot, "config", "targets");
    const workspaceTargetDir = path.join(workspaceRoot, "config", "targets");
    await mkdir(projectTargetDir, { recursive: true });
    await mkdir(workspaceTargetDir, { recursive: true });

    const baseTarget = {
      id: "shared-af",
      symbol: "QQQ",
      timeframe: "120",
      strategyFamily: "AF",
      primaryExecutor: "local-af-backtest",
      externalCalibrationExecutor: "tradingview",
      objectivePolicyFile: "objective.project.json",
      noveltyPolicy: "novelty.project.json",
      calibrationPolicy: "calibration.project.json",
    };
    await writeFile(
      path.join(projectTargetDir, "shared-af.json"),
      JSON.stringify(baseTarget),
    );
    await writeFile(
      path.join(workspaceTargetDir, "shared-af.json"),
      JSON.stringify({
        ...baseTarget,
        symbol: "BTC",
        timeframe: "15",
        objectivePolicyFile: "objective.workspace.json",
      }),
    );

    const targets = loadAllResearchTargets({ projectRoot, workspaceRoot });

    expect(targets).toHaveLength(1);
    expect(targets[0]).toMatchObject({
      id: "shared-af",
      symbol: "BTC",
      timeframe: "15",
      objectivePolicyFile: "objective.workspace.json",
    });
  });
});
