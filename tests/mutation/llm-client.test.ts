import { describe, expect, test } from "vitest";

import { createOpenAiCompatibleLlmClient } from "../../src/mutation/llm-client.js";

describe("createOpenAiCompatibleLlmClient", () => {
  test("returns content from a successful JSON completion", async () => {
    const client = createOpenAiCompatibleLlmClient({
      baseUrl: "http://127.0.0.1:10531/v1",
      model: "gpt-5.4",
      fetchImpl: async () =>
        new Response(
          JSON.stringify({
            choices: [
              {
                message: {
                  content:
                    '{"candidateSummary":"ok","nextMutationHints":[],"pineScript":"//@version=5","inventory":[]}',
                },
              },
            ],
          }),
          {
            status: 200,
            headers: {
              "content-type": "application/json",
            },
          },
        ),
    });

    const result = await client.generateMutation({
      brief: {
        objective: "test",
        guardrails: {
          minimumTotalTrades: 50,
          minimumPostFeeNetProfitPercent: 0,
          maximumStrategyDrawdownPercent: 15,
        },
        repairMode: "balanced",
        seedStrategy: {
          candidateId: "seed_primary",
          summary: "seed",
          studyTitle: "AF Seed 01",
        },
        acceptedHead: null,
        improvementSource: "seed",
        recentFailures: [],
        recentCompileErrors: [],
        recentCompileFailureClasses: [],
        recentLossAnalysis: {
          status: "unavailable_no_trades",
          summary: "none",
          topLossZones: [],
          repairPriorities: [],
        },
        researchContext: {
          status: "none",
          summary: "none",
          matchedProblemTags: [],
          relevantKnowledgeIds: [],
          insights: [],
        },
        lossHotZones: [],
        repairPriorities: [],
        stagnationSignals: [],
        nextMutationDirection: "test",
        forbiddenPatterns: [],
        analysisGuidance: {
          hypothesis: "test hypothesis",
          expectedEffect: "test effect",
          invalidIf: "test invalidation",
          preserveConditions: [],
          weakenConditions: [],
          lossZoneGuidance: [],
          fallbackEvidenceGuidance: {
            available: false,
            source: null,
            authoritative: false,
            summary: "No fallback evidence.",
            suggestedHypothesis: "Use authoritative verification before trusting local evidence.",
            forbiddenInterpretation: "do_not_treat_as_verified",
          },
        },
      },
      baselinePine: "//@version=5",
    });

    expect(result).toContain('"candidateSummary":"ok"');
  });

  test("surfaces a timeout when the OpenAI-compatible endpoint does not respond", async () => {
    const client = createOpenAiCompatibleLlmClient({
      baseUrl: "http://127.0.0.1:10531/v1",
      model: "gpt-5.4",
      requestTimeoutMs: 20,
      fetchImpl: async (_input, init) =>
        await new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener(
            "abort",
            () => {
              const error = new Error("The operation was aborted.");
              error.name = "AbortError";
              reject(error);
            },
            { once: true },
          );
        }),
    });

    await expect(
      client.generateMutation({
        brief: {
          objective: "test",
          guardrails: {
            minimumTotalTrades: 50,
            minimumPostFeeNetProfitPercent: 0,
            maximumStrategyDrawdownPercent: 15,
          },
          repairMode: "balanced",
          seedStrategy: {
            candidateId: "seed_primary",
            summary: "seed",
            studyTitle: "AF Seed 01",
          },
          acceptedHead: null,
          improvementSource: "seed",
          recentFailures: [],
          recentCompileErrors: [],
          recentCompileFailureClasses: [],
          recentLossAnalysis: {
            status: "unavailable_no_trades",
            summary: "none",
            topLossZones: [],
            repairPriorities: [],
          },
          researchContext: {
            status: "none",
            summary: "none",
            matchedProblemTags: [],
            relevantKnowledgeIds: [],
            insights: [],
          },
          lossHotZones: [],
          repairPriorities: [],
          stagnationSignals: [],
          nextMutationDirection: "test",
          forbiddenPatterns: [],
          analysisGuidance: {
            hypothesis: "test hypothesis",
            expectedEffect: "test effect",
            invalidIf: "test invalidation",
            preserveConditions: [],
            weakenConditions: [],
            lossZoneGuidance: [],
            fallbackEvidenceGuidance: {
              available: false,
              source: null,
              authoritative: false,
              summary: "No fallback evidence.",
              suggestedHypothesis: "Use authoritative verification before trusting local evidence.",
              forbiddenInterpretation: "do_not_treat_as_verified",
            },
          },
        },
        baselinePine: "//@version=5",
      }),
    ).rejects.toThrow(/timed out after 20ms/i);
  });
});
