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

export interface MarketContextTarget {
  symbol: string;
  timeframe: string;
}

interface MarketContextRequest {
  yahooSymbol: string;
  interval: string;
  range: string;
  aggregationBars: number;
  timeframeMinutes: number;
  normalizedSymbol: string;
  normalizedTimeframe: string;
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

function enrichMarketBars(bars: HourlyBar[]): MarketContextBar[] {
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
  return buildAggregatedBars(hourlyBars, 2);
}

export function buildAggregatedBars(
  sourceBars: HourlyBar[],
  aggregationBars: number,
): HourlyBar[] {
  if (aggregationBars <= 1) {
    return sourceBars;
  }

  const result: HourlyBar[] = [];
  for (let index = 0; index < sourceBars.length; index += aggregationBars) {
    const window = sourceBars.slice(index, index + aggregationBars);
    if (window.length < aggregationBars) {
      break;
    }
    const first = window[0];
    const last = window.at(-1);
    if (!first || !last) {
      break;
    }
    result.push({
      time: first.time,
      open: first.open,
      high: Math.max(...window.map((bar) => bar.high)),
      low: Math.min(...window.map((bar) => bar.low)),
      close: last.close,
      volume: window.reduce((sum, bar) => sum + bar.volume, 0),
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
  return loadMarketContext(
    workspaceRoot,
    {
      symbol: "QQQ",
      timeframe: "120",
    },
    options,
  );
}

export async function ensureQqqTwoHourContext(
  workspaceRoot: string,
  options?: {
    fetchImpl?: typeof fetch;
    stateRoot?: string;
  },
): Promise<{ bars: MarketContextBar[]; cachePath: string; fromCache: boolean }> {
  return ensureMarketContext(
    workspaceRoot,
    {
      symbol: "QQQ",
      timeframe: "120",
    },
    options,
  );
}

export async function loadMarketContext(
  workspaceRoot: string,
  target: MarketContextTarget,
  options?: {
    fetchImpl?: typeof fetch;
    forceRefresh?: boolean;
    stateRoot?: string;
  },
): Promise<{ bars: MarketContextBar[]; cachePath: string; fromCache: boolean }> {
  const stateRoot = resolveMarketContextStateRoot(workspaceRoot, options?.stateRoot);
  const request = resolveMarketContextRequest(target);
  const cachePath = resolveMarketContextCachePath(stateRoot, request);

  if (!options?.forceRefresh && (await fileExists(cachePath))) {
    const cached = await readJson<{ bars: MarketContextBar[] }>(cachePath);
    return {
      bars: cached.bars,
      cachePath,
      fromCache: true,
    };
  }

  const fetchImpl = options?.fetchImpl ?? fetch;
  const query = new URL(
    `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(request.yahooSymbol)}`,
  );
  query.searchParams.set("range", request.range);
  query.searchParams.set("interval", request.interval);
  const response = await fetchImpl(query);
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
    throw new Error(
      `Failed to fetch ${request.normalizedSymbol} ${request.interval} context: ${response.status}`,
    );
  }

  const payload = await response.json();
  const sourceBars = extractHourlyBars(payload);
  const bars = enrichMarketBars(
    buildAggregatedBars(sourceBars, request.aggregationBars),
  );
  await writeJson(cachePath, {
    generatedAt: new Date().toISOString(),
    symbol: request.normalizedSymbol,
    timeframe: request.normalizedTimeframe,
    yahooSymbol: request.yahooSymbol,
    sourceInterval: request.interval,
    sourceRange: request.range,
    bars,
  });
  return {
    bars,
    cachePath,
    fromCache: false,
  };
}

export async function ensureMarketContext(
  workspaceRoot: string,
  target: MarketContextTarget,
  options?: {
    fetchImpl?: typeof fetch;
    stateRoot?: string;
  },
): Promise<{ bars: MarketContextBar[]; cachePath: string; fromCache: boolean }> {
  const stateRoot = resolveMarketContextStateRoot(workspaceRoot, options?.stateRoot);
  const request = resolveMarketContextRequest(target);
  const cachePath = resolveMarketContextCachePath(stateRoot, request);

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

  return loadMarketContext(workspaceRoot, target, {
    fetchImpl: options?.fetchImpl,
    forceRefresh: true,
    stateRoot,
  });
}

function resolveMarketContextRequest(target: MarketContextTarget): MarketContextRequest {
  const timeframeMinutes = normalizeTimeframeMinutes(target.timeframe);
  const normalizedSymbol = normalizeMarketSymbol(target.symbol);
  const yahooSymbol = resolveYahooSymbol(normalizedSymbol);
  const sourceMinutes = timeframeMinutes <= 30 ? timeframeMinutes : 60;
  const aggregationBars = Math.max(1, Math.round(timeframeMinutes / sourceMinutes));
  const interval =
    sourceMinutes < 60 ? `${sourceMinutes}m` : sourceMinutes === 60 ? "1h" : `${sourceMinutes}m`;
  const range = timeframeMinutes <= 30 ? "60d" : "730d";

  return {
    yahooSymbol,
    interval,
    range,
    aggregationBars,
    timeframeMinutes,
    normalizedSymbol,
    normalizedTimeframe: formatTimeframe(timeframeMinutes),
  };
}

function resolveMarketContextCachePath(
  stateRoot: string,
  request: MarketContextRequest,
): string {
  const paths = resolveKnowledgePaths(stateRoot);
  if (request.normalizedSymbol === "QQQ" && request.timeframeMinutes === 120) {
    return paths.qqqTwoHourContextPath;
  }

  const symbolKey = request.normalizedSymbol.toLowerCase().replace(/[^a-z0-9]+/g, "-");
  return path.join(
    paths.resultsDir,
    `${symbolKey}-${request.normalizedTimeframe}-context.json`,
  );
}

function normalizeMarketSymbol(value: string): string {
  const bare = value.trim().toUpperCase().split(":").at(-1) ?? value.trim().toUpperCase();
  if (bare === "BTC" || bare === "BTCUSD" || bare === "BTCUSDT" || bare === "BTC-USD") {
    return "BTC";
  }
  return bare;
}

function resolveYahooSymbol(normalizedSymbol: string): string {
  if (normalizedSymbol === "BTC") {
    return "BTC-USD";
  }
  return normalizedSymbol;
}

function normalizeTimeframeMinutes(value: string): number {
  const normalized = value.trim().toLowerCase();
  if (normalized.endsWith("h")) {
    const hours = Number.parseFloat(normalized.slice(0, -1));
    if (Number.isFinite(hours) && hours > 0) {
      return Math.round(hours * 60);
    }
  }
  if (normalized.endsWith("m")) {
    const minutes = Number.parseInt(normalized.slice(0, -1), 10);
    if (Number.isFinite(minutes) && minutes > 0) {
      return minutes;
    }
  }
  const minutes = Number.parseInt(normalized, 10);
  if (Number.isFinite(minutes) && minutes > 0) {
    return minutes;
  }
  throw new Error(`Unsupported market context timeframe: ${value}`);
}

function formatTimeframe(minutes: number): string {
  if (minutes % 60 === 0) {
    return `${minutes / 60}h`;
  }
  return `${minutes}m`;
}

function resolveMarketContextStateRoot(
  workspaceRoot: string,
  stateRoot?: string,
): string {
  return stateRoot
    ? path.resolve(stateRoot)
    : path.join(workspaceRoot, "state", "pi-autoresearch");
}
