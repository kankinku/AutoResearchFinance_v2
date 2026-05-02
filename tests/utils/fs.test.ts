import { access, mkdtemp, readFile, utimes, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { describe, expect, test } from "vitest";

import { appendJsonlAtomic, readJsonl, scanJsonlTolerant } from "../../src/utils/fs.js";

describe("appendJsonlAtomic", () => {
  test("cleans up stale lock files before appending", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-jsonl-lock-"));
    const filePath = path.join(root, "experiments.jsonl");
    const lockPath = `${filePath}.lock`;
    await writeFile(lockPath, JSON.stringify({ pid: 123, acquiredAt: "2026-04-01T00:00:00.000Z" }), "utf8");
    const staleAt = new Date(Date.now() - 60_000);
    await utimes(lockPath, staleAt, staleAt);

    await appendJsonlAtomic(filePath, { candidateId: "cand-1" });

    await expect(access(lockPath)).rejects.toThrow();
    await expect(readJsonl<{ candidateId: string }>(filePath)).resolves.toEqual([
      { candidateId: "cand-1" },
    ]);
  });

  test("serializes concurrent appends without corrupting JSONL lines", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-jsonl-concurrent-"));
    const filePath = path.join(root, "experiments.jsonl");

    await Promise.all(
      Array.from({ length: 20 }, (_, index) =>
        appendJsonlAtomic(filePath, { candidateId: `cand-${index}` }),
      ),
    );

    const contents = await readFile(filePath, "utf8");
    const lines = contents
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);

    expect(lines).toHaveLength(20);
    expect(() => lines.forEach((line) => JSON.parse(line))).not.toThrow();
  });

  test("reports partial tail corruption without throwing", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-jsonl-tail-"));
    const filePath = path.join(root, "experiments.jsonl");
    await writeFile(
      filePath,
      `${JSON.stringify({ candidateId: "cand-1" })}\n{"candidateId":"cand-2"`,
      "utf8",
    );

    const result = await scanJsonlTolerant<{ candidateId: string }>(filePath);

    expect(result.records).toEqual([{ candidateId: "cand-1" }]);
    expect(result.issues).toEqual([
      expect.objectContaining({
        kind: "partial_tail",
        lineNumber: 2,
      }),
    ]);
  });

  test("reports malformed middle lines and keeps valid later records", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-jsonl-middle-"));
    const filePath = path.join(root, "experiments.jsonl");
    await writeFile(
      filePath,
      [
        JSON.stringify({ candidateId: "cand-1" }),
        '{"candidateId":',
        JSON.stringify({ candidateId: "cand-3" }),
        "",
      ].join("\n"),
      "utf8",
    );

    const result = await scanJsonlTolerant<{ candidateId: string }>(filePath);

    expect(result.records).toEqual([
      { candidateId: "cand-1" },
      { candidateId: "cand-3" },
    ]);
    expect(result.issues).toEqual([
      expect.objectContaining({
        kind: "malformed_json",
        lineNumber: 2,
      }),
    ]);
  });
});
