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
        'Cannot call "input.time" with argument "defval"="call "timestamp" (simple int)". An argument of "simple int" type was used but a "const int" is expected.',
      ),
    ).toBe("input_time_requires_const_defval");
    expect(
      classifyCompileFailure(
        "The structure is missing a local code block. Functions, conditional structures, and loops must include expressions that define their local scopes.",
      ),
    ).toBe("missing_local_code_block");
    expect(
      classifyCompileFailure(
        "A strategy must contain at least one of the following: any `strategy.*()` function that creates orders, any `plot*()` function, `barcolor()`, `bgcolor()`, `hline()`, or any drawing (line, label, box, table, polyline).",
      ),
    ).toBe("missing_pine_side_effect");
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
          errors: ["Undeclared identifier 'slotPct'"],
        },
      },
    ]);

    expect(counts.undeclared_identifier).toBe(2);
    expect(counts.qty_percent_argument).toBe(1);
    expect(counts.input_time_requires_const_defval).toBe(0);
    expect(counts.missing_local_code_block).toBe(0);
    expect(counts.missing_pine_side_effect).toBe(0);
  });
});
