import {
  type EnrichedTradeRecord,
  type LossAnalysisSummary,
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
    repairPriorities: [],
  };
}

export function createNoTradesLossAnalysis(): LossAnalysisSummary {
  return {
    status: "unavailable_no_trades",
    summary: "No losing trades were available for loss-zone analysis.",
    topLossZones: [],
    repairPriorities: [
      "Restore tradable entry frequency before optimizing other metrics.",
    ],
  };
}

export function summarizeLossZones(
  trades: EnrichedTradeRecord[],
): LossAnalysisSummary {
  const losers = trades.filter((trade) => (trade.profitPercent ?? 0) < 0);
  if (losers.length === 0) {
    return createNoTradesLossAnalysis();
  }

  const zoneCounts = new Map<string, number>();
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
    repairPriorities,
  };
}
