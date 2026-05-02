import { LocalAfBacktestExecutor } from "../automation/local-backtest/executor.js";
import { TradingViewDesktopExecutor } from "../automation/tradingview/playwright-driver.js";
import { type PineEvaluationExecutor } from "../automation/common/executor.js";
import { type RuntimeEnvironment } from "./runtime-config.js";

export function createPineEvaluationExecutor(
  env: RuntimeEnvironment,
  executorName = env.evaluationExecutor,
): PineEvaluationExecutor {
  if (env.evaluationUseMock) {
    throw new Error(
      "Mock Pine evaluation executors are forbidden by project policy. Configure the real executor instead.",
    );
  }

  if (executorName === "local-backtest") {
    return new LocalAfBacktestExecutor({
      workspaceRoot: env.workspaceRoot,
      stateRoot: env.stateRoot,
    });
  }

  return new TradingViewDesktopExecutor({
    executablePath: env.tradingViewDesktopPath,
    cdpUrl: env.tradingViewCdpUrl,
    pineEditorTimeoutMs: env.pineEditorTimeoutMs,
    cdpCommandTimeoutMs: env.tradingViewCdpCommandTimeoutMs,
  });
}
