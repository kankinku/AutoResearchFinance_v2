import { describe, expect, test } from "vitest";

import {
  ensureCandidateStudyTitle,
  extractStudyTitle,
} from "../../src/strategy-source/pine-study.js";

describe("pine-study", () => {
  test("extracts a Pine strategy title", () => {
    expect(
      extractStudyTitle("//@version=5\nstrategy('Baseline Alpha', overlay=true)\nplot(close)\n"),
    ).toBe("Baseline Alpha");
  });

  test("injects a candidate-specific study title for exact attach validation", () => {
    const result = ensureCandidateStudyTitle(
      "//@version=5\nstrategy('Baseline Alpha', overlay=true)\nplot(close)\n",
      "cand-12345678",
    );

    expect(result.studyTitle).toBe("Baseline Alpha [cand-12345678]");
    expect(result.source).toContain("strategy('Baseline Alpha [cand-12345678]'");
  });
});
