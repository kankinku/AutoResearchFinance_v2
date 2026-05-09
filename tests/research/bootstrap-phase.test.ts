import { describe, expect, test } from "vitest";

import { resolveBootstrapSeedSpecPath } from "../../src/research/autonomous/bootstrap-phase.js";

describe("autonomous bootstrap phase", () => {
  test("resolves the BTC target-specific bootstrap baseline spec", async () => {
    const projectRoot = process.cwd();
    const resolved = await resolveBootstrapSeedSpecPath({
      projectRoot,
      workspaceRoot: projectRoot,
      targetId: "btc-15m-af",
    });

    expect(resolved).toMatch(/baseline\.btc-15m-af\.af-spec\.json$/);
  });

  test("falls back to the default bootstrap baseline spec", async () => {
    const projectRoot = process.cwd();
    const resolved = await resolveBootstrapSeedSpecPath({
      projectRoot,
      workspaceRoot: projectRoot,
      targetId: "qqq-120m-af",
    });

    expect(resolved).toMatch(/baseline\.af-spec\.json$/);
  });
});
