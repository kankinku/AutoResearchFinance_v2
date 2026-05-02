import { type PineEvaluationExecutor } from "../automation/common/executor.js";
import {
  type TaskBatchRecoveryContext,
  type TaskBatchRecoveryHooks,
  type TaskBatchRecoveryOutcome,
} from "../research/task-batch-runner.js";
import { type RuntimeEnvironment } from "./runtime-config.js";
import { ensureAlphaXivAuthReady, type AlphaXivAuthStatus } from "./alphaxiv-auth.js";
import { createPineEvaluationExecutor } from "./executor-factory.js";
import {
  ensureOpenAiAuthReady,
  type EnsureOpenAiAuthOptions,
  type OpenAiAuthStatus,
} from "./openai-oauth.js";

type RecoverySurface = "openai" | "tradingview" | "alphaxiv";

interface RecoveryMonitor {
  log(
    event: string,
    message: string,
    details?: Record<string, unknown>,
  ): Promise<void>;
}

interface AutoHealDependencies {
  ensureOpenAiAuthReady: (
    env: RuntimeEnvironment,
    options?: EnsureOpenAiAuthOptions,
  ) => Promise<OpenAiAuthStatus>;
  ensureAlphaXivAuthReady: (
    env: RuntimeEnvironment,
  ) => Promise<AlphaXivAuthStatus>;
}

export function createAutomaticTaskBatchRecoveryHooks(input: {
  env: RuntimeEnvironment;
  monitor?: RecoveryMonitor;
  executorFactory?: () => PineEvaluationExecutor;
  dependencies?: Partial<AutoHealDependencies>;
}): TaskBatchRecoveryHooks {
  const executorFactory =
    input.executorFactory ?? (() => createPineEvaluationExecutor(input.env));
  const dependencies: AutoHealDependencies = {
    ensureOpenAiAuthReady,
    ensureAlphaXivAuthReady,
    ...input.dependencies,
  };

  return {
    beforeBatch: async (context) => {
      await input.monitor?.log(
        "task.system_check",
        "Running task batch system checks",
        {
          batchId: context.batchId,
          taskCount: context.taskCount,
        },
      );

      const recoveryActions: string[] = [];
      const openAiStatus = await dependencies.ensureOpenAiAuthReady(input.env);
      if (openAiStatus.proxyStarted) {
        recoveryActions.push("started_openai_oauth_proxy");
      }

      const alphaXivStatus = await dependencies.ensureAlphaXivAuthReady(input.env).catch(
        () => null,
      );
      if (alphaXivStatus?.reachable) {
        recoveryActions.push("verified_alphaxiv_auth");
      }

      try {
        await context.currentExecutor.prepareChart(resolveChartTarget(input.env));
      } catch {
        const replacementExecutor = executorFactory();
        try {
          await replacementExecutor.prepareChart(resolveChartTarget(input.env));
          recoveryActions.push("reinitialized_tradingview_surface");
          return {
            recovered: true,
            recoveryActions,
            executor: replacementExecutor,
          };
        } catch (error) {
          await replacementExecutor.close?.();
          throw error;
        }
      }

      return recoveryActions.length > 0
        ? {
            recovered: true,
            recoveryActions,
          }
        : undefined;
    },
    onFailure: async (context) => {
      const surface = inferAutomaticRecoverySurface(context);
      if (!surface) {
        return {
          recovered: false,
          recoveryActions: [],
        };
      }

      await input.monitor?.log(
        "task.system_recovery",
        "Attempting automatic task recovery",
        {
          taskId: context.taskId,
          taskNumber: context.taskNumber,
          surface,
          detail: context.failureDetail ?? context.error?.message ?? null,
        },
      );

      return await recoverBySurface({
        surface,
        env: input.env,
        executorFactory,
        dependencies,
        failureText: context.failureDetail ?? context.error?.message ?? "",
      });
    },
  };
}

async function recoverBySurface(input: {
  surface: RecoverySurface;
  env: RuntimeEnvironment;
  executorFactory: () => PineEvaluationExecutor;
  dependencies: AutoHealDependencies;
  failureText: string;
}): Promise<TaskBatchRecoveryOutcome> {
  if (input.surface === "openai") {
    const status = await input.dependencies.ensureOpenAiAuthReady(input.env, {
      forceRestartProxy: shouldForceOpenAiProxyRestart(
        input.env,
        input.failureText,
      ),
    });
    if (!status.reachable) {
      return {
        recovered: false,
        recoveryActions: [],
      };
    }

    return {
      recovered: true,
      recoveryActions: [
        status.proxyRestarted
          ? "restarted_openai_oauth_proxy"
          : status.proxyStarted
            ? "started_openai_oauth_proxy"
            : "revalidated_openai_auth",
      ],
    };
  }

  if (input.surface === "alphaxiv") {
    const status = await input.dependencies.ensureAlphaXivAuthReady(input.env);
    return {
      recovered: status.reachable,
      recoveryActions: status.reachable ? ["revalidated_alphaxiv_auth"] : [],
    };
  }

  const replacementExecutor = input.executorFactory();
  try {
    await replacementExecutor.prepareChart(resolveChartTarget(input.env));
    return {
      recovered: true,
      recoveryActions: ["reinitialized_tradingview_surface"],
      executor: replacementExecutor,
    };
  } catch (error) {
    await replacementExecutor.close?.();
    throw error;
  }
}

function resolveChartTarget(env: RuntimeEnvironment): {
  symbol: string;
  timeframe: string;
  chartType: string;
} {
  return {
    symbol: env.chartSymbol,
    timeframe: env.chartTimeframe,
    chartType: env.chartType,
  };
}

export function inferAutomaticRecoverySurface(
  input: Pick<TaskBatchRecoveryContext, "decision" | "failureDetail" | "error">,
): RecoverySurface | null {
  const detail = [
    input.failureDetail ?? "",
    input.error?.message ?? "",
    input.decision ?? "",
  ]
    .join(" ")
    .toLowerCase();

  if (
    /(openai|oauth|auth\.json|proxy|failed to reach openai-compatible endpoint|status 429|status 500|status 502|status 503|status 504|fetch failed|llm offline)/i.test(
      detail,
    )
  ) {
    return "openai";
  }

  if (/(alphaxiv|mcp|session cookies|oauth token)/i.test(detail)) {
    return "alphaxiv";
  }

  if (
    /(tradingview|cdp|pine editor|monaco|chart|study attachment|strategy tester metrics|stale attach|geteditors)/i.test(
      detail,
    )
  ) {
    return "tradingview";
  }

  return null;
}

function shouldForceOpenAiProxyRestart(
  env: RuntimeEnvironment,
  failureText: string,
): boolean {
  if (env.openAiAuthMode !== "oauth_proxy") {
    return false;
  }

  return /(timed out|fetch failed|status 500|status 502|status 503|status 504|failed to reach openai-compatible endpoint)/i.test(
    failureText,
  );
}

export const __test__ = {
  inferAutomaticRecoverySurface,
  shouldForceOpenAiProxyRestart,
};
