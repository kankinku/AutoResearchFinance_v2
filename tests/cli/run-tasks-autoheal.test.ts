import { describe, expect, test, vi } from "vitest";

import { createMockPineEvaluationExecutor } from "../../src/automation/tradingview/mock-driver.js";
import {
  __test__,
  createAutomaticTaskBatchRecoveryHooks,
} from "../../src/cli/run-tasks-autoheal.js";
import { type RuntimeEnvironment } from "../../src/cli/runtime-config.js";

function createTestEnv(): RuntimeEnvironment {
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
    tradingViewDesktopPath: undefined,
    tradingViewCdpUrl: "http://127.0.0.1:9222",
    pineEditorTimeoutMs: 15_000,
    tradingViewCdpCommandTimeoutMs: 8_000,
    chartSymbol: "QQQ",
    chartTimeframe: "120",
    chartType: "candles",
    maxTrades: 50,
    researchRefreshEveryTasks: 3,
    alphaXivMcpUrl: "https://api.alphaxiv.org/mcp/v1",
    alphaXivMcpBearerToken: "token",
    alphaXivAuthFilePath: undefined,
    alphaXivSessionFilePath: undefined,
    tvCalibrationMode: "live",
    mutationSchemaMode: "strict",
    autonomousBootstrapMode: "disabled",
    autoProcessCalibration: false,
    calibrationBudget: 1,
    calibrationTimeoutMs: 30_000,
  };
}

describe("run-tasks automatic recovery", () => {
  test("classifies OpenAI failures for automatic recovery", () => {
    expect(
      __test__.inferAutomaticRecoverySurface({
        decision: "mutation_generation_fail",
        failureDetail: "LLM offline",
      }),
    ).toBe("openai");
  });

  test("classifies OpenAI 500 failures for automatic recovery", () => {
    expect(
      __test__.inferAutomaticRecoverySurface({
        decision: "mutation_generation_fail",
        failureDetail:
          "LLM request failed with status 500 at http://127.0.0.1:10531/v1/chat/completions.",
      }),
    ).toBe("openai");
    expect(
      __test__.shouldForceOpenAiProxyRestart(
        createTestEnv(),
        "LLM request failed with status 500 at http://127.0.0.1:10531/v1/chat/completions.",
      ),
    ).toBe(true);
  });

  test("classifies TradingView surface failures for automatic recovery", () => {
    expect(
      __test__.inferAutomaticRecoverySurface({
        failureDetail: "Pine editor open timed out after 30000ms.",
      }),
    ).toBe("tradingview");
  });

  test("revalidates OpenAI auth when a recoverable LLM failure occurs", async () => {
    const ensureOpenAiAuthReady = vi.fn(async () => ({
      authMode: "oauth_proxy" as const,
      authConfigured: true,
      reachable: true,
      status: 200,
      proxyStarted: false,
      proxyRestarted: false,
      authFilePath: "auth.json",
    }));
    const ensureAlphaXivAuthReady = vi.fn(async () => ({
      authConfigured: true,
      reachable: true,
      status: 200,
      authMethod: "bearer" as const,
      authFilePath: null,
      sessionFilePath: null,
      error: null,
    }));

    const hooks = createAutomaticTaskBatchRecoveryHooks({
      env: createTestEnv(),
      dependencies: {
        ensureOpenAiAuthReady,
        ensureAlphaXivAuthReady,
      },
    });

    const recovery = await hooks.onFailure?.({
      workspaceRoot: process.cwd(),
      stateRoot: process.cwd(),
      runId: "run-1",
      batchId: "batch-1",
      taskId: "batch-1-task-01",
      taskNumber: 1,
      attempt: 1,
      currentExecutor: createMockPineEvaluationExecutor(),
      decision: "mutation_generation_fail",
      failureDetail: "LLM offline",
    });

    expect(ensureOpenAiAuthReady).toHaveBeenCalledTimes(1);
    expect(recovery).toMatchObject({
      recovered: true,
      recoveryActions: ["revalidated_openai_auth"],
    });
  });

  test("forces proxy restart for timeout-style OpenAI failures", async () => {
    const ensureOpenAiAuthReady = vi.fn(async () => ({
      authMode: "oauth_proxy" as const,
      authConfigured: true,
      reachable: true,
      status: 200,
      proxyStarted: true,
      proxyRestarted: true,
      authFilePath: "auth.json",
    }));

    const hooks = createAutomaticTaskBatchRecoveryHooks({
      env: createTestEnv(),
      dependencies: {
        ensureOpenAiAuthReady,
        ensureAlphaXivAuthReady: async () => ({
          authConfigured: true,
          reachable: true,
          status: 200,
          authMethod: "bearer" as const,
          authFilePath: null,
          sessionFilePath: null,
          error: null,
        }),
      },
    });

    await hooks.onFailure?.({
      workspaceRoot: process.cwd(),
      stateRoot: process.cwd(),
      runId: "run-timeout",
      batchId: "batch-timeout",
      taskId: "batch-timeout-task-01",
      taskNumber: 1,
      attempt: 1,
      currentExecutor: createMockPineEvaluationExecutor(),
      decision: "mutation_generation_fail",
      failureDetail:
        "OpenAI-compatible endpoint http://127.0.0.1:10531/v1/chat/completions timed out after 180000ms.",
    });

    expect(ensureOpenAiAuthReady).toHaveBeenCalledWith(expect.anything(), {
      forceRestartProxy: true,
    });
  });

  test("replaces the executor when TradingView surface recovery is needed", async () => {
    const currentExecutor = {
      role: "external_calibration" as const,
      evidenceAuthority: "external_tv" as const,
      supportedStrategyFamilies: ["Pine"],
      supportedSymbols: ["QQQ"],
      supportedTimeframes: ["120"],
      getCapability() {
        return {
          kind: "tradingview-live" as const,
          authoritative: true,
          supportedSymbols: ["QQQ"],
          supportedTimeframes: ["120"],
          supportedStrategyFamilies: ["Pine"],
          confidenceLevel: "verification" as const,
        };
      },
      async healthCheck() {
        return {
          healthy: false,
          status: "degraded" as const,
          detail: "test stub",
        };
      },
      async prepareChart() {
        throw new Error("current executor still broken");
      },
      async updateStrategySource() {
        return;
      },
      async compileStrategy() {
        return { ok: true, errors: [] };
      },
      async applyStrategy() {
        return { ok: true, message: "ok", fallbackActions: [] };
      },
      async readArtifactBundle() {
        return {
          strategy: null,
          trades: [],
          equity: {
            available: false,
            unavailableReason: null,
            pointsAvailable: false,
            pointCount: 0,
            finalEquity: null,
            maxDrawdownPercent: null,
            points: [],
          },
          state: {},
        };
      },
      async close() {
        return;
      },
    };
    const replacementExecutor = createMockPineEvaluationExecutor();
    const hooks = createAutomaticTaskBatchRecoveryHooks({
      env: createTestEnv(),
      executorFactory: () => replacementExecutor,
      dependencies: {
        ensureOpenAiAuthReady: async () => ({
          authMode: "oauth_proxy",
          authConfigured: true,
          reachable: true,
          status: 200,
          proxyStarted: false,
          proxyRestarted: false,
          authFilePath: "auth.json",
        }),
        ensureAlphaXivAuthReady: async () => ({
          authConfigured: true,
          reachable: true,
          status: 200,
          authMethod: "bearer",
          authFilePath: null,
          sessionFilePath: null,
          error: null,
        }),
      },
    });

    const recovery = await hooks.onFailure?.({
      workspaceRoot: process.cwd(),
      stateRoot: process.cwd(),
      runId: "run-2",
      batchId: "batch-2",
      taskId: "batch-2-task-01",
      taskNumber: 1,
      attempt: 1,
      currentExecutor,
      error: new Error("Pine editor open timed out after 30000ms."),
      failureDetail: "Pine editor open timed out after 30000ms.",
    });

    expect(recovery?.recovered).toBe(true);
    expect(recovery?.recoveryActions).toContain("reinitialized_tradingview_surface");
    expect(recovery?.executor).toBe(replacementExecutor);
  });
});
