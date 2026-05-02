import { readFile } from "node:fs/promises";
import path from "node:path";

import { type MarketContextBar } from "../contracts/types.js";
import { resolveKnowledgePaths } from "../state/knowledge-paths.js";
import { fileExists, readJson, writeJson } from "../utils/fs.js";

interface HourlyBar {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

function average(values: number[]): number {
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function standardDeviation(values: number[]): number {
  const mean = average(values);
  const variance =
    values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / values.length;
  return Math.sqrt(variance);
}

function computeEma(values: number[], period: number): Array<number | null> {
  const multiplier = 2 / (period + 1);
  const result: Array<number | null> = [];
  let ema: number | null = null;

  for (let index = 0; index < values.length; index += 1) {
    const value = values[index];
    if (index < period - 1) {
      result.push(null);
      continue;
    }
    if (ema === null) {
      ema = average(values.slice(index - period + 1, index + 1));
    } else {
      ema = (value - ema) * multiplier + ema;
    }
    result.push(ema);
  }

  return result;
}

function computeAtr(bars: HourlyBar[], period: number): Array<number | null> {
  const trueRanges = bars.map((bar, index) => {
    const prevClose = index > 0 ? bars[index - 1].close : bar.close;
    return Math.max(
      bar.high - bar.low,
      Math.abs(bar.high - prevClose),
      Math.abs(bar.low - prevClose),
    );
  });

  const result: Array<number | null> = [];
  let atr: number | null = null;
  for (let index = 0; index < trueRanges.length; index += 1) {
    const tr = trueRanges[index];
    if (index < period - 1) {
      result.push(null);
      continue;
    }
    if (atr === null) {
      atr = average(trueRanges.slice(index - period + 1, index + 1));
    } else {
      atr = (atr * (period - 1) + tr) / period;
    }
    result.push(atr);
  }
  return result;
}

function computeRsi(values: number[], period: number): Array<number | null> {
  const result: Array<number | null> = [];
  let avgGain: number | null = null;
  let avgLoss: number | null = null;

  for (let index = 0; index < values.length; index += 1) {
    if (index === 0) {
      result.push(null);
      continue;
    }
    const delta = values[index] - values[index - 1];
    const gain = Math.max(delta, 0);
    const loss = Math.max(-delta, 0);

    if (index < period) {
      result.push(null);
      continue;
    }

    if (avgGain === null || avgLoss === null) {
      const gains: number[] = [];
      const losses: number[] = [];
      for (let cursor = 1; cursor <= period; cursor += 1) {
        const diff = values[cursor] - values[cursor - 1];
        gains.push(Math.max(diff, 0));
        losses.push(Math.max(-diff, 0));
      }
      avgGain = average(gains);
      avgLoss = average(losses);
    } else {
      avgGain = (avgGain * (period - 1) + gain) / period;
      avgLoss = (avgLoss * (period - 1) + loss) / period;
    }

    if (avgLoss === 0) {
      result.push(100);
      continue;
    }

    const relativeStrength = avgGain / avgLoss;
    result.push(100 - 100 / (1 + relativeStrength));
  }

  return result;
}

function computeBbWidth(values: number[], period: number): Array<number | null> {
  return values.map((value, index) => {
    if (index < period - 1) {
      return null;
    }
    const window = values.slice(index - period + 1, index + 1);
    const mean = average(window);
    if (mean === 0) {
      return null;
    }
    const stddev = standardDeviation(window);
    return (stddev * 4) / mean;
  });
}

function computeReturn(values: number[], lookback: number): Array<number | null> {
  return values.map((value, index) => {
    if (index < lookback) {
      return null;
    }
    const previous = values[index - lookback];
    if (previous === 0) {
      return null;
    }
    return (value - previous) / previous;
  });
}

function enrichTwoHourBars(bars: HourlyBar[]): MarketContextBar[] {
  const closes = bars.map((bar) => bar.close);
  const ema20 = computeEma(closes, 20);
  const ema50 = computeEma(closes, 50);
  const ema200 = computeEma(closes, 200);
  const atr14 = computeAtr(bars, 14);
  const rsi14 = computeRsi(closes, 14);
  const bbWidth = computeBbWidth(closes, 20);
  const ret3 = computeReturn(closes, 3);
  const ret10 = computeReturn(closes, 10);

  return bars.map((bar, index) => {
    const atrPercent =
      atr14[index] !== null && bar.close !== 0 ? (atr14[index] as number) / bar.close * 100 : null;
    return {
      time: bar.time,
      open: bar.open,
      high: bar.high,
      low: bar.low,
      close: bar.close,
      volume: bar.volume,
      ema20: ema20[index],
      ema50: ema50[index],
      ema200: ema200[index],
      atr14: atr14[index],
      atrPercent,
      rsi14: rsi14[index],
      bbWidth: bbWidth[index],
      ret3: ret3[index],
      ret10: ret10[index],
      regime: classifyMarketRegime({
        close: bar.close,
        ema20: ema20[index],
        ema50: ema50[index],
        ema200: ema200[index],
        atrPercent,
        bbWidth: bbWidth[index],
      }),
    };
  });
}

function extractHourlyBars(payload: any): HourlyBar[] {
  const result = payload?.chart?.result?.[0];
  const timestamps: number[] = result?.timestamp ?? [];
  const quote = result?.indicators?.quote?.[0];
  const opens: Array<number | null> = quote?.open ?? [];
  const highs: Array<number | null> = quote?.high ?? [];
  const lows: Array<number | null> = quote?.low ?? [];
  const closes: Array<number | null> = quote?.close ?? [];
  const volumes: Array<number | null> = quote?.volume ?? [];

  return timestamps
    .map((timestamp, index) => ({
      time: new Date(timestamp * 1000).toISOString(),
      open: opens[index],
      high: highs[index],
      low: lows[index],
      close: closes[index],
      volume: volumes[index] ?? 0,
    }))
    .filter(
      (bar): bar is HourlyBar =>
        bar.open !== null &&
        bar.high !== null &&
        bar.low !== null &&
        bar.close !== null,
    );
}

export function buildTwoHourBars(hourlyBars: HourlyBar[]): HourlyBar[] {
  const result: HourlyBar[] = [];
  for (let index = 0; index < hourlyBars.length; index += 2) {
    const first = hourlyBars[index];
    const second = hourlyBars[index + 1];
    if (!first || !second) {
      break;
    }
    result.push({
      time: first.time,
      open: first.open,
      high: Math.max(first.high, second.high),
      low: Math.min(first.low, second.low),
      close: second.close,
      volume: first.volume + second.volume,
    });
  }
  return result;
}

export function classifyMarketRegime(input: {
  close: number;
  ema20: number | null;
  ema50: number | null;
  ema200: number | null;
  atrPercent: number | null;
  bbWidth: number | null;
}): string {
  if (
    input.ema20 !== null &&
    input.ema50 !== null &&
    input.ema200 !== null &&
    input.close < input.ema20 &&
    input.ema20 < input.ema50 &&
    input.ema50 < input.ema200
  ) {
    return "trend_down";
  }
  if (
    input.ema20 !== null &&
    input.ema50 !== null &&
    input.ema200 !== null &&
    input.close > input.ema20 &&
    input.ema20 > input.ema50 &&
    input.ema50 > input.ema200
  ) {
    return "trend_up";
  }
  if ((input.bbWidth ?? 0) <= 0.03) {
    return "range_squeeze";
  }
  if ((input.atrPercent ?? 0) >= 2.5) {
    return "volatile";
  }
  return "range";
}

export async function loadQqqTwoHourContext(
  workspaceRoot: string,
  options?: {
    fetchImpl?: typeof fetch;
    forceRefresh?: boolean;
    stateRoot?: string;
  },
): Promise<{ bars: MarketContextBar[]; cachePath: string; fromCache: boolean }> {
  const stateRoot = resolveMarketContextStateRoot(workspaceRoot, options?.stateRoot);
  const cachePath = resolveKnowledgePaths(stateRoot).qqqTwoHourContextPath;

  if (!options?.forceRefresh && (await fileExists(cachePath))) {
    const cached = await readJson<{ bars: MarketContextBar[] }>(cachePath);
    return {
      bars: cached.bars,
      cachePath,
      fromCache: true,
    };
  }

  const fetchImpl = options?.fetchImpl ?? fetch;
  const response = await fetchImpl(
    "https://query1.finance.yahoo.com/v8/finance/chart/QQQ?range=730d&interval=1h",
  );
  if (!response.ok) {
    if (await fileExists(cachePath)) {
      const cached = JSON.parse(await readFile(cachePath, "utf8")) as {
        bars: MarketContextBar[];
      };
      return {
        bars: cached.bars,
        cachePath,
        fromCache: true,
      };
    }
    throw new Error(`Failed to fetch QQQ 1h context: ${response.status}`);
  }

  const payload = await response.json();
  const hourlyBars = extractHourlyBars(payload);
  const bars = enrichTwoHourBars(buildTwoHourBars(hourlyBars));
  await writeJson(cachePath, {
    generatedAt: new Date().toISOString(),
    symbol: "QQQ",
    timeframe: "2h",
    bars,
  });
  return {
    bars,
    cachePath,
    fromCache: false,
  };
}

export async function ensureQqqTwoHourContext(
  workspaceRoot: string,
  options?: {
    fetchImpl?: typeof fetch;
    stateRoot?: string;
  },
): Promise<{ bars: MarketContextBar[]; cachePath: string; fromCache: boolean }> {
  const stateRoot = resolveMarketContextStateRoot(workspaceRoot, options?.stateRoot);
  const cachePath = resolveKnowledgePaths(stateRoot).qqqTwoHourContextPath;

  if (await fileExists(cachePath)) {
    try {
      const cached = await readJson<{ bars?: MarketContextBar[] }>(cachePath);
      if (Array.isArray(cached.bars) && cached.bars.length > 0) {
        return {
          bars: cached.bars,
          cachePath,
          fromCache: true,
        };
      }
    } catch {
      // Fall through to a forced refresh when the cache is unreadable.
    }
  }

  return loadQqqTwoHourContext(workspaceRoot, {
    fetchImpl: options?.fetchImpl,
    forceRefresh: true,
    stateRoot,
  });
}

function resolveMarketContextStateRoot(
  workspaceRoot: string,
  stateRoot?: string,
): string {
  return stateRoot
    ? path.resolve(stateRoot)
    : path.join(workspaceRoot, "state", "pi-autoresearch");
}
