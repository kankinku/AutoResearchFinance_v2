import {
  backtestMetricsSchema,
  equitySummarySchema,
  tradeRecordSchema,
  type BacktestMetrics,
  type EquitySummary,
  type TraceEventV1,
  type TradeRecord,
} from "../../contracts/types.js";
import { extractTraceEventsFromUnknownReportData } from "./trace-artifact.js";

interface RawTradeLeg {
  c?: string;
  p?: number;
  tm?: number;
}

interface RawTradeProfit {
  v?: number;
  p?: number;
}

interface RawTrade {
  e?: RawTradeLeg;
  x?: RawTradeLeg;
  q?: number;
  cp?: RawTradeProfit;
  rn?: RawTradeProfit;
  dd?: RawTradeProfit;
}

interface RawReportDataPerformanceAll {
  netProfitPercent?: number;
  profitFactor?: number;
  percentProfitable?: number;
  avgTradePercent?: number;
}

interface RawReportDataPerformance {
  all?: RawReportDataPerformanceAll;
  maxStrategyDrawDownPercent?: number;
  sharpeRatio?: number;
  sortinoRatio?: number;
}

export interface RawStrategyReportData {
  performance?: RawReportDataPerformance;
  trades?: RawTrade[];
  currency?: string | null;
  buyHold?: number[];
  buyHoldPercent?: number[];
}

export const TRADINGVIEW_REPORT_PARSER_VERSION = "tradingview-report/v2";

export interface ReportDataInspection {
  hasNetProfit: boolean;
  hasTotalTrades: boolean;
  hasMaxDrawdown: boolean;
  hasProfitFactor: boolean;
  hasWinRate: boolean;
  hasTrades: boolean;
  hasEquitySummary: boolean;
  hasRawReport: boolean;
  missingFields: string[];
  parseWarnings: string[];
  parserVersion: string;
}

export function extractBacktestMetricsFromReportData(
  reportData: RawStrategyReportData | null | undefined,
): BacktestMetrics | null {
  if (!reportData?.performance?.all) {
    return null;
  }

  const performanceAll = reportData.performance.all;
  const trades = reportData.trades ?? [];
  return backtestMetricsSchema.parse({
    netProfitPercent: ratioToPercent(performanceAll.netProfitPercent),
    postFeeNetProfitPercent: ratioToPercent(performanceAll.netProfitPercent),
    profitFactor: toFiniteNumber(performanceAll.profitFactor),
    maxStrategyDrawdownPercent: ratioToPercent(
      reportData.performance.maxStrategyDrawDownPercent,
    ),
    percentProfitable: ratioToPercent(performanceAll.percentProfitable),
    totalTrades: trades.length,
    avgTradePercent: ratioToPercent(performanceAll.avgTradePercent),
  });
}

export function inspectReportData(
  reportData: RawStrategyReportData | null | undefined,
): ReportDataInspection {
  const missingFields: string[] = [];
  const parseWarnings: string[] = [];
  const hasRawReport = reportData != null;
  const performanceAll = reportData?.performance?.all;
  const hasNetProfit = isFiniteNumber(performanceAll?.netProfitPercent);
  const hasProfitFactor = isFiniteNumber(performanceAll?.profitFactor);
  const hasWinRate = isFiniteNumber(performanceAll?.percentProfitable);
  const hasMaxDrawdown = isFiniteNumber(
    reportData?.performance?.maxStrategyDrawDownPercent,
  );
  const hasTrades = Array.isArray(reportData?.trades);
  const hasTotalTrades = hasTrades;
  const hasEquitySummary =
    hasFiniteNumberArray(reportData?.buyHold) ||
    hasFiniteNumberArray(reportData?.buyHoldPercent);

  if (!hasNetProfit) {
    missingFields.push("net_profit");
  }
  if (!hasTotalTrades) {
    missingFields.push("total_trades");
  }
  if (!hasMaxDrawdown) {
    missingFields.push("max_drawdown");
  }
  if (!hasProfitFactor) {
    missingFields.push("profit_factor");
  }
  if (!hasWinRate) {
    missingFields.push("win_rate");
  }
  if (!hasTrades) {
    missingFields.push("trades");
  }
  if (!hasEquitySummary) {
    missingFields.push("equity_summary");
  }
  if (!hasRawReport) {
    missingFields.push("raw_report");
  }

  if (hasRawReport && !reportData?.performance?.all) {
    parseWarnings.push("report.performance_all_missing");
  }
  if (hasRawReport && !Array.isArray(reportData?.trades)) {
    parseWarnings.push("report.trade_list_missing");
  }
  if (hasRawReport && !hasEquitySummary) {
    parseWarnings.push("report.equity_summary_missing");
  }

  return {
    hasNetProfit,
    hasTotalTrades,
    hasMaxDrawdown,
    hasProfitFactor,
    hasWinRate,
    hasTrades,
    hasEquitySummary,
    hasRawReport,
    missingFields,
    parseWarnings,
    parserVersion: TRADINGVIEW_REPORT_PARSER_VERSION,
  };
}

export function extractTradeRecordsFromReportData(
  reportData: RawStrategyReportData | null | undefined,
  maxTrades = 50,
): TradeRecord[] {
  const trades = (reportData?.trades ?? []).slice(0, maxTrades);
  return trades.map((trade) =>
    tradeRecordSchema.parse({
      entryComment: trade.e?.c ?? null,
      entryPrice: toNullableNumber(trade.e?.p),
      entryTime: toIsoString(trade.e?.tm),
      exitComment: trade.x?.c ?? null,
      exitPrice: toNullableNumber(trade.x?.p),
      exitTime: toIsoString(trade.x?.tm),
      qty: toNullableNumber(trade.q),
      profitValue: toNullableNumber(trade.cp?.v),
      profitPercent: ratioToNullablePercent(trade.cp?.p),
      runupPercent: ratioToNullablePercent(trade.rn?.p),
      drawdownPercent: ratioToNullablePercent(trade.dd?.p),
    }),
  );
}

export function extractTraceEventsFromReportData(
  reportData: RawStrategyReportData | null | undefined,
  maxEvents = 200,
): TraceEventV1[] {
  return extractTraceEventsFromUnknownReportData(reportData, maxEvents);
}

export function extractEquitySummaryFromReportData(
  reportData: RawStrategyReportData | null | undefined,
): EquitySummary {
  const equityValues = toFiniteNumberArray(reportData?.buyHold);
  if (equityValues.length > 0) {
    const points = equityValues.map((value, index) => ({
      time: new Date(index * 60_000).toISOString(),
      value: roundNumber(value),
    }));
    return equitySummarySchema.parse({
      available: true,
      unavailableReason: null,
      pointsAvailable: true,
      pointCount: points.length,
      finalEquity: points.at(-1)?.value ?? null,
      maxDrawdownPercent: calculateMaxDrawdownPercent(
        points.map((point) => point.value),
      ),
      points,
    });
  }

  const equityPercentValues = toFiniteNumberArray(reportData?.buyHoldPercent);
  if (equityPercentValues.length > 0) {
    const points = equityPercentValues.map((ratio, index) => ({
      time: new Date(index * 60_000).toISOString(),
      value: roundNumber(100 * (1 + ratio)),
    }));
    return equitySummarySchema.parse({
      available: true,
      unavailableReason: null,
      pointsAvailable: true,
      pointCount: points.length,
      finalEquity: points.at(-1)?.value ?? null,
      maxDrawdownPercent: calculateMaxDrawdownPercent(
        points.map((point) => point.value),
      ),
      points,
    });
  }

  return equitySummarySchema.parse({
    available: false,
    unavailableReason: "equity_table_not_found",
    pointsAvailable: false,
    pointCount: 0,
    finalEquity: null,
    maxDrawdownPercent: null,
    points: [],
  });
}

export function normalizeAttachedStudyTitle(title: string | null | undefined): string | null {
  if (!title) {
    return null;
  }

  return title.replace(/\s+\([^)]*\)$/, "").trim();
}

function ratioToPercent(value: number | null | undefined): number {
  return roundNumber(toFiniteNumber(value) * 100);
}

function ratioToNullablePercent(value: number | null | undefined): number | null {
  return value == null ? null : roundNumber(toFiniteNumber(value) * 100);
}

function toFiniteNumber(value: number | null | undefined): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return 0;
  }

  return value;
}

function toNullableNumber(value: number | null | undefined): number | null {
  if (value == null || !Number.isFinite(value)) {
    return null;
  }

  return value;
}

function toIsoString(value: number | null | undefined): string | null {
  if (value == null || !Number.isFinite(value)) {
    return null;
  }

  return new Date(value).toISOString();
}

function roundNumber(value: number): number {
  return Math.round(value * 1_000_000) / 1_000_000;
}

function isFiniteNumber(value: number | null | undefined): boolean {
  return typeof value === "number" && Number.isFinite(value);
}

function hasFiniteNumberArray(value: number[] | null | undefined): boolean {
  return Array.isArray(value) && value.some((entry) => isFiniteNumber(entry));
}

function toFiniteNumberArray(value: number[] | null | undefined): number[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value.filter((entry): entry is number => isFiniteNumber(entry));
}

function calculateMaxDrawdownPercent(values: number[]): number | null {
  if (values.length === 0) {
    return null;
  }

  let peak = values[0] ?? 0;
  let maxDrawdown = 0;
  for (const value of values) {
    if (value > peak) {
      peak = value;
      continue;
    }
    if (peak <= 0) {
      continue;
    }
    const drawdown = ((peak - value) / peak) * 100;
    if (drawdown > maxDrawdown) {
      maxDrawdown = drawdown;
    }
  }

  return roundNumber(maxDrawdown);
}
