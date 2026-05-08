import { beforeEach, describe, expect, test, vi } from "vitest";

import { type MutationLlmClient } from "../../src/mutation/llm-client.js";
import { type RuntimeEnvironment } from "../../src/cli/runtime-config.js";

const ensureOpenAiAuthReady = vi.fn();
const createOpenAiCompatibleLlmClient = vi.fn<() => MutationLlmClient>();

vi.mock("../../src/cli/openai-oauth.js", () => ({
  ensureOpenAiAuthReady,
}));

vi.mock("../../src/mutation/llm-client.js", () => ({
  createOpenAiCompatibleLlmClient,
}));

function createRuntimeEnv(overrides?: Partial<RuntimeEnvironment>): RuntimeEnvironment {
  const workspaceRoot = process.cwd();
  return {
    projectRoot: process.cwd(),
    workspaceRoot,
    stateRoot: `${workspaceRoot}\\state\\pi-autoresearch`,
    researchTargetId: "qqq-120m-af",
    openAiAuthMode: "oauth_proxy",
    openAiBaseUrl: "http://127.0.0.1:10531/v1",
    openAiModel: "gpt-5.4",
    openAiApiKey: undefined,
    openAiRequestTimeoutMs: 180_000,
    openAiMaxRetries: 3,
    openAiOauthProxyCommand: "npx openai-oauth",
    openAiOauthAuthFilePath: undefined,
    mutationStaticResponsePath: undefined,
    evaluationUseMock: false,
    evaluationExecutor: "tradingview-desktop-cdp",
    promotionVerificationExecutor: "none",
    tradingViewDesktopPath: "C:\\TradingView\\TradingView.exe",
    tradingViewCdpUrl: undefined,
    pineEditorTimeoutMs: 15_000,
    tradingViewCdpCommandTimeoutMs: 8_000,
    chartSymbol: "QQQ",
    chartTimeframe: "120",
    chartType: "candles",
    maxTrades: 50,
    researchRefreshEveryTasks: 3,
    alphaXivMcpUrl: "https://api.alphaxiv.org/mcp/v1",
    alphaXivMcpBearerToken: undefined,
    alphaXivAuthFilePath: undefined,
    alphaXivSessionFilePath: undefined,
    tvCalibrationMode: "live",
    mutationSchemaMode: "strict",
    autonomousBootstrapMode: "disabled",
    autoProcessCalibration: false,
    calibrationBudget: 1,
    calibrationTimeoutMs: 30_000,
    strategyReviewMode: "selective",
    strategyReviewDeepBudget: 3,
    strategyReviewMinConfidence: 0.7,
    strategyReviewQuarantineConfidence: 0.85,
    ...overrides,
    researchModeConfig: overrides?.researchModeConfig ?? {
      mode: "continuous_improvement",
      source: "default",
    },
  };
}

describe("createMutationLlmClient", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
    ensureOpenAiAuthReady.mockResolvedValue({
      authMode: "oauth_proxy",
      authConfigured: true,
      reachable: true,
      status: 200,
      proxyStarted: false,
      proxyRestarted: false,
      authFilePath: "C:\\Users\\hanji\\.codex\\auth.json",
    });
  });

  test("passes the configured request timeout to the live OpenAI client", async () => {
    createOpenAiCompatibleLlmClient.mockReturnValue({
      generateMutation: vi.fn().mockResolvedValue("{}"),
      generateConditionAblation: vi.fn().mockResolvedValue("{}"),
      repairMutation: vi.fn().mockResolvedValue("{}"),
    });

    const { createMutationLlmClient } = await import("../../src/cli/llm-factory.js");
    await createMutationLlmClient(
      createRuntimeEnv({
        openAiRequestTimeoutMs: 240_000,
      }),
    );

    expect(createOpenAiCompatibleLlmClient).toHaveBeenCalledWith(
      expect.objectContaining({
        requestTimeoutMs: 240_000,
      }),
    );
  });

  test("retries retryable fetch failures up to the configured retry budget", async () => {
    createOpenAiCompatibleLlmClient.mockReturnValue({
      generateMutation: vi
        .fn()
        .mockRejectedValueOnce(
          new Error(
            "Failed to reach OpenAI-compatible endpoint http://127.0.0.1:10531/v1/chat/completions: fetch failed",
          ),
        )
        .mockResolvedValueOnce("{\"candidateSummary\":\"ok\",\"nextMutationHints\":[],\"pineScript\":\"//@version=5\",\"inventory\":[]}"),
      generateConditionAblation: vi.fn().mockResolvedValue("{}"),
      repairMutation: vi.fn().mockResolvedValue("{}"),
    });

    const { createMutationLlmClient } = await import("../../src/cli/llm-factory.js");
    const client = await createMutationLlmClient(
      createRuntimeEnv({
        openAiMaxRetries: 2,
      }),
    );
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

    expect(result).toContain("\"pineScript\"");
    expect(ensureOpenAiAuthReady).toHaveBeenCalledTimes(2);
    expect(ensureOpenAiAuthReady).toHaveBeenNthCalledWith(2, expect.anything(), {
      forceRestartProxy: true,
    });
  });

  test("retries OpenAI 500 responses through the recovery path", async () => {
    createOpenAiCompatibleLlmClient.mockReturnValue({
      generateMutation: vi
        .fn()
        .mockRejectedValueOnce(
          new Error(
            "LLM request failed with status 500 at http://127.0.0.1:10531/v1/chat/completions.",
          ),
        )
        .mockResolvedValueOnce(
          "{\"candidateSummary\":\"ok\",\"nextMutationHints\":[],\"pineScript\":\"//@version=5\",\"inventory\":[]}",
        ),
      generateConditionAblation: vi.fn().mockResolvedValue("{}"),
      repairMutation: vi.fn().mockResolvedValue("{}"),
    });

    const { createMutationLlmClient } = await import("../../src/cli/llm-factory.js");
    const client = await createMutationLlmClient(createRuntimeEnv());
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

    expect(result).toContain("\"pineScript\"");
    expect(ensureOpenAiAuthReady).toHaveBeenCalledTimes(2);
    expect(ensureOpenAiAuthReady).toHaveBeenNthCalledWith(2, expect.anything(), {
      forceRestartProxy: true,
    });
  });

  test("does not retry non-retryable failures", async () => {
    createOpenAiCompatibleLlmClient.mockReturnValue({
      generateMutation: vi.fn().mockRejectedValueOnce(
        new Error("LLM request failed with status 400 at http://127.0.0.1:10531/v1/chat/completions."),
      ),
      generateConditionAblation: vi.fn().mockResolvedValue("{}"),
      repairMutation: vi.fn().mockResolvedValue("{}"),
    });

    const { createMutationLlmClient } = await import("../../src/cli/llm-factory.js");
    const client = await createMutationLlmClient(createRuntimeEnv());

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
    ).rejects.toThrow(/status 400/);

    expect(ensureOpenAiAuthReady).toHaveBeenCalledTimes(1);
  });

  test("retries once after OpenAI request timeout", async () => {
    createOpenAiCompatibleLlmClient.mockReturnValue({
      generateMutation: vi
        .fn()
        .mockRejectedValueOnce(
          new Error(
            "OpenAI-compatible endpoint http://127.0.0.1:10531/v1/chat/completions timed out after 180000ms.",
          ),
        )
        .mockRejectedValueOnce(
          new Error(
            "OpenAI-compatible endpoint http://127.0.0.1:10531/v1/chat/completions timed out after 180000ms.",
          ),
        )
        .mockResolvedValueOnce(
          "{\"candidateSummary\":\"ok\",\"nextMutationHints\":[],\"pineScript\":\"//@version=5\",\"inventory\":[]}",
        ),
      generateConditionAblation: vi.fn().mockResolvedValue("{}"),
      repairMutation: vi.fn().mockResolvedValue("{}"),
    });

    const { createMutationLlmClient } = await import("../../src/cli/llm-factory.js");
    const client = await createMutationLlmClient(
      createRuntimeEnv({
        openAiMaxRetries: 2,
      }),
    );
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

    expect(result).toContain("\"pineScript\"");
    expect(ensureOpenAiAuthReady).toHaveBeenCalledTimes(3);
    expect(ensureOpenAiAuthReady).toHaveBeenNthCalledWith(2, expect.anything(), {
      forceRestartProxy: true,
    });
    expect(ensureOpenAiAuthReady).toHaveBeenNthCalledWith(3, expect.anything(), {
      forceRestartProxy: true,
    });
  });
});
