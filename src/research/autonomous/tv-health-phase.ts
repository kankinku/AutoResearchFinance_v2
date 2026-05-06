import { type RuntimeEnvironment } from "../../cli/runtime-config.js";

export type TvHealthStatus = "healthy" | "degraded" | "unavailable";

export function resolveTvHealthStatus(
  env: Pick<
    RuntimeEnvironment,
    | "promotionVerificationExecutor"
    | "tradingViewCdpUrl"
    | "tradingViewDesktopPath"
    | "tradingViewWebCdpUrl"
    | "tradingViewWebProfileDir"
  >,
): TvHealthStatus {
  if (env.promotionVerificationExecutor === "tradingview-web-playwright") {
    return "healthy";
  }

  if (env.promotionVerificationExecutor !== "tradingview-desktop-cdp") {
    return "unavailable";
  }

  if (!env.tradingViewCdpUrl && !env.tradingViewDesktopPath) {
    return "degraded";
  }

  return "healthy";
}
