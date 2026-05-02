import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { describe, expect, test } from "vitest";

import {
  ensureActiveSeedBaseline,
  loadSeedStrategyReference,
} from "../../src/research/seed-strategy.js";
import { initializeWorkspace } from "../../src/research/workspace.js";

describe("seed strategy", () => {
  test("copies the curated seed into baseline when workspace initializes", async () => {
    const workspace = await mkdtemp(path.join(tmpdir(), "af-seed-"));

    await initializeWorkspace(workspace);
    await ensureActiveSeedBaseline(workspace);

    const baseline = await readFile(
      path.join(workspace, "strategies", "source", "baseline.pine"),
      "utf8",
    );
    expect(baseline).toContain('strategy("AF Seed 01"');
  });

  test("loads a structured seed strategy reference", async () => {
    const workspace = await mkdtemp(path.join(tmpdir(), "af-seed-ref-"));

    await initializeWorkspace(workspace);
    const seed = await loadSeedStrategyReference(workspace);

    expect(seed.candidateId).toBe("seed_primary");
    expect(seed.studyTitle).toContain("AF Seed 01");
    expect(seed.summary.length).toBeGreaterThan(0);
    expect(seed.candidateHash.length).toBeGreaterThan(10);
  });
});
