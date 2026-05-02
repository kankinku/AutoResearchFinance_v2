import { describe, expect, test } from "vitest";

import { parseMutationResponse } from "../../src/mutation/parser.js";

describe("parseMutationResponse", () => {
  test("parses structured JSON with pine script and inventory", () => {
    const response = JSON.stringify({
      candidateSummary: "EMA and RSI entry refinement",
      nextMutationHints: ["tighten risk exit", "test volatility filter"],
      pineScript: "//@version=5\nstrategy('Test', overlay=true)\n",
      inventory: [
        {
          conditionId: "entry-ema-cross",
          role: "entry",
          summary: "Fast EMA above slow EMA",
          pineLineHints: [8, 12],
        },
      ],
    });

    const parsed = parseMutationResponse(response);

    expect(parsed.candidateSummary).toBe("EMA and RSI entry refinement");
    expect(parsed.inventory[0]?.conditionId).toBe("entry-ema-cross");
    expect(parsed.pineScript).toContain("strategy('Test'");
  });

  test("accepts alternate pine-only payloads and infers missing fields", () => {
    const parsed = parseMutationResponse(
      JSON.stringify({
        pine: [
          "//@version=5",
          "strategy('Alt Test', overlay=true)",
          "trendUp = close > ta.ema(close, 200)",
          "longEntry = trendUp and ta.rsi(close, 14) > 55",
          "if longEntry",
          "    strategy.entry('Long', strategy.long)",
        ].join("\n"),
      }),
    );

    expect(parsed.candidateSummary).toContain("Alt Test");
    expect(parsed.inventory.length).toBeGreaterThan(0);
    expect(parsed.inventory[0]?.pineLineHints.length).toBeGreaterThan(0);
    expect(parsed.pineScript).toContain("strategy('Alt Test'");
  });

  test("rejects payloads that omit Pine code entirely", () => {
    expect(() => parseMutationResponse(JSON.stringify({ candidateSummary: "invalid" }))).toThrow(
      /pineScript|Pine code/i,
    );
  });
});
