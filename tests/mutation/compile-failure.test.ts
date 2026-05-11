import { describe, expect, test } from "vitest";

import {
  buildCompileFailureClassCounts,
  classifyCompileFailure,
  normalizeCompileFailureClasses,
} from "../../src/mutation/compile-failure.js";

describe("compile failure normalization", () => {
  test("maps representative compiler messages into stable classes", () => {
    expect(classifyCompileFailure("Undeclared identifier 'emaLen'")).toBe(
      "undeclared_identifier",
    );
    expect(
      classifyCompileFailure(
        "The 'strategy.entry' function does not have an argument with the name 'qty_percent'",
      ),
    ).toBe("qty_percent_argument");
    expect(
      classifyCompileFailure(
        "Could not find function or function reference 'ta.sum'",
      ),
    ).toBe("unsupported_ta_sum");
    expect(
      classifyCompileFailure(
        "Cannot modify global variable 'lastOrderBar' in function",
      ),
    ).toBe("function_mutates_global");
    expect(
      classifyCompileFailure("Strategy title is too long for the current executor"),
    ).toBe("title_too_long");
    expect(classifyCompileFailure("NA type cannot be assigned to variable")).toBe(
      "na_type_assignment",
    );
    expect(
      classifyCompileFailure(
        "You should not start a new statement with an indent (4 spaces or 1 tab)!",
      ),
    ).toBe("leading_indented_statement");
  });

  test("deduplicates classes across raw compiler strings", () => {
    expect(
      normalizeCompileFailureClasses([
        "Undeclared identifier 'emaLen'",
        "Undeclared identifier 'slotPct'",
        "Could not find function or function reference 'ta.sum'",
      ]),
    ).toEqual(["undeclared_identifier", "unsupported_ta_sum"]);
  });

  test("counts compile-fail classes across experiment records", () => {
    const counts = buildCompileFailureClassCounts([
      {
        runId: "run-1",
        iteration: 1,
        candidateId: "cand-1",
        parentCandidateId: null,
        branchId: "main",
        acceptedHeadCandidateId: null,
        baselineCandidateId: "seed",
        candidateScore: null,
        decision: "compile_fail",
        status: "compile_failed",
        compile: {
          ok: false,
          errors: [
            "Undeclared identifier 'emaLen'",
            "The 'strategy.entry' function does not have an argument with the name 'qty_percent'",
          ],
        },
      },
      {
        runId: "run-1",
        iteration: 2,
        candidateId: "cand-2",
        parentCandidateId: "cand-1",
        branchId: "main",
        acceptedHeadCandidateId: "cand-1",
        baselineCandidateId: "seed",
        candidateScore: null,
        decision: "compile_fail",
        status: "compile_failed",
        compile: {
          ok: false,
          errors: [
            "Undeclared identifier 'slotPct'",
            "You should not start a new statement with an indent (4 spaces or 1 tab)!",
          ],
        },
      },
    ]);

    expect(counts.undeclared_identifier).toBe(2);
    expect(counts.qty_percent_argument).toBe(1);
    expect(counts.leading_indented_statement).toBe(1);
  });
});
