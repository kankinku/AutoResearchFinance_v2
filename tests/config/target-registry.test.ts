import { readFile } from "node:fs/promises";
import path from "node:path";

import { describe, expect, test } from "vitest";

import {
  DEFAULT_RESEARCH_TARGET_ID,
  loadResearchTarget,
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
});
