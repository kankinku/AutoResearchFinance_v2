import { describe, expect, test } from "vitest";

import {
  inspectGeneratedMutation,
  repairTimeBoxedVariantPreflightIssues,
} from "../../src/mutation/preflight.js";
import type {
  MutationBrief,
  ParsedMutationResponse,
} from "../../src/contracts/types.js";

describe("inspectGeneratedMutation", () => {
  test("detects blocking Pine generation issues before compile", () => {
    const inspection = inspectGeneratedMutation({
      candidateSummary: "Broken candidate",
      nextMutationHints: [],
      pineScript: [
        "strategy('Broken', overlay=true)",
        "// TODO replace this",
        "adxValue = ta.adx(14)",
        "```",
      ].join("\n"),
      inventory: [
        {
          conditionId: "entry-alpha",
          role: "entry",
          summary: "Entry condition",
          pineLineHints: [2],
        },
      ],
      inventorySource: "llm",
      missingFields: [],
      inferredFields: [],
    });

    expect(inspection.blockingIssues.map((issue) => issue.code)).toEqual(
      expect.arrayContaining([
        "missing_version_pragma",
        "unsupported_ta_adx",
        "placeholder_logic",
        "markdown_fence_leak",
      ]),
    );
  });

  test("detects repeated Pine compile anti-patterns before local compile", () => {
    const inspection = inspectGeneratedMutation(
      {
        candidateSummary: "Compile anti-patterns",
        nextMutationHints: [],
        pineScript: [
          "//@version=5",
          "strategy('Broken', overlay=true)",
          "var int lastOrderBar = na",
          "f_close_slot() =>",
          "    lastOrderBar := bar_index",
          "qtyNow = 1",
          "strategy.entry('L', strategy.long, qty_percent=10)",
          "sumValue = ta.sum(close, 5)",
          "plot(emaLen)",
        ].join("\n"),
        inventory: [
          {
            conditionId: "entry-alpha",
            role: "entry",
            summary: "Entry condition",
            pineLineHints: [7],
          },
        ],
        inventorySource: "llm",
        missingFields: [],
        inferredFields: [],
      },
      {
        recentCompileErrors: [
          "Undeclared identifier 'emaLen'",
          "The 'strategy.entry' function does not have an argument with the name 'qty_percent'",
          "Could not find function or function reference 'ta.sum'",
          "Cannot modify global variable 'lastOrderBar' in function",
        ],
        recentCompileFailureClasses: [
          "undeclared_identifier",
          "qty_percent_argument",
          "unsupported_ta_sum",
          "function_mutates_global",
        ],
      },
    );

    expect(inspection.blockingIssues.map((issue) => issue.code)).toEqual(
      expect.arrayContaining([
        "unsupported_strategy_entry_qty_percent",
        "unsupported_ta_sum",
        "recent_undeclared_identifier_repeat",
        "function_mutates_global",
      ]),
    );
  });

  test("detects normalized title and na-assignment anti-patterns when those classes repeated recently", () => {
    const inspection = inspectGeneratedMutation(
      {
        candidateSummary: "Title and na issues",
        nextMutationHints: [],
        pineScript: [
          "//@version=5",
          `strategy("This strategy title is intentionally far too long for the executor safety threshold", overlay=true)`,
          "signalState = na",
          "strategy.entry('L', strategy.long, qty=1)",
        ].join("\n"),
        inventory: [
          {
            conditionId: "entry-alpha",
            role: "entry",
            summary: "Entry condition",
            pineLineHints: [4],
          },
        ],
        inventorySource: "llm",
        missingFields: [],
        inferredFields: [],
      },
      {
        recentCompileFailureClasses: ["title_too_long", "na_type_assignment"],
      },
    );

    expect(inspection.blockingIssues.map((issue) => issue.code)).toEqual(
      expect.arrayContaining(["strategy_title_too_long", "na_type_assignment"]),
    );
  });

  test("blocks time-boxed variants that keep sparse event sources or stacked filters", () => {
    const inspection = inspectGeneratedMutation(
      {
        candidateSummary: "Sparse time-boxed variant",
        nextMutationHints: [],
        pineScript: [
          "//@version=5",
          "strategy('Sparse Time Box', overlay=true)",
          "L1_in = input.int(9, 'L1', minval=2)",
          "bullL1 = bull == L1_in",
          "bearL1 = bear == L1_in",
          "newBullL1 = bullL1 and not nz(bullL1[1], false)",
          "newBearL1 = bearL1 and not nz(bearL1[1], false)",
          "bullEventRaw = newBullConfirmed ? 4 : newBullStrong ? 3 : newBullCandidate ? 2 : newBullL1 ? 1 : 0",
          "bearEventRaw = newBearConfirmed ? 4 : newBearStrong ? 3 : newBearCandidate ? 2 : newBearL1 ? 1 : 0",
          "bullEarlyEvent = newBullL1 or newBullCandidate or newBullStrong or newBullConfirmed",
          "bearEarlyEvent = newBearL1 or newBearCandidate or newBearStrong or newBearConfirmed",
          "postBullEventWindow = bullEarlyEvent",
          "postBearReboundWindow = bearEarlyEvent",
          "primaryEntryTrigger = postBullEventWindow or postBearReboundWindow",
          "entryPass = primaryEntryTrigger and trendPass and riskPass and not overextended",
          "if entryPass",
          "    strategy.entry('L', strategy.long, qty=1)",
        ].join("\n"),
        inventory: [
          {
            conditionId: "entry-time-boxed",
            role: "entry",
            summary: "Entry condition",
            pineLineHints: [13],
          },
        ],
        inventorySource: "llm",
        missingFields: [],
        inferredFields: [],
      },
      {
        breakoutVariantDirective: {
          routeId: "time_boxed_event_rotation",
          variantId: "dual_event_age_windows",
          escalationLevel: 3,
          recentSparseCount: 17,
          summary: "Force dense event windows.",
          forcedRules: [],
          forbiddenPatterns: [],
        },
      },
    );

    expect(inspection.blockingIssues.map((issue) => issue.code)).toEqual(
      expect.arrayContaining([
        "time_boxed_sparse_event_source",
        "time_boxed_entry_overfiltered",
      ]),
    );
  });

  test("allows dense time-boxed event source with one lightweight gate", () => {
    const inspection = inspectGeneratedMutation(
      {
        candidateSummary: "Dense time-boxed variant",
        nextMutationHints: [],
        pineScript: [
          "//@version=5",
          "strategy('Dense Time Box', overlay=true)",
          "eventFloorBars = input.int(4, 'Event Floor', minval=2, maxval=5)",
          "bullEventFloor = bull >= eventFloorBars",
          "bearEventFloor = bear >= eventFloorBars",
          "earlyBullEvent = bullEventFloor and not nz(bullEventFloor[1], false)",
          "earlyBearEvent = bearEventFloor and not nz(bearEventFloor[1], false)",
          "postBullEventWindow = ta.barssince(earlyBullEvent) <= 12",
          "postBearReboundWindow = ta.barssince(earlyBearEvent) <= 12",
          "primaryEntryTrigger = postBullEventWindow or postBearReboundWindow",
          "entryPass = primaryEntryTrigger and not riskOff",
          "if entryPass",
          "    strategy.entry('L', strategy.long, qty=1)",
        ].join("\n"),
        inventory: [
          {
            conditionId: "entry-time-boxed",
            role: "entry",
            summary: "Entry condition",
            pineLineHints: [9],
          },
        ],
        inventorySource: "llm",
        missingFields: [],
        inferredFields: [],
      },
      {
        breakoutVariantDirective: {
          routeId: "time_boxed_event_rotation",
          variantId: "dual_event_age_windows",
          escalationLevel: 3,
          recentSparseCount: 17,
          summary: "Force dense event windows.",
          forcedRules: [],
          forbiddenPatterns: [],
        },
      },
    );

    expect(inspection.blockingIssues.map((issue) => issue.code)).not.toEqual(
      expect.arrayContaining([
        "time_boxed_sparse_event_source",
        "time_boxed_entry_overfiltered",
      ]),
    );
  });

  test("deterministically repairs sparse time-boxed preflight issues", () => {
    const directive: NonNullable<MutationBrief["breakoutVariantDirective"]> = {
      routeId: "time_boxed_event_rotation",
      variantId: "thresholdless_event_age_rotation",
      escalationLevel: 3,
      recentSparseCount: 18,
      summary: "Force dense event windows.",
      forcedRules: [],
      forbiddenPatterns: [],
    };
    const parsed: ParsedMutationResponse = {
      candidateSummary: "Sparse time-boxed variant",
      nextMutationHints: [],
      pineScript: [
        "//@version=5",
        "strategy('Sparse Time Box', overlay=true)",
        'groupRot = "8. Breakout Rotation"',
        "L1_in = input.int(9, 'L1', minval=2)",
        "bullL1 = bull == L1_in",
        "bearL1 = bear == L1_in",
        "newBullL1 = bullL1 and not nz(bullL1[1], false)",
        "newBearConfirmed = bearConfirmed and not nz(bearConfirmed[1], false)",
        "bullEventRaw = newBullConfirmed ? 4 : newBullStrong ? 3 : newBullCandidate ? 2 : newBullL1 ? 1 : 0",
        "bearEventRaw = newBearConfirmed ? 4 : newBearStrong ? 3 : newBearCandidate ? 2 : newBearL1 ? 1 : 0",
        "bullEarlyEvent = newBullL1 or newBullCandidate or newBullStrong or newBullConfirmed",
        "bearEarlyEvent = newBearL1 or newBearCandidate or newBearStrong or newBearConfirmed",
        "bullContinueWindow = 12",
        "bearReboundWindow = 10",
        "bullEventAge = ta.barssince(bullEarlyEvent)",
        "bearEventAge = ta.barssince(bearEarlyEvent)",
        "bullAgeActive = not na(bullEventAge) and bullEventAge >= eventFloorBars and bullEventAge <= bullContinueWindow",
        "bearAgeActive = not na(bearEventAge) and bearEventAge >= eventFloorBars and bearEventAge <= bearReboundWindow",
        "primaryEntryTrigger = bullAgeActive or bearAgeActive",
        "riskOff = false",
        "entryPass = primaryEntryTrigger and trendPass and riskPass and not overextended",
        "if entryPass",
        "    strategy.entry('L', strategy.long, qty=1)",
      ].join("\n"),
      inventory: [
        {
          conditionId: "entry-time-boxed",
          role: "entry",
          summary: "Entry condition",
          pineLineHints: [15],
        },
      ],
      inventorySource: "llm",
      missingFields: [],
      inferredFields: [],
    };

    const initial = inspectGeneratedMutation(parsed, {
      breakoutVariantDirective: directive,
    });
    const repaired = repairTimeBoxedVariantPreflightIssues(
      parsed,
      initial.blockingIssues,
      directive,
    );

    expect(repaired?.pineScript).toContain("eventFloorBars = input.int(4");
    expect(repaired?.pineScript).toContain("earlyBullEvent = bullEventFloor");
    expect(repaired?.pineScript).toContain(
      "bullEventRaw = earlyBullEvent ? 1",
    );
    expect(repaired?.pineScript).toContain("bullEarlyEvent = earlyBullEvent");
    expect(repaired?.pineScript).toContain("bearEarlyEvent = earlyBearEvent");
    expect(repaired?.pineScript).toContain(
      "bullAgeActive = not na(bullEventAge) and bullEventAge <= bullContinueWindow",
    );
    expect(repaired?.pineScript).toContain(
      "bearAgeActive = not na(bearEventAge) and bearEventAge <= bearReboundWindow",
    );
    expect(repaired?.pineScript).toContain(
      "entryPass = primaryEntryTrigger and not riskOff",
    );

    const repairedInspection = inspectGeneratedMutation(repaired!, {
      breakoutVariantDirective: directive,
    });
    expect(repairedInspection.blockingIssues.map((issue) => issue.code)).not.toEqual(
      expect.arrayContaining([
        "time_boxed_sparse_event_source",
        "time_boxed_entry_overfiltered",
      ]),
    );
  });

  test("deterministically repairs typed sparse aliases and noncanonical windows", () => {
    const directive: NonNullable<MutationBrief["breakoutVariantDirective"]> = {
      routeId: "time_boxed_event_rotation",
      variantId: "thresholdless_event_age_rotation",
      escalationLevel: 4,
      recentSparseCount: 19,
      summary: "Force dense event windows.",
      forcedRules: [],
      forbiddenPatterns: [],
    };
    const parsed: ParsedMutationResponse = {
      candidateSummary: "Typed sparse time-boxed variant",
      nextMutationHints: [],
      pineScript: [
        "//@version=5",
        "strategy('Typed Sparse Time Box', overlay=true)",
        "int L1_in = input.int(9, 'L1', minval=2)",
        "bullL1 = bull == L1_in",
        "bearL1 = bear == L1_in",
        "newBullL1 = bullL1 and not nz(bullL1[1], false)",
        "newBearL1 = bearL1 and not nz(bearL1[1], false)",
        "int bullEventRaw = earlyBullEvent ? 1 : 0",
        "int bearEventRaw = earlyBearEvent ? 1 : 0",
        "bool earlyBullEvent = newBullL1",
        "bool earlyBearEvent = newBearL1",
        "bullEventAge = ta.barssince(earlyBullEvent)",
        "bearEventAge = ta.barssince(earlyBearEvent)",
        "bool postBullEventWindow = not na(bullEventAge) and bullEventAge >= eventFloorBars and bullEventAge <= 9",
        "bool postBearReboundWindow = not na(bearEventAge) and bearEventAge >= eventFloorBars and bearEventAge <= 9",
        "bool primaryEntryTrigger = postBullEventWindow or postBearReboundWindow",
        "bool entryPass = primaryEntryTrigger and trendPass and riskPass",
        "if entryPass",
        "    strategy.entry('L', strategy.long, qty=1)",
      ].join("\n"),
      inventory: [
        {
          conditionId: "entry-time-boxed",
          role: "entry",
          summary: "Entry condition",
          pineLineHints: [16],
        },
      ],
      inventorySource: "llm",
      missingFields: [],
      inferredFields: [],
    };

    const initial = inspectGeneratedMutation(parsed, {
      breakoutVariantDirective: directive,
    });
    const repaired = repairTimeBoxedVariantPreflightIssues(
      parsed,
      initial.blockingIssues,
      directive,
    );

    expect(repaired?.pineScript).toContain(
      "bullEventAge = ta.barssince(earlyBullEvent)",
    );
    expect(repaired?.pineScript).toContain(
      "earlyBullEvent = bullEventFloor and not nz(bullEventFloor[1], false)",
    );
    expect(repaired?.pineScript).toContain(
      "bullAgeActive = not na(bullEventAge) and bullEventAge <= bullContinueWindow",
    );
    expect(repaired?.pineScript).toContain(
      "postBullEventWindow = bullAgeActive",
    );
    expect(repaired?.pineScript).toContain(
      "primaryEntryTrigger = postBullEventWindow or postBearReboundWindow",
    );
    expect(repaired?.pineScript).toContain("entryPass = primaryEntryTrigger");

    const repairedInspection = inspectGeneratedMutation(repaired!, {
      breakoutVariantDirective: directive,
    });
    expect(repairedInspection.blockingIssues.map((issue) => issue.code)).not.toEqual(
      expect.arrayContaining([
        "time_boxed_sparse_event_source",
        "time_boxed_entry_overfiltered",
      ]),
    );
  });

  test("deterministically reroutes sparse rotation-window entrySignal variants", () => {
    const directive: NonNullable<MutationBrief["breakoutVariantDirective"]> = {
      routeId: "time_boxed_event_rotation",
      variantId: "dual_event_age_windows",
      escalationLevel: 4,
      recentSparseCount: 20,
      summary: "Force dense event windows.",
      forcedRules: [],
      forbiddenPatterns: [],
    };
    const parsed: ParsedMutationResponse = {
      candidateSummary: "Sparse rotation-window variant",
      nextMutationHints: [],
      pineScript: [
        "//@version=5",
        "strategy('Rotation Window', overlay=true)",
        "L1_in = input.int(9, 'L1', minval=2)",
        "bullL1 = bull == L1_in",
        "bearL1 = bear == L1_in",
        "newBullL1 = bullL1 and not nz(bullL1[1], false)",
        "newBearL1 = bearL1 and not nz(bearL1[1], false)",
        "bullEventRaw = newBullConfirmed ? 4 : newBullStrong ? 3 : newBullCandidate ? 2 : newBullL1 ? 1 : 0",
        "bearEventRaw = newBearConfirmed ? 4 : newBearStrong ? 3 : newBearCandidate ? 2 : newBearL1 ? 1 : 0",
        "riskOff = false",
        "var int rotationWindowEnd = na",
        "windowBars = finalBullEvent >= 4 ? 5 : finalBullEvent == 3 ? 4 : finalBullEvent == 2 ? 3 : 2",
        "if finalBullEvent > 0",
        "    rotationWindowEnd := bar_index + windowBars",
        "rotationActive = not na(rotationWindowEnd) and bar_index <= rotationWindowEnd",
        "var int bullEventAge = na",
        "var int bearEventAge = na",
        "bullAgeActive = not na(bullEventAge) and bullEventAge <= 5",
        "bearAgeActive = not na(bearEventAge) and bearEventAge <= 5",
        "entrySignal = false",
        "if rotationActive",
        "    entrySignal := close > open and bullRecoveryOk",
        "canEnterLong = true",
        "if entrySignal and canEnterLong",
        "    strategy.entry('L', strategy.long, qty=1)",
      ].join("\n"),
      inventory: [
        {
          conditionId: "entry-rotation-window",
          role: "entry",
          summary: "Entry condition",
          pineLineHints: [20],
        },
      ],
      inventorySource: "llm",
      missingFields: [],
      inferredFields: [],
    };

    const initial = inspectGeneratedMutation(parsed, {
      breakoutVariantDirective: directive,
    });
    const repaired = repairTimeBoxedVariantPreflightIssues(
      parsed,
      initial.blockingIssues,
      directive,
    );

    expect(initial.blockingIssues.map((issue) => issue.code)).toContain(
      "time_boxed_sparse_event_source",
    );
    expect(repaired?.pineScript).toContain("eventFloorBars = input.int(4");
    expect(repaired?.pineScript).toContain(
      "primaryEntryTrigger = postBullEventWindow or postBearReboundWindow",
    );
    expect(repaired?.pineScript).toContain(
      "entryPass = primaryEntryTrigger and not riskOff",
    );
    expect(repaired?.pineScript).toContain("if entryPass and canEnterLong");
    expect(repaired?.pineScript).not.toContain("var int bullEventAge = na");
    expect(
      repaired!.pineScript.indexOf("bullEventFloor = bull >= eventFloorBars"),
    ).toBeLessThan(
      repaired!.pineScript.indexOf("earlyBullEvent = bullEventFloor"),
    );
    expect(
      repaired!.pineScript.indexOf("bullContinueWindow = input.int"),
    ).toBeLessThan(
      repaired!.pineScript.indexOf(
        "bullAgeActive = not na(bullEventAge) and bullEventAge <= bullContinueWindow",
      ),
    );

    const repairedInspection = inspectGeneratedMutation(repaired!, {
      breakoutVariantDirective: directive,
    });
    expect(repairedInspection.blockingIssues.map((issue) => issue.code)).not.toEqual(
      expect.arrayContaining([
        "time_boxed_sparse_event_source",
        "time_boxed_entry_overfiltered",
      ]),
    );
  });
});
