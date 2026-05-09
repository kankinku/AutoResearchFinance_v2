import { describe, expect, test } from "vitest";

import { buildMutationBrief } from "../../src/mutation/brief.js";

describe("buildMutationBrief", () => {
  test("includes curated seed and loss analysis context", () => {
    const brief = buildMutationBrief({
      objective: {
        symbol: "QQQ",
        timeframe: "120",
        hardGates: {
          minimumTotalTrades: 50,
          minimumPostFeeNetProfitPercent: 0,
        },
        softGuardrails: {
          maximumStrategyDrawdownPercent: 15,
          softGuardrailPenalty: 0.1,
        },
        weights: {
          netProfitPercent: 0.45,
          profitFactor: 0.15,
          inverseMaxDrawdown: 0.15,
          percentProfitable: 0.1,
          totalTrades: 0.05,
          avgTradePercent: 0.1,
        },
        normalizationCaps: {
          netProfitPercent: 30,
          profitFactor: 3,
          maxStrategyDrawdownPercent: 30,
          percentProfitable: 100,
          totalTrades: 100,
          avgTradePercent: 1,
        },
      },
      seedStrategy: {
        candidateId: "seed_primary",
        summary: "Curated seed",
        studyTitle: "AF Seed 01",
      },
      acceptedHead: null,
      recentFailures: ["hard_gate_fail"],
      recentCompileErrors: [],
      recentLossAnalysis: {
        status: "available",
        summary: "Losses cluster in trend_down counter-trend entries.",
        topLossZones: ["trend_down:counter_trend_entry"],
        repairPriorities: ["Reduce B2/B3 entries during trend_down regimes."],
      },
      researchContext: {
        status: "available",
        summary: "Attached one research insight.",
        matchedProblemTags: ["weak_exit"],
        relevantKnowledgeIds: ["rsk-1"],
        insights: [
          {
            knowledgeId: "rsk-1",
            title: "Exit timing note",
            sourceType: "manual_text",
            summary: "Weak exits in ranges should cut faster.",
            suggestedMutation: "Tighten exits when weak momentum persists after entry.",
            confidence: 0.82,
          },
          {
            knowledgeId: "rsk-2",
            title: "Trend-down taper note",
            sourceType: "manual_text",
            summary: "Trend-down longs can be tapered.",
            suggestedMutation: "Reduce counter-trend long entries during trend_down regimes.",
            confidence: 0.8,
          },
        ],
      },
    });

    expect(brief.seedStrategy.candidateId).toBe("seed_primary");
    expect(brief.improvementSource).toBe("seed");
    expect(brief.repairMode).toBe("balanced");
    expect(brief.lossHotZones[0]).toContain("trend_down");
    expect(brief.nextMutationDirection).toContain("Preserve the AF seed core architecture");
    expect(brief.nextMutationDirection).toContain("Reduce B2/B3");
    expect(brief.nextMutationDirection).toContain("Tighten exits");
    expect(brief.researchContext.status).toBe("available");
    expect(
      brief.forbiddenPatterns.some((pattern) => pattern.includes("generic EMA crossover")),
    ).toBe(true);
  });

  test("protects parent tradability when no-trade failures dominate", () => {
    const brief = buildMutationBrief({
      objective: {
        symbol: "QQQ",
        timeframe: "120",
        hardGates: {
          minimumTotalTrades: 50,
          minimumPostFeeNetProfitPercent: 0,
        },
        softGuardrails: {
          maximumStrategyDrawdownPercent: 15,
          softGuardrailPenalty: 0.1,
        },
        weights: {
          netProfitPercent: 0.45,
          profitFactor: 0.15,
          inverseMaxDrawdown: 0.15,
          percentProfitable: 0.1,
          totalTrades: 0.05,
          avgTradePercent: 0.1,
        },
        normalizationCaps: {
          netProfitPercent: 30,
          profitFactor: 3,
          maxStrategyDrawdownPercent: 30,
          percentProfitable: 100,
          totalTrades: 100,
          avgTradePercent: 1,
        },
      },
      seedStrategy: {
        candidateId: "seed_primary",
        summary: "Curated seed",
        studyTitle: "AF Seed 01",
      },
      acceptedHead: {
        candidateId: "manual-exhaustion-sample",
        score: 0.75,
        summary: "Strong parent strategy",
        metrics: {
          netProfitPercent: 31.1,
          postFeeNetProfitPercent: 31.1,
          profitFactor: 7.5,
          maxStrategyDrawdownPercent: 4.8,
          percentProfitable: 61,
          totalTrades: 79,
          avgTradePercent: 0.39,
        },
      },
      recentFailures: ["backtest_empty", "backtest_empty", "hard_gate_fail"],
      recentCompileErrors: [],
      recentLossAnalysis: {
        status: "unavailable_no_trades",
        summary: "Most recent candidate produced no trades.",
        topLossZones: [],
        repairPriorities: ["Restore tradable entry frequency before optimizing other metrics."],
      },
      researchContext: {
        status: "none",
        summary: "No external research matched the current failures.",
        matchedProblemTags: [],
        relevantKnowledgeIds: [],
        insights: [],
      },
    });

    expect(brief.acceptedHead?.tradeRetentionTarget).toBe(56);
    expect(brief.repairMode).toBe("entry_recovery");
    expect(brief.nextMutationDirection).toContain("keep at least 56 closed trades");
    expect(brief.nextMutationDirection).toContain("loosening or removing existing entry filters");
    expect(
      brief.forbiddenPatterns.some((pattern) => pattern.includes("collapses below 56 trades")),
    ).toBe(true);
    expect(
      brief.forbiddenPatterns.some((pattern) => pattern.includes("prefer parameter loosening")),
    ).toBe(false);
    expect(
      brief.forbiddenPatterns.some((pattern) =>
        pattern.includes("do not add new filters or new subsystems"),
      ),
    ).toBe(true);
  });

  test("switches from blanket tradability recovery to targeted repair when loss analysis is available", () => {
    const brief = buildMutationBrief({
      objective: {
        symbol: "QQQ",
        timeframe: "120",
        hardGates: {
          minimumTotalTrades: 50,
          minimumPostFeeNetProfitPercent: 0,
        },
        softGuardrails: {
          maximumStrategyDrawdownPercent: 15,
          softGuardrailPenalty: 0.1,
        },
        weights: {
          netProfitPercent: 0.45,
          profitFactor: 0.15,
          inverseMaxDrawdown: 0.15,
          percentProfitable: 0.1,
          totalTrades: 0.05,
          avgTradePercent: 0.1,
        },
        normalizationCaps: {
          netProfitPercent: 30,
          profitFactor: 3,
          maxStrategyDrawdownPercent: 30,
          percentProfitable: 100,
          totalTrades: 100,
          avgTradePercent: 1,
        },
      },
      seedStrategy: {
        candidateId: "seed_primary",
        summary: "Curated seed",
        studyTitle: "AF Seed 01",
      },
      acceptedHead: {
        candidateId: "manual-exhaustion-sample",
        score: 0.75,
        summary: "Strong parent strategy",
        metrics: {
          netProfitPercent: 31.1,
          postFeeNetProfitPercent: 31.1,
          profitFactor: 7.5,
          maxStrategyDrawdownPercent: 4.8,
          percentProfitable: 61,
          totalTrades: 79,
          avgTradePercent: 0.39,
        },
      },
      recentFailures: ["apply_fail", "compile_fail", "hard_gate_fail"],
      recentCompileErrors: [],
      recentLossAnalysis: {
        status: "available",
        summary: "Losses now cluster in range weak exits.",
        topLossZones: ["range:weak_exit:3", "trend_down:weak_exit:5"],
        repairPriorities: [
          "Prioritize faster loser exits in range and range_squeeze regimes before tuning new entries.",
          "Tighten exit behavior when losing trades continue into deeper drawdown.",
        ],
      },
      researchContext: {
        status: "available",
        summary: "Attached one research insight.",
        matchedProblemTags: ["weak_exit", "range_squeeze"],
        relevantKnowledgeIds: ["rsk-1"],
        insights: [
          {
            knowledgeId: "rsk-1",
            title: "Exit timing note",
            sourceType: "manual_text",
            summary: "Weak exits in ranges should cut faster.",
            suggestedMutation: "Reduce counter-trend long entries during trend_down regimes.",
            confidence: 0.82,
          },
        ],
      },
      guidanceMetrics: {
        netProfitPercent: 2.52,
        postFeeNetProfitPercent: 2.52,
        profitFactor: 1.74,
        maxStrategyDrawdownPercent: 2.45,
        percentProfitable: 37.68,
        totalTrades: 69,
        avgTradePercent: 0.19,
      },
    });

    expect(brief.acceptedHead?.tradeRetentionTarget).toBe(56);
    expect(brief.repairMode).toBe("exit_profit_repair");
    expect(brief.nextMutationDirection).toContain("Keep tradability above 56 closed trades");
    expect(brief.nextMutationDirection).not.toContain("Recover tradability by loosening or removing recent entry filters");
    expect(brief.nextMutationDirection).toContain("Prioritize faster loser exits");
    expect(
      brief.forbiddenPatterns.some((pattern) => pattern.includes("collapses below 56 trades")),
    ).toBe(true);
    expect(
      brief.forbiddenPatterns.some((pattern) => pattern.includes("actionable loss analysis")),
    ).toBe(true);
  });

  test("treats a strong accepted head as a control and limits mutation scope", () => {
    const brief = buildMutationBrief({
      objective: {
        symbol: "QQQ",
        timeframe: "120",
        hardGates: {
          minimumTotalTrades: 50,
          minimumPostFeeNetProfitPercent: 0,
        },
        softGuardrails: {
          maximumStrategyDrawdownPercent: 15,
          softGuardrailPenalty: 0.1,
        },
        weights: {
          netProfitPercent: 0.45,
          profitFactor: 0.15,
          inverseMaxDrawdown: 0.15,
          percentProfitable: 0.1,
          totalTrades: 0.05,
          avgTradePercent: 0.1,
        },
        normalizationCaps: {
          netProfitPercent: 30,
          profitFactor: 3,
          maxStrategyDrawdownPercent: 30,
          percentProfitable: 100,
          totalTrades: 100,
          avgTradePercent: 1,
        },
      },
      seedStrategy: {
        candidateId: "seed_primary",
        summary: "Curated seed",
        studyTitle: "AF Seed 01",
      },
      acceptedHead: {
        candidateId: "manual-exhaustion-sample",
        score: 0.75,
        summary: "Strong parent strategy",
        metrics: {
          netProfitPercent: 31.1,
          postFeeNetProfitPercent: 31.1,
          profitFactor: 7.5,
          maxStrategyDrawdownPercent: 4.8,
          percentProfitable: 79.7,
          totalTrades: 79,
          avgTradePercent: 3.41,
        },
      },
      recentFailures: ["hard_gate_fail"],
      recentCompileErrors: [],
      recentLossAnalysis: {
        status: "available",
        summary: "Losses now cluster in range weak exits.",
        topLossZones: ["range:weak_exit:3"],
        repairPriorities: ["Prioritize faster loser exits in range and range_squeeze regimes before tuning new entries."],
      },
      researchContext: {
        status: "available",
        summary: "Attached one research insight.",
        matchedProblemTags: ["weak_exit"],
        relevantKnowledgeIds: ["rsk-1"],
        insights: [
          {
            knowledgeId: "rsk-1",
            title: "Exit timing note",
            sourceType: "manual_text",
            summary: "Weak exits in ranges should cut faster.",
            suggestedMutation: "Tighten exits when weak momentum persists after entry.",
            confidence: 0.82,
          },
        ],
      },
      guidanceMetrics: {
        netProfitPercent: 31.1,
        postFeeNetProfitPercent: 31.1,
        profitFactor: 7.5,
        maxStrategyDrawdownPercent: 4.8,
        percentProfitable: 79.7,
        totalTrades: 79,
        avgTradePercent: 3.41,
      },
    });

    expect(brief.nextMutationDirection).toContain("Use the accepted head as a control");
    expect(brief.repairMode).toBe("exit_profit_repair");
    expect(brief.nextMutationDirection).toContain(
      "Prefer parameter, threshold, or single-rule adjustments",
    );
    expect(brief.nextMutationDirection).not.toContain(
      "Reduce counter-trend long entries during trend_down regimes.",
    );
    expect(
      brief.forbiddenPatterns.some((pattern) =>
        pattern.includes("simultaneously rewrite multiple core blocks"),
      ),
    ).toBe(true);
    expect(
      brief.forbiddenPatterns.some((pattern) =>
        pattern.includes("Preserve control-candidate defaults"),
      ),
    ).toBe(true);
    expect(
      brief.forbiddenPatterns.some((pattern) =>
        pattern.includes("new multi-part subsystems"),
      ),
    ).toBe(true);
  });

  test("carries recent compile errors into the brief so generation can avoid them", () => {
    const brief = buildMutationBrief({
      objective: {
        symbol: "QQQ",
        timeframe: "120",
        hardGates: {
          minimumTotalTrades: 50,
          minimumPostFeeNetProfitPercent: 0,
        },
        softGuardrails: {
          maximumStrategyDrawdownPercent: 15,
          softGuardrailPenalty: 0.1,
        },
        weights: {
          netProfitPercent: 0.45,
          profitFactor: 0.15,
          inverseMaxDrawdown: 0.15,
          percentProfitable: 0.1,
          totalTrades: 0.05,
          avgTradePercent: 0.1,
        },
        normalizationCaps: {
          netProfitPercent: 30,
          profitFactor: 3,
          maxStrategyDrawdownPercent: 30,
          percentProfitable: 100,
          totalTrades: 100,
          avgTradePercent: 1,
        },
      },
      seedStrategy: {
        candidateId: "seed_primary",
        summary: "Curated seed",
        studyTitle: "AF Seed 01",
      },
      acceptedHead: null,
      recentFailures: ["compile_fail"],
      recentCompileErrors: [
        "Undeclared identifier 'emaLen'",
        "The 'strategy.entry' function does not have an argument with the name 'qty_percent'",
      ],
      recentCompileFailureClasses: [
        "undeclared_identifier",
        "qty_percent_argument",
      ],
      recentLossAnalysis: {
        status: "unavailable_no_trades",
        summary: "No prior loss analysis is available yet.",
        topLossZones: [],
        repairPriorities: [],
      },
      researchContext: {
        status: "none",
        summary: "No external research matched the current failures.",
        matchedProblemTags: [],
        relevantKnowledgeIds: [],
        insights: [],
      },
    });

    expect(brief.recentCompileErrors).toContain("Undeclared identifier 'emaLen'");
    expect(brief.recentCompileFailureClasses).toEqual([
      "undeclared_identifier",
      "qty_percent_argument",
    ]);
    expect(
      brief.forbiddenPatterns.some((pattern) =>
        pattern.includes("Do not repeat recent compile failures"),
      ),
    ).toBe(true);
    expect(
      brief.forbiddenPatterns.some((pattern) =>
        pattern.includes("compile-failure classes"),
      ),
    ).toBe(true);
  });

  test("adds stagnation signals when the same diagnosis keeps repeating", () => {
    const brief = buildMutationBrief({
      objective: {
        symbol: "QQQ",
        timeframe: "120",
        hardGates: {
          minimumTotalTrades: 50,
          minimumPostFeeNetProfitPercent: 0,
        },
        softGuardrails: {
          maximumStrategyDrawdownPercent: 15,
          softGuardrailPenalty: 0.1,
        },
        weights: {
          netProfitPercent: 0.45,
          profitFactor: 0.15,
          inverseMaxDrawdown: 0.15,
          percentProfitable: 0.1,
          totalTrades: 0.05,
          avgTradePercent: 0.1,
        },
        normalizationCaps: {
          netProfitPercent: 30,
          profitFactor: 3,
          maxStrategyDrawdownPercent: 30,
          percentProfitable: 100,
          totalTrades: 100,
          avgTradePercent: 1,
        },
      },
      seedStrategy: {
        candidateId: "seed_primary",
        summary: "Curated seed",
        studyTitle: "AF Seed 01",
      },
      acceptedHead: {
        candidateId: "manual-exhaustion-sample",
        score: 0.75,
        summary: "Strong parent strategy",
        metrics: {
          netProfitPercent: 31.1,
          postFeeNetProfitPercent: 31.1,
          profitFactor: 7.5,
          maxStrategyDrawdownPercent: 4.8,
          percentProfitable: 61,
          totalTrades: 79,
          avgTradePercent: 0.39,
        },
      },
      recentFailures: ["hard_gate_fail"],
      recentCompileErrors: [],
      recentLossAnalysis: {
        status: "available",
        summary: "Range weak exits keep repeating.",
        topLossZones: ["range:weak_exit:3", "range_squeeze:weak_exit:2"],
        repairPriorities: ["Prioritize faster loser exits in range and range_squeeze regimes before tuning new entries."],
      },
      researchContext: {
        status: "none",
        summary: "No external research matched the current failures.",
        matchedProblemTags: [],
        relevantKnowledgeIds: [],
        insights: [],
      },
      guidanceMetrics: {
        netProfitPercent: 5,
        postFeeNetProfitPercent: 4,
        profitFactor: 1.4,
        maxStrategyDrawdownPercent: 4,
        percentProfitable: 42,
        totalTrades: 69,
        avgTradePercent: 0.18,
      },
      stagnationSignals: [
        'Avoid repeating repair priority "Prioritize faster loser exits in range and range_squeeze regimes before tuning new entries." again without a materially different rule change; it appeared 3 times in the last 5 evaluated candidates without score improvement.',
      ],
    });

    expect(brief.stagnationSignals).toHaveLength(1);
    expect(brief.nextMutationDirection).toContain("materially different rule change");
    expect(
      brief.forbiddenPatterns.some((pattern) =>
        pattern.includes("Do not repeat the same diagnosis again"),
      ),
    ).toBe(true);
  });

  test("preserves explicit fallback evidence guidance in analysis guidance", () => {
    const brief = buildMutationBrief({
      objective: {
        symbol: "QQQ",
        timeframe: "120",
        hardGates: {
          minimumTotalTrades: 50,
          minimumPostFeeNetProfitPercent: 0,
        },
        softGuardrails: {
          maximumStrategyDrawdownPercent: 15,
          softGuardrailPenalty: 0.1,
        },
        weights: {
          netProfitPercent: 0.45,
          profitFactor: 0.15,
          inverseMaxDrawdown: 0.15,
          percentProfitable: 0.1,
          totalTrades: 0.05,
          avgTradePercent: 0.1,
        },
        normalizationCaps: {
          netProfitPercent: 30,
          profitFactor: 3,
          maxStrategyDrawdownPercent: 30,
          percentProfitable: 100,
          totalTrades: 100,
          avgTradePercent: 1,
        },
      },
      seedStrategy: {
        candidateId: "seed_primary",
        summary: "Curated seed",
        studyTitle: "AF Seed 01",
      },
      acceptedHead: null,
      recentFailures: ["verification_fail"],
      recentCompileErrors: [],
      recentLossAnalysis: {
        status: "market_context_unavailable",
        summary: "No loss data yet.",
        topLossZones: [],
        repairPriorities: [],
      },
      researchContext: {
        status: "none",
        summary: "No external research matched the current failures.",
        matchedProblemTags: [],
        relevantKnowledgeIds: [],
        insights: [],
      },
      fallbackEvidenceGuidance: {
        available: true,
        source: "local-af-screening",
        authoritative: false,
        summary: "Local verification failed earlier; local fallback evidence exists.",
        suggestedHypothesis:
          "Use the local screening delta as a hypothesis only until local validation succeeds.",
        forbiddenInterpretation: "do_not_treat_as_verified",
      },
    });

    expect(brief.analysisGuidance.fallbackEvidenceGuidance.available).toBe(true);
    expect(brief.analysisGuidance.fallbackEvidenceGuidance.source).toBe(
      "local-af-screening",
    );
    expect(brief.analysisGuidance.fallbackEvidenceGuidance.summary).toContain(
      "local fallback evidence",
    );
    expect(
      brief.analysisGuidance.fallbackEvidenceGuidance.forbiddenInterpretation,
    ).toBe("do_not_treat_as_verified");
  });
});
