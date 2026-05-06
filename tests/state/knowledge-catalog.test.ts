import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { describe, expect, test } from "vitest";

import { initializeWorkspace } from "../../src/research/workspace.js";
import {
  auditKnowledgeTree,
  migrateLegacyKnowledgeLayout,
} from "../../src/state/knowledge-catalog.js";
import { resolveKnowledgePaths } from "../../src/state/knowledge-paths.js";

describe("knowledge catalog", () => {
  test("initializes layered knowledge directories and passes audit on a fresh workspace", async () => {
    const workspaceRoot = await mkdtemp(path.join(tmpdir(), "af-knowledge-"));

    await initializeWorkspace(workspaceRoot);

    const paths = resolveKnowledgePaths(path.join(workspaceRoot, "state", "pi-autoresearch"));
    const catalog = JSON.parse(await readFile(paths.knowledgeCatalogPath, "utf8"));
    const audit = await auditKnowledgeTree(workspaceRoot);

    expect(catalog.entries.some((entry: { id: string }) => entry.id === "ledger.experiments")).toBe(
      true,
    );
    expect(
      catalog.entries.some((entry: { id: string }) => entry.id === "evidence.qqq_2h_context"),
    ).toBe(true);
    expect(
      catalog.entries.some((entry: { id: string }) => entry.id === "ledger.research_knowledge"),
    ).toBe(true);
    expect(
      catalog.entries.some((entry: { id: string }) => entry.id === "ledger.indicator_artifacts"),
    ).toBe(true);
    expect(
      catalog.entries.some((entry: { id: string }) => entry.id === "views.research_summary"),
    ).toBe(true);
    expect(audit.ok).toBe(true);
    expect(audit.summary.legacyRootArtifacts).toEqual([]);
  });

  test("copies legacy flat files into the layered knowledge tree", async () => {
    const workspaceRoot = await mkdtemp(path.join(tmpdir(), "af-knowledge-migrate-"));
    const stateRoot = path.join(workspaceRoot, "state", "pi-autoresearch");

    await initializeWorkspace(workspaceRoot);
    await writeFile(path.join(stateRoot, "experiments.jsonl"), '{"candidateId":"legacy"}\n', "utf8");
    await writeFile(path.join(stateRoot, "leaderboard.json"), '{"legacy":true}\n', "utf8");

    const migration = await migrateLegacyKnowledgeLayout(workspaceRoot);
    const paths = resolveKnowledgePaths(stateRoot);

    expect(migration.copied).toContain("state/pi-autoresearch/ledger/experiments.jsonl");
    expect(await readFile(paths.experimentsPath, "utf8")).toContain('"candidateId":"legacy"');
    expect(migration.copied).not.toContain("state/pi-autoresearch/views/leaderboard.json");
  });
});
