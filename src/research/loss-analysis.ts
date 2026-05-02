import {
  type EnrichedTradeRecord,
  type LossZoneDetail,
  type LossAnalysisSummary,
  type TradeLifecycleSummary,
} from "../contracts/types.js";

function sortCounts(map: Map<string, number>): string[] {
  return [...map.entries()]
    .sort((left, right) => {
      const priorityDiff = zonePriority(right[0]) - zonePriority(left[0]);
      if (priorityDiff !== 0) {
        return priorityDiff;
      }
      return right[1] - left[1] || left[0].localeCompare(right[0]);
    })
    .map(([label, count]) => `${label}:${count}`);
}

function zonePriority(label: string): number {
  if (/^range_squeeze:weak_exit$/.test(label)) {
    return 400;
  }
  if (/^range:weak_exit$/.test(label)) {
    return 350;
  }
  if (/^range_squeeze:/.test(label)) {
    return 200;
  }
  if (/^range:/.test(label)) {
    return 150;
  }
  if (/weak_exit/.test(label)) {
    return 100;
  }
  return 0;
}

export function createMarketContextUnavailableLossAnalysis(): LossAnalysisSummary {
  return {
    status: "market_context_unavailable",
    summary: "QQQ 2h market context was unavailable during this evaluation.",
    topLossZones: [],
    lossZoneDetails: [],
    tradeLifecycle: [],
    repairPriorities: [],
  };
}

export function createNoTradesLossAnalysis(): LossAnalysisSummary {
  return {
    status: "unavailable_no_trades",
    summary: "No losing trades were available for loss-zone analysis.",
    topLossZones: [],
    lossZoneDetails: [],
    tradeLifecycle: [],
    repairPriorities: [
      "Restore tradable entry frequency before optimizing other metrics.",
    ],
  };
}

export function summarizeLossZones(
  trades: EnrichedTradeRecord[],
): LossAnalysisSummary {
  const tradeLifecycle = summarizeTradeLifecycle(trades);
  const losers = trades.filter((trade) => (trade.profitPercent ?? 0) < 0);
  if (losers.length === 0) {
    return {
      ...createNoTradesLossAnalysis(),
      tradeLifecycle,
    };
  }

  const zoneCounts = new Map<string, number>();
  const zoneDetailGroups = new Map<string, { detail: LossZoneDetail; losses: number[] }>();
  const repairCounts = {
    counterTrend: 0,
    overextended: 0,
    lateEntry: 0,
    weakExit: 0,
    rangeWeakExit: 0,
  };

  for (const trade of losers) {
    const regime = trade.entryContext?.regime ?? "unknown";
    zoneCounts.set(regime, (zoneCounts.get(regime) ?? 0) + 1);
    addLossZoneDetail(zoneDetailGroups, trade);

    if (trade.flags.counterTrendEntry) {
      const label = `${regime}:counter_trend_entry`;
      zoneCounts.set(label, (zoneCounts.get(label) ?? 0) + 1);
      repairCounts.counterTrend += 1;
    }
    if (trade.flags.overextendedEntry) {
      const label = `${regime}:overextended_entry`;
      zoneCounts.set(label, (zoneCounts.get(label) ?? 0) + 1);
      repairCounts.overextended += 1;
    }
    if (trade.flags.lateEntry) {
      const label = `${regime}:late_entry`;
      zoneCounts.set(label, (zoneCounts.get(label) ?? 0) + 1);
      repairCounts.lateEntry += 1;
    }
    if (trade.flags.weakExit) {
      const label = `${trade.exitContext?.regime ?? regime}:weak_exit`;
      zoneCounts.set(label, (zoneCounts.get(label) ?? 0) + 1);
      repairCounts.weakExit += 1;
      if ((trade.exitContext?.regime ?? regime) === "range" || (trade.exitContext?.regime ?? regime) === "range_squeeze") {
        repairCounts.rangeWeakExit += 1;
      }
    }
  }

  const topLossZones = sortCounts(zoneCounts).slice(0, 5);
  const lossZoneDetails = [...zoneDetailGroups.values()]
    .map(({ detail, losses }) => ({
      ...detail,
      lossCount: losses.length,
      averageLossPercent: average(losses),
    }))
    .sort(
      (left, right) =>
        right.lossCount - left.lossCount ||
        Math.abs(right.averageLossPercent ?? 0) - Math.abs(left.averageLossPercent ?? 0),
    )
    .slice(0, 8);
  const repairPriorities: string[] = [];
  if (repairCounts.rangeWeakExit > 0) {
    repairPriorities.push(
      "Prioritize faster loser exits in range and range_squeeze regimes before tuning new entries.",
    );
  }
  if (repairCounts.weakExit > 0) {
    repairPriorities.push(
      "Tighten exit behavior when losing trades continue into deeper drawdown.",
    );
  }
  if (repairCounts.counterTrend > 0) {
    repairPriorities.push(
      "Reduce counter-trend long entries during trend_down regimes.",
    );
  }
  if (repairCounts.overextended > 0) {
    repairPriorities.push(
      "Reduce overextended entries when price is materially above EMA20.",
    );
  }
  if (repairCounts.lateEntry > 0) {
    repairPriorities.push(
      "Avoid late entries after short-window upside extension.",
    );
  }

  const topRegime = topLossZones[0]?.split(":")[0] ?? "unknown";
  return {
    status: "available",
    summary: `Analyzed ${losers.length} losing trades. Largest loss cluster appeared in ${topRegime}.`,
    topLossZones,
    lossZoneDetails,
    tradeLifecycle,
    repairPriorities,
  };
}

function addLossZoneDetail(
  groups: Map<string, { detail: LossZoneDetail; losses: number[] }>,
  trade: EnrichedTradeRecord,
): void {
  const regime = trade.entryContext?.regime ?? "unknown";
  const detail: LossZoneDetail = {
    regime,
    volatilityBucket: classifyVolatility(trade.entryContext?.atrPercent ?? null),
    trendBucket: classifyTrendBucket(regime),
    entryRoute: normalizeRoute(trade.entryComment),
    exitReason: normalizeExitReason(trade.exitComment, trade.flags.weakExit),
    slotRank: extractSlotRank(trade.entryComment),
    barsHeld: estimateBarsHeld(trade.entryTime, trade.exitTime),
    lossCount: 0,
    averageLossPercent: null,
  };
  const key = [
    detail.regime,
    detail.volatilityBucket,
    detail.trendBucket,
    detail.entryRoute,
    detail.exitReason,
    detail.slotRank ?? "slot_unknown",
  ].join("|");
  const current = groups.get(key) ?? { detail, losses: [] };
  current.losses.push(trade.profitPercent ?? 0);
  groups.set(key, current);
}

function summarizeTradeLifecycle(
  trades: EnrichedTradeRecord[],
): TradeLifecycleSummary[] {
  const groups = new Map<string, EnrichedTradeRecord[]>();
  for (const trade of trades) {
    const route = normalizeRoute(trade.entryComment);
    groups.set(route, [...(groups.get(route) ?? []), trade]);
  }

  return [...groups.entries()]
    .map(([entryRoute, groupedTrades]) => {
      const barsHeld = groupedTrades
        .map((trade) => estimateBarsHeld(trade.entryTime, trade.exitTime))
        .filter((value): value is number => typeof value === "number");
      const runups = groupedTrades
        .map((trade) => trade.runupPercent)
        .filter((value): value is number => typeof value === "number");
      const drawdowns = groupedTrades
        .map((trade) => trade.drawdownPercent)
        .filter((value): value is number => typeof value === "number");
      const profits = groupedTrades
        .map((trade) => trade.profitPercent)
        .filter((value): value is number => typeof value === "number");
      const exitReasonDistribution: Record<string, number> = {};
      for (const trade of groupedTrades) {
        const reason = normalizeExitReason(trade.exitComment, trade.flags.weakExit);
        exitReasonDistribution[reason] = (exitReasonDistribution[reason] ?? 0) + 1;
      }
      return {
        entryRoute,
        tradeCount: groupedTrades.length,
        averageBarsHeld: average(barsHeld),
        mfeProxy: average(runups),
        maeProxy: average(drawdowns),
        exitReasonDistribution,
        profitDistribution: {
          winners: profits.filter((value) => value > 0).length,
          losers: profits.filter((value) => value < 0).length,
          breakeven: profits.filter((value) => value === 0).length,
          averageProfitPercent: average(profits),
          medianProfitPercent: median(profits),
        },
      } satisfies TradeLifecycleSummary;
    })
    .sort((left, right) => right.tradeCount - left.tradeCount)
    .slice(0, 8);
}

function classifyVolatility(atrPercent: number | null): string {
  if (atrPercent == null || !Number.isFinite(atrPercent)) {
    return "unknown";
  }
  if (atrPercent >= 3) {
    return "extreme";
  }
  if (atrPercent >= 2) {
    return "high";
  }
  if (atrPercent >= 1) {
    return "normal";
  }
  return "low";
}

function classifyTrendBucket(regime: string): string {
  if (
    regime === "trend_up" ||
    regime === "trend_down" ||
    regime === "range" ||
    regime === "range_squeeze" ||
    regime === "volatile"
  ) {
    return regime;
  }
  return "unknown";
}

function normalizeRoute(comment: string | null): string {
  const value = normalizeComment(comment);
  if (value.includes("bear")) {
    return "bear_rebound";
  }
  if (value.includes("bull")) {
    return "bull_event";
  }
  if (value.includes("reclaim")) {
    return "reclaim";
  }
  if (value.includes("compression")) {
    return "compression_release";
  }
  if (value.includes("time")) {
    return "time_boxed";
  }
  return value === "unknown" ? "unknown_route" : value;
}

function normalizeExitReason(comment: string | null, weakExit: boolean): string {
  const value = normalizeComment(comment);
  if (weakExit) {
    return "weak_exit";
  }
  if (value.includes("time") || value.includes("hold")) {
    return "time_exit";
  }
  if (value.includes("bear")) {
    return "bear_event_exit";
  }
  if (value.includes("risk")) {
    return "risk_off_exit";
  }
  return value === "unknown" ? "unknown_exit" : value;
}

function normalizeComment(comment: string | null): string {
  const normalized = (comment ?? "unknown")
    .toLowerCase()
    .replace(/aftrace\|v1\|[^ ]+/g, "")
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return normalized.length === 0 ? "unknown" : normalized.slice(0, 48);
}

function extractSlotRank(comment: string | null): number | null {
  const match = (comment ?? "").match(/\b(?:slot|rank)[_\s:-]*(\d+)\b/i);
  if (!match) {
    return null;
  }
  const value = Number(match[1]);
  return Number.isInteger(value) ? value : null;
}

function estimateBarsHeld(
  entryTime: string | null,
  exitTime: string | null,
): number | null {
  if (!entryTime || !exitTime) {
    return null;
  }
  const entryMs = Date.parse(entryTime);
  const exitMs = Date.parse(exitTime);
  if (!Number.isFinite(entryMs) || !Number.isFinite(exitMs) || exitMs < entryMs) {
    return null;
  }
  return Math.round(((exitMs - entryMs) / 7_200_000) * 100) / 100;
}

function average(values: number[]): number | null {
  if (values.length === 0) {
    return null;
  }
  return round(values.reduce((sum, value) => sum + value, 0) / values.length);
}

function median(values: number[]): number | null {
  if (values.length === 0) {
    return null;
  }
  const sorted = [...values].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 1) {
    return sorted[middle] ?? null;
  }
  return round(((sorted[middle - 1] ?? 0) + (sorted[middle] ?? 0)) / 2);
}

function round(value: number): number {
  return Math.round(value * 1_000_000) / 1_000_000;
}
