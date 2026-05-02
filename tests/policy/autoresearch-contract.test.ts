import { readFile } from "node:fs/promises";
import path from "node:path";

import { describe, expect, test } from "vitest";

import {
  EDITABLE_RESEARCH_PATHS,
  EVALUATION_FIREWALL_PATHS,
  assertEditableResearchPath,
} from "../../src/policy/autoresearch-contract.js";
import { parseMutationResponseStrict } from "../../src/mutation/parser.js";

const workspaceRoot = path.resolve(process.cwd());

const strategySpec = {
  version: "af-spec/v1" as const,
  name: "Policy Test Candidate",
  event: {
    source: "event_floor" as const,
    L1: 8,
    L2: 12,
    L3: 15,
    confirmBars: 2,
    eventFloorBars: 5,
    eventWindowBars: 10,
  },
  regime: {
    trendMode: "Balanced" as const,
    useSupertrendFilter: true,
    riskOffRsi: 44,
    maxExtPct: 5.5,
  },
  entry: {
    primaryTrigger: "bull_event",
    cooldownBars: 1,
    allowBearRebound: true,
    applyFilterToB1: false,
  },
  slot: {
    slotPct: 12,
    maxSlots: 14,
    useReplacement: true,
    replaceMinRank: 3,
    replaceIfPnlBelow: -4,
  },
  exit: {
    weakRangeExit: true,
    maxHoldBars: 18,
    closeAllOnBearConfRiskOff: true,
    resetOnL3: false,
  },
};

function strictPayload(overrides: Record<string, unknown> = {}) {
  return JSON.stringify({
    candidateSummary: "Spec-only candidate",
    nextMutationHints: ["verify promotion evidence"],
    strategySpec,
    specPatch: {
      version: "af-spec-patch/v1",
      summary: "Test editable strategy patch.",
      operations: [
        {
          path: "/entry",
          after: strategySpec.entry,
          reason: "Exercise strict policy validation.",
        },
      ],
    },
    inventory: [
      {
        conditionId: "entry-bull-event",
        role: "entry",
        summary: "Bull event entry",
        pineLineHints: [1],
      },
    ],
    ...overrides,
  });
}

describe("autoresearch contract policy", () => {
  test("keeps program.finance.md synchronized with policy path constants", async () => {
    const program = await readFile(path.join(workspaceRoot, "program.finance.md"), "utf8");

    for (const firewallPath of EVALUATION_FIREWALL_PATHS) {
      expect(program).toContain(firewallPath);
    }
    for (const editablePath of EDITABLE_RESEARCH_PATHS) {
      expect(program).toContain(editablePath);
    }
  });

  test("allows candidate artifact writes only under editable research paths", () => {
    expect(() =>
      assertEditableResearchPath({
        workspaceRoot,
        targetPath: path.join(workspaceRoot, "strategies", "candidates", "candidate.pine"),
      }),
    ).not.toThrow();
    expect(() =>
      assertEditableResearchPath({
        workspaceRoot,
        targetPath: path.join(workspaceRoot, "strategies", "specs", "candidate.json"),
      }),
    ).not.toThrow();
    expect(() =>
      assertEditableResearchPath({
        workspaceRoot,
        targetPath: path.join(workspaceRoot, "src", "evaluation", "objective.ts"),
      }),
    ).toThrow(/editable research paths/i);
  });

  test("rejects firewall path references in strict mutation responses", () => {
    expect(() =>
      parseMutationResponseStrict(
        strictPayload({
          candidateSummary: "Change src/evaluation/objective.ts to improve score.",
        }),
      ),
    ).toThrow(/evaluation firewall path/i);

    expect(() =>
      parseMutationResponseStrict(
        strictPayload({
          nextMutationHints: ["Tune config/objective.qqq-120m.json after this candidate."],
        }),
      ),
    ).toThrow(/evaluation firewall path/i);
  });

  test("rejects specPatch operations outside editable spec JSON pointer roots", () => {
    expect(() =>
      parseMutationResponseStrict(
        strictPayload({
          specPatch: {
            version: "af-spec-patch/v1",
            summary: "Invalid patch path.",
            operations: [
              {
                path: "/objective",
                after: { minimumTrades: 1 },
                reason: "Attempt to mutate evaluation policy.",
              },
            ],
          },
        }),
      ),
    ).toThrow(/specPatch failed validation/i);
  });
});
