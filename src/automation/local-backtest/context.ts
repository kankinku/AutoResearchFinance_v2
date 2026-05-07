import { type MarketContextBar } from "../../contracts/types.js";
import {
  ensureMarketContext,
  type MarketContextTarget,
} from "../../research/market-context.js";
import {
  DEFAULT_RESEARCH_TARGET_ID,
  loadResearchTarget,
} from "../../config/target-registry.js";

export async function loadLocalBacktestBars(
  workspaceRoot: string,
  options?: { stateRoot?: string; chartTarget?: MarketContextTarget },
): Promise<MarketContextBar[]> {
  const target = options?.chartTarget ?? resolveDefaultMarketContextTarget(workspaceRoot);
  const payload = await ensureMarketContext(workspaceRoot, target, {
    stateRoot: options?.stateRoot,
  });
  const bars = payload.bars;
  if (bars.length === 0) {
    throw new Error(
      `Local backtest executor could not load ${target.symbol} ${target.timeframe} context from ${payload.cachePath}.`,
    );
  }

  return bars as MarketContextBar[];
}

function resolveDefaultMarketContextTarget(workspaceRoot: string): MarketContextTarget {
  const targetId = process.env.AF_RESEARCH_TARGET_ID ?? DEFAULT_RESEARCH_TARGET_ID;
  const target = loadResearchTarget({
    projectRoot: process.env.AF_PROJECT_ROOT ?? workspaceRoot,
    workspaceRoot,
    targetId,
  });
  return {
    symbol: process.env.TRADINGVIEW_CHART_SYMBOL ?? target.symbol,
    timeframe: process.env.TRADINGVIEW_CHART_TIMEFRAME ?? target.timeframe,
  };
}
