import {
  artifactBundleSchema,
  backtestMetricsSchema,
  equitySummarySchema,
  tradeRecordSchema,
  type ArtifactBundle,
  type BacktestMetrics,
  type MarketContextBar,
  type TradeRecord,
} from "../../contracts/types.js";
import { type AfStrategyConfig } from "./af-config.js";

interface IndicatorSeries {
  ema: Array<number | null>;
  baseEma: Array<number | null>;
  rsi: Array<number | null>;
  atr: Array<number | null>;
  supertrendLine: Array<number | null>;
  supertrendDirection: Array<number | null>;
}

interface SlotPosition {
  id: string;
  entryPrice: number;
  qty: number;
  rank: number;
  entryBarIndex: number;
  entryTime: string;
  peakHigh: number;
  troughLow: number;
  entryCommission: number;
}

interface EquityPoint {
  time: string;
  value: number;
}

export interface LocalBacktestResult {
  artifactBundle: ArtifactBundle;
  metrics: BacktestMetrics;
}

export function simulateAfStrategy(
  bars: MarketContextBar[],
  config: AfStrategyConfig,
): LocalBacktestResult {
  const indicators = computeIndicators(bars, config);
  const trades: TradeRecord[] = [];
  const equityPoints: EquityPoint[] = [];
  const slots: SlotPosition[] = [];

  let cash = config.initialCapital;
  let bull = 0;
  let bear = 0;
  let cycle = 0;
  let bullSignalBar: number | null = null;
  let bearSignalBar: number | null = null;
  let nextSlotNo = 1;
  let lastLongEntryBar: number | null = null;
  let lastOrderBar: number | null = null;

  let previousBullL1 = false;
  let previousBullCandidate = false;
  let previousBullStrong = false;
  let previousBullConfirmed = false;
  let previousBearL1 = false;
  let previousBearCandidate = false;
  let previousBearStrong = false;
  let previousBearConfirmed = false;
  let previousBullEventFloor = false;
  let previousBearEventFloor = false;
  let lastBullFloorEventBar: number | null = null;
  let lastBearFloorEventBar: number | null = null;

  for (let index = 0; index < bars.length; index += 1) {
    const bar = bars[index];
    const previousBar = index > 0 ? bars[index - 1] : null;
    const close = bar.close;
    const high = bar.high;
    const low = bar.low;
    const open = bar.open;
    const ema = indicators.ema[index];
    const baseEma = indicators.baseEma[index];
    const rsi = indicators.rsi[index];
    const atr = indicators.atr[index];
    const supertrendLine = indicators.supertrendLine[index];
    const supertrendDirection = indicators.supertrendDirection[index];

    updateSlotExtremes(slots, high, low);

    const has4 = index >= 4;
    const has2 = index >= 2;

    if (!has4) {
      bull = 0;
      bear = 0;
      cycle = 0;
    } else if (cycle < config.L1) {
      if (close < bars[index - 4].close) {
        bull += 1;
        bear = 0;
        cycle = bull;
      } else if (close > bars[index - 4].close) {
        bear += 1;
        bull = 0;
        cycle = bear;
      } else {
        [bull, bear, cycle] = resetCycleState(bars, index);
      }
    } else if (bull > 0) {
      if (has2 && close < bars[index - 2].close) {
        bull += 1;
        cycle = bull;
      } else {
        [bull, bear, cycle] = resetCycleState(bars, index);
      }
    } else if (bear > 0) {
      if (has2 && close > bars[index - 2].close) {
        bear += 1;
        cycle = bear;
      } else {
        [bull, bear, cycle] = resetCycleState(bars, index);
      }
    } else {
      [bull, bear, cycle] = resetCycleState(bars, index);
    }

    const bullL1 = bull === config.L1;
    const bullCandidate = bull === config.L2;
    const bullStrong = bull === config.L3;
    const bearL1 = bear === config.L1;
    const bearCandidate = bear === config.L2;
    const bearStrong = bear === config.L3;

    if (bullCandidate || bullStrong) {
      bullSignalBar = index;
    }
    if (bearCandidate || bearStrong) {
      bearSignalBar = index;
    }

    const bullConfirmed =
      bullSignalBar !== null &&
      index > bullSignalBar &&
      index - bullSignalBar <= config.confirmBars &&
      previousBar !== null &&
      close > previousBar.high;
    const bearConfirmed =
      bearSignalBar !== null &&
      index > bearSignalBar &&
      index - bearSignalBar <= config.confirmBars &&
      previousBar !== null &&
      close < previousBar.low;

    if (
      bullConfirmed ||
      (bullSignalBar !== null && index - bullSignalBar > config.confirmBars)
    ) {
      bullSignalBar = null;
    }
    if (
      bearConfirmed ||
      (bearSignalBar !== null && index - bearSignalBar > config.confirmBars)
    ) {
      bearSignalBar = null;
    }

    const newBullL1 = bullL1 && !previousBullL1;
    const newBullCandidate = bullCandidate && !previousBullCandidate;
    const newBullStrong = bullStrong && !previousBullStrong;
    const newBullConfirmed = bullConfirmed && !previousBullConfirmed;
    const newBearL1 = bearL1 && !previousBearL1;
    const newBearCandidate = bearCandidate && !previousBearCandidate;
    const newBearStrong = bearStrong && !previousBearStrong;
    const newBearConfirmed = bearConfirmed && !previousBearConfirmed;

    previousBullL1 = bullL1;
    previousBullCandidate = bullCandidate;
    previousBullStrong = bullStrong;
    previousBullConfirmed = bullConfirmed;
    previousBearL1 = bearL1;
    previousBearCandidate = bearCandidate;
    previousBearStrong = bearStrong;
    previousBearConfirmed = bearConfirmed;

    const timeBoxedRouteEnabled =
      config.eventFloorBars != null ||
      config.eventWindowBars != null ||
      config.maxHoldBars != null;
    const eventFloorBars = Math.max(1, config.eventFloorBars ?? config.L1);
    const bullEventFloor = timeBoxedRouteEnabled && bull >= eventFloorBars;
    const bearEventFloor = timeBoxedRouteEnabled && bear >= eventFloorBars;
    const earlyBullEvent = bullEventFloor && !previousBullEventFloor;
    const earlyBearEvent = bearEventFloor && !previousBearEventFloor;
    previousBullEventFloor = bullEventFloor;
    previousBearEventFloor = bearEventFloor;
    if (earlyBullEvent) {
      lastBullFloorEventBar = index;
    }
    if (earlyBearEvent) {
      lastBearFloorEventBar = index;
    }

    const bullEventRaw = newBullConfirmed ? 4 : newBullStrong ? 3 : newBullCandidate ? 2 : newBullL1 ? 1 : 0;
    const bearEventRaw = newBearConfirmed ? 4 : newBearStrong ? 3 : newBearCandidate ? 2 : newBearL1 ? 1 : 0;

    const bullMomentum =
      ((indicators.rsi[index - 1] != null && rsi != null && rsi > (indicators.rsi[index - 1] as number)) ||
        (previousBar !== null && close > previousBar.close));
    const bearMomentum =
      ((indicators.rsi[index - 1] != null && rsi != null && rsi < (indicators.rsi[index - 1] as number)) ||
        (previousBar !== null && close < previousBar.close));
    const bullTrend = ema != null && close >= ema;
    const supertrendBull = supertrendDirection != null && supertrendDirection < 0;
    const supertrendBear = supertrendDirection != null && supertrendDirection > 0;
    const emaUp =
      index > 0 &&
      indicators.ema[index - 1] != null &&
      ema != null &&
      ema >= (indicators.ema[index - 1] as number);
    const emaDown =
      index > 0 &&
      indicators.ema[index - 1] != null &&
      ema != null &&
      ema <= (indicators.ema[index - 1] as number);

    const [finalBullEvent, finalBearEvent] = resolveConflict({
      bullEvent: bullEventRaw,
      bearEvent: bearEventRaw,
      mode: config.sameBarConflictMode,
      bullMomentum,
      bearMomentum,
      ema,
      close,
      rsi,
    });

    const baseRiskOff =
      baseEma != null &&
      rsi != null &&
      close < baseEma &&
      rsi < config.riskOffRsi &&
      emaDown;
    const supertrendRiskOff =
      config.supertrendRiskOffEnabled &&
      supertrendBear &&
      supertrendLine != null &&
      close < supertrendLine;
    const riskOff = baseRiskOff || supertrendRiskOff;
    const overextended = ema != null && close > ema * (1 + config.maxExtPct / 100);
    const emaSpreadAtr =
      atr != null && atr > 0 && ema != null && baseEma != null
        ? Math.abs(ema - baseEma) / atr
        : 0;
    const rangeLikeRegime =
      baseEma != null &&
      close <= baseEma &&
      emaSpreadAtr <= config.weakSlopeAtrMax &&
      (!emaUp || (rsi ?? 0) < 55);

    let bullRecoveryOk = false;
    if (config.trendMode === "Strict") {
      bullRecoveryOk = bullTrend && bullMomentum;
    } else if (config.trendMode === "Balanced") {
      bullRecoveryOk = bullMomentum && (bullTrend || emaUp || close > open);
    } else {
      bullRecoveryOk = bullMomentum || close > open;
    }

    const bullRiskAllowed =
      !riskOff || (config.allowStrongCounterTrend && finalBullEvent >= 3 && bullMomentum);
    const supertrendWeakPass = !config.useSupertrendFilter || supertrendBull;
    const supertrendStrongPass =
      !config.useSupertrendFilter ||
      supertrendBull ||
      !config.supertrendBlocksWeakBull;
    const bullBaseAllowed = bullRiskAllowed && !overextended;
    const baseEmaRecoveryPass =
      baseEma != null && rsi != null && close > baseEma && rsi >= 45;
    const baseEmaRecoveryPassRelaxed =
      baseEma != null && rsi != null && ema != null && close > baseEma && rsi >= 42 && ema >= baseEma;
    const nearBaseEmaRecoveryPass =
      atr != null &&
      atr > 0 &&
      baseEma != null &&
      rsi != null &&
      ema != null &&
      close >= baseEma - atr * 0.4 &&
      rsi >= 47 &&
      ema >= baseEma;

    let bullB1Allowed = true;
    if (config.applyFilterToB1) {
      bullB1Allowed = bullBaseAllowed && supertrendWeakPass && (bullRecoveryOk || bullTrend);
    } else {
      bullB1Allowed = supertrendWeakPass;
    }

    let bullFilterPass = false;
    if (finalBullEvent === 1) {
      bullFilterPass = bullB1Allowed;
    } else if (finalBullEvent === 2) {
      bullFilterPass =
        bullBaseAllowed &&
        supertrendWeakPass &&
        (bullRecoveryOk ||
          baseEmaRecoveryPass ||
          (config.trendMode === "Balanced" &&
            (baseEmaRecoveryPassRelaxed || nearBaseEmaRecoveryPass)));
    } else if (finalBullEvent === 3) {
      bullFilterPass =
        bullBaseAllowed &&
        supertrendStrongPass &&
        (bullRecoveryOk ||
          close > open ||
          baseEmaRecoveryPass ||
          (config.trendMode === "Balanced" &&
            (baseEmaRecoveryPassRelaxed || nearBaseEmaRecoveryPass)));
    } else if (finalBullEvent === 4) {
      bullFilterPass =
        bullBaseAllowed &&
        supertrendStrongPass &&
        (bullRecoveryOk ||
          (ema != null && close > ema) ||
          baseEmaRecoveryPass ||
          (config.trendMode === "Balanced" &&
            (baseEmaRecoveryPassRelaxed || nearBaseEmaRecoveryPass)));
    }

    const effectiveBearEvent = timeBoxedRouteEnabled && earlyBearEvent ? 1 : finalBearEvent;
    const allowBear = effectiveBearEvent > 0;
    const eventWindowBars = Math.max(1, config.eventWindowBars ?? 14);
    const bullContinueWindow = Math.max(
      1,
      config.bullContinueWindow ?? eventWindowBars,
    );
    const bearReboundWindow = Math.max(
      1,
      config.bearReboundWindow ?? eventWindowBars,
    );
    const bullEventAge =
      lastBullFloorEventBar == null ? null : index - lastBullFloorEventBar;
    const bearEventAge =
      lastBearFloorEventBar == null ? null : index - lastBearFloorEventBar;
    const bullAgeActive =
      timeBoxedRouteEnabled &&
      bullEventAge != null &&
      bullEventAge <= bullContinueWindow;
    const bearAgeActive =
      timeBoxedRouteEnabled &&
      bearEventAge != null &&
      bearEventAge <= bearReboundWindow;
    const timeBoxedEntryPass = (bullAgeActive || bearAgeActive) && !riskOff;
    const timeBoxedEntryRank = bullAgeActive && bearAgeActive ? 4 : bullAgeActive ? 3 : 2;
    const effectiveEntryPass = timeBoxedRouteEnabled
      ? timeBoxedEntryPass
      : finalBullEvent > 0 && bullFilterPass;
    const effectiveEntryRank = timeBoxedRouteEnabled ? timeBoxedEntryRank : finalBullEvent;
    const equityBeforeOrders = currentEquity(cash, slots, close);
    const qtyNow = Math.max(
      close > 0 ? (equityBeforeOrders * (config.slotPct / 100)) / close : 0,
      config.minQty,
    );
    const qtyOk = Number.isFinite(qtyNow) && qtyNow > 0;
    const canEnterLong =
      lastLongEntryBar === null ||
      index - lastLongEntryBar >= config.entryCooldownBars + 1;
    const slotAvailable = slots.length < config.maxSlots;

    if (effectiveEntryPass && canEnterLong && qtyOk) {
      if (slotAvailable) {
        enterSlot(slots, trades, {
          close,
          high,
          low,
          qty: qtyNow,
          rank: effectiveEntryRank,
          barIndex: index,
          time: bar.time,
          nextSlotNo,
          commissionPercent: config.commissionPercent,
        }, (slot, totalCost) => {
          cash -= totalCost;
          nextSlotNo += 1;
          lastLongEntryBar = index;
          lastOrderBar = index;
          slots.push(slot);
        });
      } else if (config.useReplacement && effectiveEntryRank >= config.replaceMinRank) {
        const weakestIndex = findWeakestSlotIndex(slots, close);
        if (weakestIndex !== null) {
          const weakest = slots[weakestIndex];
          const weakPnl = percentPnl(weakest.entryPrice, close);
          const canReplace =
            weakPnl <= config.replaceIfPnlBelow || effectiveEntryRank > weakest.rank;
          if (canReplace) {
            closeSlot(slots, weakestIndex, close, bar.time, config.commissionPercent, trades, (netProceeds) => {
              cash += netProceeds;
            });
            lastOrderBar = index;
            enterSlot(slots, trades, {
                close,
                high,
                low,
                qty: qtyNow,
                rank: effectiveEntryRank,
                barIndex: index,
                time: bar.time,
                nextSlotNo,
              commissionPercent: config.commissionPercent,
            }, (slot, totalCost) => {
              cash -= totalCost;
              nextSlotNo += 1;
              lastLongEntryBar = index;
              lastOrderBar = index;
              slots.push(slot);
            });
          }
        }
      }
    }

    if (timeBoxedRouteEnabled && config.maxHoldBars != null && slots.length > 0) {
      const maxHoldBars = Math.max(1, config.maxHoldBars);
      for (let slotIndex = slots.length - 1; slotIndex >= 0; slotIndex -= 1) {
        const slot = slots[slotIndex];
        if (index - slot.entryBarIndex >= maxHoldBars) {
          closeSlot(slots, slotIndex, close, bar.time, config.commissionPercent, trades, (netProceeds) => {
            cash += netProceeds;
          });
          lastOrderBar = index;
        }
      }
    }

    if (config.enableWeakRangeExit && slots.length > 0 && rangeLikeRegime && atr != null && atr > 0) {
      for (let slotIndex = slots.length - 1; slotIndex >= 0; slotIndex -= 1) {
        const slot = slots[slotIndex];
        const barsHeld = index - slot.entryBarIndex;
        const runupAtr = (slot.peakHigh - slot.entryPrice) / atr;
        const lossAtr = (slot.entryPrice - close) / atr;
        const nonProgressing = barsHeld >= config.weakExitBars && runupAtr < config.weakRunupAtrMax;
        const loserTooDeep = lossAtr >= config.weakLossAtrMin;
        if (nonProgressing && loserTooDeep && ema != null && close < ema) {
          closeSlot(slots, slotIndex, close, bar.time, config.commissionPercent, trades, (netProceeds) => {
            cash += netProceeds;
          });
          lastOrderBar = index;
        }
      }
    }

    if (allowBear && slots.length > 0) {
      if (effectiveBearEvent === 1 || effectiveBearEvent === 2) {
        const weakestIndex = findWeakestSlotIndex(slots, close);
        if (weakestIndex !== null) {
          closeSlot(slots, weakestIndex, close, bar.time, config.commissionPercent, trades, (netProceeds) => {
            cash += netProceeds;
          });
          lastOrderBar = index;
        }
      }

      if (effectiveBearEvent === 3) {
        for (let step = 0; step < 2; step += 1) {
          const weakestIndex = findWeakestSlotIndex(slots, close);
          if (weakestIndex === null) {
            break;
          }
          closeSlot(slots, weakestIndex, close, bar.time, config.commissionPercent, trades, (netProceeds) => {
            cash += netProceeds;
          });
          lastOrderBar = index;
        }
      }

      if (effectiveBearEvent === 4) {
        while (slots.length > 0) {
          const weakestIndex = findWeakestSlotIndex(slots, close);
          if (weakestIndex === null) {
            break;
          }
          const weakest = slots[weakestIndex];
          if (percentPnl(weakest.entryPrice, close) >= 0) {
            break;
          }
          closeSlot(slots, weakestIndex, close, bar.time, config.commissionPercent, trades, (netProceeds) => {
            cash += netProceeds;
          });
          lastOrderBar = index;
        }

        if (config.closeAllOnBearConfRiskOff && riskOff) {
          while (slots.length > 0) {
            closeSlot(slots, 0, close, bar.time, config.commissionPercent, trades, (netProceeds) => {
              cash += netProceeds;
            });
            lastOrderBar = index;
          }
        }
      }
    }

    if (config.resetOnL3 && (bull === config.L3 || bear === config.L3)) {
      bull = 0;
      bear = 0;
      cycle = 0;
    }

    if (slots.length === 0 && lastOrderBar !== null && index > lastOrderBar) {
      lastOrderBar = null;
    }

    equityPoints.push({
      time: bar.time,
      value: roundNumber(currentEquity(cash, slots, close)),
    });
  }

  if (bars.length > 0 && slots.length > 0) {
    const lastBar = bars[bars.length - 1];
    while (slots.length > 0) {
      closeSlot(slots, 0, lastBar.close, lastBar.time, config.commissionPercent, trades, (netProceeds) => {
        cash += netProceeds;
      });
    }
    equityPoints.push({
      time: lastBar.time,
      value: roundNumber(cash),
    });
  }

  const metrics = backtestMetricsSchema.parse(buildMetrics(config.initialCapital, cash, trades, equityPoints));
  const artifactBundle = artifactBundleSchema.parse({
    strategy: metrics,
    trades: trades.map((trade) => tradeRecordSchema.parse(trade)),
    equity: equitySummarySchema.parse({
      available: true,
      pointsAvailable: true,
      pointCount: equityPoints.length,
      finalEquity: equityPoints.at(-1)?.value ?? cash,
      maxDrawdownPercent: metrics.maxStrategyDrawdownPercent,
      points: equityPoints,
    }),
    state: {
      engine: "local-backtest",
      initialCapital: config.initialCapital,
      commissionPercent: config.commissionPercent,
      slotCountClosed: trades.length,
    },
  });

  return {
    artifactBundle,
    metrics,
  };
}

function updateSlotExtremes(slots: SlotPosition[], high: number, low: number): void {
  for (const slot of slots) {
    slot.peakHigh = Math.max(slot.peakHigh, high);
    slot.troughLow = Math.min(slot.troughLow, low);
  }
}

function resetCycleState(
  bars: MarketContextBar[],
  index: number,
): [number, number, number] {
  if (index < 4) {
    return [0, 0, 0];
  }
  const close = bars[index].close;
  const compare = bars[index - 4].close;
  if (close < compare) {
    return [1, 0, 1];
  }
  if (close > compare) {
    return [0, 1, 1];
  }
  return [0, 0, 0];
}

function resolveConflict(input: {
  bullEvent: number;
  bearEvent: number;
  mode: AfStrategyConfig["sameBarConflictMode"];
  bullMomentum: boolean;
  bearMomentum: boolean;
  ema: number | null;
  close: number;
  rsi: number | null;
}): [number, number] {
  if (input.bullEvent === 0 || input.bearEvent === 0) {
    return [input.bullEvent, input.bearEvent];
  }

  if (input.mode === "BearPriority") {
    return [0, input.bearEvent];
  }
  if (input.mode === "SkipBoth") {
    return [0, 0];
  }
  if (input.bullEvent > input.bearEvent) {
    return [input.bullEvent, 0];
  }
  if (input.bearEvent > input.bullEvent) {
    return [0, input.bearEvent];
  }
  if (input.bullMomentum && !input.bearMomentum) {
    return [input.bullEvent, 0];
  }
  if (input.bearMomentum && !input.bullMomentum) {
    return [0, input.bearEvent];
  }
  if (input.ema != null && input.close > input.ema && (input.rsi ?? 0) >= 50) {
    return [input.bullEvent, 0];
  }
  if (input.ema != null && input.close < input.ema && (input.rsi ?? 100) <= 50) {
    return [0, input.bearEvent];
  }
  return [0, 0];
}

function enterSlot(
  slots: SlotPosition[],
  trades: TradeRecord[],
  input: {
    close: number;
    high: number;
    low: number;
    qty: number;
    rank: number;
    barIndex: number;
    time: string;
    nextSlotNo: number;
    commissionPercent: number;
  },
  commit: (slot: SlotPosition, totalCost: number) => void,
): void {
  void slots;
  void trades;
  const id = `L_${input.nextSlotNo}`;
  const entryValue = input.close * input.qty;
  const entryCommission = entryValue * (input.commissionPercent / 100);
  commit(
    {
      id,
      entryPrice: input.close,
      qty: input.qty,
      rank: input.rank,
      entryBarIndex: input.barIndex,
      entryTime: input.time,
      peakHigh: input.high,
      troughLow: input.low,
      entryCommission,
    },
    entryValue + entryCommission,
  );
}

function closeSlot(
  slots: SlotPosition[],
  slotIndex: number,
  closePrice: number,
  time: string,
  commissionPercent: number,
  trades: TradeRecord[],
  commit: (netProceeds: number) => void,
): void {
  const [slot] = slots.splice(slotIndex, 1);
  const grossValue = closePrice * slot.qty;
  const exitCommission = grossValue * (commissionPercent / 100);
  const netProceeds = grossValue - exitCommission;
  const profitValue = netProceeds - slot.entryPrice * slot.qty - slot.entryCommission;
  const costBasis = slot.entryPrice * slot.qty + slot.entryCommission;

  commit(netProceeds);
  trades.push(
    tradeRecordSchema.parse({
      entryComment: slot.id,
      entryPrice: roundNumber(slot.entryPrice),
      entryTime: slot.entryTime,
      exitComment: `Close entry(s) order ${slot.id}`,
      exitPrice: roundNumber(closePrice),
      exitTime: time,
      qty: roundNumber(slot.qty),
      profitValue: roundNumber(profitValue),
      profitPercent: roundNumber(costBasis > 0 ? (profitValue / costBasis) * 100 : 0),
      runupPercent: roundNumber(((slot.peakHigh - slot.entryPrice) / slot.entryPrice) * 100),
      drawdownPercent: roundNumber(((slot.entryPrice - slot.troughLow) / slot.entryPrice) * 100),
    }),
  );
}

function findWeakestSlotIndex(slots: SlotPosition[], close: number): number | null {
  let weakestIndex: number | null = null;
  let worstPnl = Number.POSITIVE_INFINITY;
  let worstRank = Number.POSITIVE_INFINITY;

  for (let index = 0; index < slots.length; index += 1) {
    const slot = slots[index];
    const pnl = percentPnl(slot.entryPrice, close);
    if (
      weakestIndex === null ||
      pnl < worstPnl ||
      (Math.abs(pnl - worstPnl) < 0.0001 && slot.rank < worstRank)
    ) {
      weakestIndex = index;
      worstPnl = pnl;
      worstRank = slot.rank;
    }
  }

  return weakestIndex;
}

function percentPnl(entryPrice: number, closePrice: number): number {
  return entryPrice > 0 ? ((closePrice - entryPrice) / entryPrice) * 100 : 0;
}

function currentEquity(cash: number, slots: SlotPosition[], close: number): number {
  return cash + slots.reduce((sum, slot) => sum + slot.qty * close, 0);
}

function buildMetrics(
  initialCapital: number,
  endingEquity: number,
  trades: TradeRecord[],
  equityPoints: EquityPoint[],
): BacktestMetrics {
  const profitableTrades = trades.filter((trade) => (trade.profitValue ?? 0) > 0);
  const losingTrades = trades.filter((trade) => (trade.profitValue ?? 0) < 0);
  const grossProfit = profitableTrades.reduce((sum, trade) => sum + (trade.profitValue ?? 0), 0);
  const grossLoss = losingTrades.reduce(
    (sum, trade) => sum + Math.abs(trade.profitValue ?? 0),
    0,
  );
  const avgTradePercent =
    trades.length === 0
      ? 0
      : trades.reduce((sum, trade) => sum + (trade.profitPercent ?? 0), 0) / trades.length;
  const maxDrawdownPercent = computeMaxDrawdownPercent(equityPoints);

  return {
    netProfitPercent: roundNumber(((endingEquity - initialCapital) / initialCapital) * 100),
    postFeeNetProfitPercent: roundNumber(((endingEquity - initialCapital) / initialCapital) * 100),
    profitFactor: roundNumber(grossLoss === 0 ? grossProfit : grossProfit / grossLoss),
    maxStrategyDrawdownPercent: roundNumber(maxDrawdownPercent),
    percentProfitable: roundNumber(
      trades.length === 0 ? 0 : (profitableTrades.length / trades.length) * 100,
    ),
    totalTrades: trades.length,
    avgTradePercent: roundNumber(avgTradePercent),
  };
}

function computeMaxDrawdownPercent(points: EquityPoint[]): number {
  let peak = Number.NEGATIVE_INFINITY;
  let maxDrawdown = 0;

  for (const point of points) {
    peak = Math.max(peak, point.value);
    if (peak <= 0) {
      continue;
    }
    maxDrawdown = Math.max(maxDrawdown, ((peak - point.value) / peak) * 100);
  }

  return maxDrawdown;
}

function computeIndicators(
  bars: MarketContextBar[],
  config: AfStrategyConfig,
): IndicatorSeries {
  const closes = bars.map((bar) => bar.close);
  return {
    ema: computeEma(closes, config.emaLen),
    baseEma: computeEma(closes, config.baseEmaLen),
    rsi: computeRsi(closes, config.rsiLen),
    atr: computeAtr(bars, config.weakExitAtrLen),
    ...computeSupertrend(bars, config.supertrendAtrPeriod, config.supertrendFactor),
  };
}

function computeEma(values: number[], period: number): Array<number | null> {
  const result: Array<number | null> = [];
  const multiplier = 2 / (period + 1);
  let ema: number | null = null;

  for (let index = 0; index < values.length; index += 1) {
    if (index < period - 1) {
      result.push(null);
      continue;
    }
    if (ema === null) {
      ema = average(values.slice(index - period + 1, index + 1));
    } else {
      ema = (values[index] - ema) * multiplier + ema;
    }
    result.push(ema);
  }

  return result;
}

function computeAtr(bars: MarketContextBar[], period: number): Array<number | null> {
  const trueRanges = bars.map((bar, index) => {
    const previousClose = index > 0 ? bars[index - 1].close : bar.close;
    return Math.max(
      bar.high - bar.low,
      Math.abs(bar.high - previousClose),
      Math.abs(bar.low - previousClose),
    );
  });

  const result: Array<number | null> = [];
  let atr: number | null = null;
  for (let index = 0; index < trueRanges.length; index += 1) {
    if (index < period - 1) {
      result.push(null);
      continue;
    }
    if (atr === null) {
      atr = average(trueRanges.slice(index - period + 1, index + 1));
    } else {
      atr = (atr * (period - 1) + trueRanges[index]) / period;
    }
    result.push(atr);
  }

  return result;
}

function computeRsi(values: number[], period: number): Array<number | null> {
  const result: Array<number | null> = [null];
  let avgGain: number | null = null;
  let avgLoss: number | null = null;

  for (let index = 1; index < values.length; index += 1) {
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

function computeSupertrend(
  bars: MarketContextBar[],
  period: number,
  factor: number,
): {
  supertrendLine: Array<number | null>;
  supertrendDirection: Array<number | null>;
} {
  const atr = computeAtr(bars, period);
  const line: Array<number | null> = [];
  const direction: Array<number | null> = [];
  const upperBand: Array<number | null> = [];
  const lowerBand: Array<number | null> = [];

  for (let index = 0; index < bars.length; index += 1) {
    if (atr[index] == null) {
      upperBand.push(null);
      lowerBand.push(null);
      line.push(null);
      direction.push(null);
      continue;
    }

    const hl2 = (bars[index].high + bars[index].low) / 2;
    const basicUpper = hl2 + factor * (atr[index] as number);
    const basicLower = hl2 - factor * (atr[index] as number);
    const previousUpper = upperBand[index - 1];
    const previousLower = lowerBand[index - 1];
    const previousClose = index > 0 ? bars[index - 1].close : bars[index].close;

    const currentUpper =
      index === 0 || previousUpper == null || basicUpper < previousUpper || previousClose > previousUpper
        ? basicUpper
        : previousUpper;
    const currentLower =
      index === 0 || previousLower == null || basicLower > previousLower || previousClose < previousLower
        ? basicLower
        : previousLower;

    upperBand.push(currentUpper);
    lowerBand.push(currentLower);

    const previousDirection = direction[index - 1];
    let currentDirection = previousDirection ?? -1;
    if (index > 0) {
      if (bars[index].close > (previousUpper ?? currentUpper)) {
        currentDirection = -1;
      } else if (bars[index].close < (previousLower ?? currentLower)) {
        currentDirection = 1;
      }
    }

    direction.push(currentDirection);
    line.push(currentDirection < 0 ? currentLower : currentUpper);
  }

  return {
    supertrendLine: line,
    supertrendDirection: direction,
  };
}

function average(values: number[]): number {
  if (values.length === 0) {
    return 0;
  }
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function roundNumber(value: number): number {
  return Math.round(value * 1_000_000) / 1_000_000;
}
