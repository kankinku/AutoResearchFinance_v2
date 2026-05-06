import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { describe, expect, test } from "vitest";

import {
  generateIndicatorArtifact,
  validateIndicatorPine,
} from "../../src/research/indicator-generator.js";
import { readIndicatorArtifactRecords } from "../../src/state/jsonl-store.js";
import { type MutationLlmClient } from "../../src/mutation/llm-client.js";

describe("indicator generator", () => {
  test("persists a valid Pine indicator artifact outside strategy ledgers", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-indicator-"));
    const stateRoot = path.join(root, "state", "pi-autoresearch");
    const llmClient: MutationLlmClient = {
      async generateMutation() {
        throw new Error("not used");
      },
      async generateIndicator() {
        return JSON.stringify({
          indicatorSummary: "Short-term top detector",
          nextSteps: ["Tune RSI threshold"],
          pineScript: [
            "//@version=5",
            "indicator(\"Short-Term Top Detector\", overlay=true)",
            "r = ta.rsi(close, 14)",
            "top = r > 70 and close < close[1]",
            "plotshape(top, title=\"Top\", style=shape.triangledown)",
            "alertcondition(top, title=\"Top alert\", message=\"Possible top\")",
          ].join("\n"),
        });
      },
      async generateConditionAblation() {
        throw new Error("not used");
      },
      async repairMutation() {
        throw new Error("not used");
      },
    };

    const result = await generateIndicatorArtifact({
      workspaceRoot: root,
      stateRoot,
      llmClient,
      goal: "단기 고점 확인",
    });

    expect(result.record.indicatorId).toMatch(/^ind-/);
    expect(result.record.pinePath).toContain(path.join("strategies", "indicators"));
    expect(await readFile(result.record.pinePath, "utf8")).toContain("indicator(");
    expect(await readIndicatorArtifactRecords(stateRoot)).toEqual([
      expect.objectContaining({
        indicatorId: result.record.indicatorId,
        goal: "단기 고점 확인",
        validationStatus: "valid",
      }),
    ]);
  });

  test("rejects strategy code in indicator mode", () => {
    expect(
      validateIndicatorPine(
        [
          "//@version=5",
          "strategy(\"Bad\", overlay=true)",
          "strategy.entry(\"L\", strategy.long)",
          "plot(close)",
        ].join("\n"),
      ),
    ).toEqual(expect.arrayContaining([
      expect.stringMatching(/strategy/i),
    ]));
  });
});
