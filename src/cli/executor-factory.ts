import path from "node:path";

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

  const isWebTradingView = executorName === "tradingview-web-playwright";
  return new TradingViewDesktopExecutor({
    surface: isWebTradingView ? "web" : "desktop",
    executablePath: isWebTradingView
      ? env.tradingViewWebBrowserPath
      : env.tradingViewDesktopPath,
    cdpUrl: isWebTradingView
      ? env.tradingViewWebCdpUrl
      : env.tradingViewCdpUrl,
    webProfileDir:
      env.tradingViewWebProfileDir ??
      path.join(env.runtimeRoot ?? env.stateRoot, "tradingview-web-profile"),
    webChartUrl: env.tradingViewWebChartUrl,
    webHeadless: env.tradingViewWebHeadless,
    pineEditorTimeoutMs: env.pineEditorTimeoutMs,
    cdpCommandTimeoutMs: env.tradingViewCdpCommandTimeoutMs,
  });
}
