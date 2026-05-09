import { mkdtemp, readdir, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { describe, expect, test } from "vitest";

import { createCliMonitor } from "../../src/cli/monitor.js";
import { DEFAULT_RESEARCH_TARGET_ID, resolveTargetStateRoot } from "../../src/config/target-registry.js";
import { resolveKnowledgePaths } from "../../src/state/knowledge-paths.js";

describe("createCliMonitor", () => {
  test("emits structured stage logs and persists JSONL traces", async () => {
    const workspaceRoot = await mkdtemp(path.join(tmpdir(), "af-monitor-"));
    const output: string[] = [];
    const monitor = await createCliMonitor({
      workspaceRoot,
      commandName: "iterate",
      sink: (line) => output.push(line),
    });

    await monitor.log("iteration.start", "Starting iteration", {
      iteration: 1,
      hypothesis: "Improve trade count",
    });
    await monitor.log("mutation.brief", "Mutation brief ready", {
      recentFailures: ["hard_gate_fail"],
    });
    await monitor.close();

    expect(output).toHaveLength(2);
    expect(output[0]).toContain("반복을 시작합니다.");
    expect(output[0]).toContain("iteration: 1");
    expect(output[0]).not.toContain('{"');
    expect(output[0]).toMatch(/\| \d{4}-\d{2}-\d{2}T/);
    expect(output[1]).toContain("변형 브리프를 준비했습니다.");
    expect(output[1]).toContain("최근 실패: hard_gate_fail");
    expect(output[1]).not.toContain('{"');
    expect(output[1]).toMatch(/\| \d{4}-\d{2}-\d{2}T/);

    const tracesDir = resolveKnowledgePaths(
      resolveTargetStateRoot({
        workspaceRoot,
        targetId: DEFAULT_RESEARCH_TARGET_ID,
      }),
    ).tracesDir;
    const files = await readdir(tracesDir);
    expect(files).toHaveLength(1);

    const traceLines = (await readFile(path.join(tracesDir, files[0]!), "utf8"))
      .trim()
      .split("\n")
      .map((line) => JSON.parse(line));

    expect(traceLines[0]?.event).toBe("iteration.start");
    expect(traceLines[1]?.details?.recentFailures).toEqual(["hard_gate_fail"]);
  });

  test("prints a task banner and includes task number in subsequent logs", async () => {
    const workspaceRoot = await mkdtemp(path.join(tmpdir(), "af-monitor-task-"));
    const output: string[] = [];
    const monitor = await createCliMonitor({
      workspaceRoot,
      commandName: "iterate",
      sink: (line) => output.push(line),
    });

    await monitor.setTask(1);
    await monitor.log("iterate.loop", "Running iteration", {
      currentIteration: 1,
      totalIterations: 3,
    });
    await monitor.close();

    expect(output[0]).toBe("-------task 01----------");
    expect(output[1]).toContain("task 01 |");
    expect(output[1]).toContain("진행: 1/3");
    expect(output[1]).not.toContain('{"');
    expect(output[1]).toMatch(/\| \d{4}-\d{2}-\d{2}T/);
  });

  test("stores traces under the explicit temp state root when provided", async () => {
    const workspaceRoot = await mkdtemp(path.join(tmpdir(), "af-monitor-workspace-"));
    const stateRoot = path.join(await mkdtemp(path.join(tmpdir(), "af-monitor-state-")), "state");
    const monitor = await createCliMonitor({
      workspaceRoot,
      stateRoot,
      commandName: "iterate",
    });

    await monitor.log("iteration.start", "Starting iteration", { iteration: 1 });
    await monitor.close();

    const knowledgePaths = resolveKnowledgePaths(stateRoot);
    const files = await readdir(knowledgePaths.tracesDir);

    expect(monitor.tracePath.startsWith(knowledgePaths.tracesDir)).toBe(true);
    expect(files).toHaveLength(1);
    await expect(
      readFile(path.join(knowledgePaths.tracesDir, files[0]!), "utf8"),
    ).resolves.toContain("\"event\":\"iteration.start\"");
  });
});
