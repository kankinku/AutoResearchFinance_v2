import { type MarketContextBar } from "../../contracts/types.js";
import { ensureQqqTwoHourContext } from "../../research/market-context.js";

export async function loadLocalBacktestBars(
  workspaceRoot: string,
  options?: { stateRoot?: string },
): Promise<MarketContextBar[]> {
  const payload = await ensureQqqTwoHourContext(workspaceRoot, {
    stateRoot: options?.stateRoot,
  });
  const bars = payload.bars;
  if (bars.length === 0) {
    throw new Error(
      `Local backtest executor could not load QQQ 2h context from ${payload.cachePath}.`,
    );
  }

  return bars as MarketContextBar[];
}
