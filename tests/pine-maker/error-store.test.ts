import { mkdtemp, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { describe, expect, test } from "vitest";

import {
  inspectPineMakerSource,
  recordPineMakerError,
  resolvePineMakerPaths,
} from "../../src/pine-maker/error-store.js";

describe("pine maker error store", () => {
  test("records TradingView compiler errors and feeds them into preflight checks", async () => {
    const workspace = await mkdtemp(path.join(os.tmpdir(), "af-pine-maker-"));
    const stateRoot = path.join(workspace, "state");
    const sourcePath = path.join(workspace, "candidate.pine");
    await writeFile(
      sourcePath,
      [
        "//@version=5",
        "strategy('Broken', overlay=true)",
        "backtestStartTime = input.time(timestamp(2023, 5, 31, 13, 30), 'backtestStartTime')",
        "strategy.entry('L', strategy.long, qty=1)",
      ].join("\n"),
      "utf8",
    );

    const recorded = await recordPineMakerError({
      stateRoot,
      targetId: "btc-15m-af",
      candidateId: "cand-test",
      sourcePath,
      errorText:
        'Cannot call "input.time" with argument "defval"="call "timestamp" (simple int)". An argument of "simple int" type was used but a "const int" is expected.',
    });
    const inspection = await inspectPineMakerSource({
      stateRoot,
      sourcePath,
      targetId: "btc-15m-af",
      candidateId: "cand-test",
    });

    expect(recorded.record.compileFailureClasses).toContain(
      "input_time_requires_const_defval",
    );
    expect(inspection.recentCompileFailureClasses).toContain(
      "input_time_requires_const_defval",
    );
    expect(inspection.inspection.blockingIssues.map((issue) => issue.code)).toContain(
      "input_time_timestamp_defval",
    );
    expect(resolvePineMakerPaths(stateRoot).errorsPath).toContain(
      path.join("runtime", "pine-maker", "compile-errors.jsonl"),
    );
  });
});
