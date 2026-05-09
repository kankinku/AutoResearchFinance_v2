import { describe, expect, test } from "vitest";

import { createPineEvaluationExecutor } from "../../src/cli/executor-factory.js";
import { createMutationLlmClient } from "../../src/cli/llm-factory.js";
import { assertNoMockPolicy, type RuntimeEnvironment } from "../../src/cli/runtime-config.js";

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
    evaluationExecutor: "local-backtest",
    promotionVerificationExecutor: "none",
    chartSymbol: "QQQ",
    chartTimeframe: "120",
    chartType: "candles",
    maxTrades: 50,
    researchRefreshEveryTasks: 3,
    alphaXivMcpUrl: "https://api.alphaxiv.org/mcp/v1",
    alphaXivMcpBearerToken: undefined,
    alphaXivAuthFilePath: undefined,
    alphaXivSessionFilePath: undefined,
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

describe("mock policy", () => {
  test("rejects mock configuration at runtime-policy level", () => {
    expect(() =>
      assertNoMockPolicy(
        createRuntimeEnv({
          evaluationUseMock: true,
        }),
      ),
    ).toThrow(/Mock Pine evaluation executors are forbidden/);

    expect(() =>
      assertNoMockPolicy(
        createRuntimeEnv({
          mutationStaticResponsePath: "config/mock-mutation-response.json",
        }),
      ),
    ).toThrow(/Static mutation responses are forbidden/);
  });

  test("driver factory refuses mock driver creation", () => {
    expect(() =>
      createPineEvaluationExecutor(
        createRuntimeEnv({
          evaluationUseMock: true,
        }),
      ),
    ).toThrow(/Mock Pine evaluation executors are forbidden/);
  });

  test("llm factory refuses static mutation responses", async () => {
    await expect(
      createMutationLlmClient(
        createRuntimeEnv({
          mutationStaticResponsePath: "config/mock-mutation-response.json",
        }),
      ),
    ).rejects.toThrow(/Static mutation responses are forbidden/);
  });
});
