import { type RuntimeEnvironment } from "../../cli/runtime-config.js";

export type TvHealthStatus = "healthy" | "degraded" | "unavailable";

export function resolveTvHealthStatus(
  env: Pick<RuntimeEnvironment, "promotionVerificationExecutor" | "tradingViewCdpUrl" | "tradingViewDesktopPath">,
): TvHealthStatus {
  if (env.promotionVerificationExecutor !== "tradingview-desktop-cdp") {
    return "unavailable";
  }

  if (!env.tradingViewCdpUrl && !env.tradingViewDesktopPath) {
    return "degraded";
  }

  return "healthy";
}
