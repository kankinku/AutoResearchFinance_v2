import {
  localExecutionTraceEntrySchema,
  localPortfolioSnapshotSchema,
  simulatedFillSchema,
  simulatedOrderSchema,
  tradeRecordSchema,
  type LocalExecutionTraceEntry,
  type LocalPortfolioSnapshot,
  type SimulatedFill,
  type SimulatedFillPolicy,
  type SimulatedOrder,
  type TradeRecord,
} from "../../contracts/types.js";

export const LOCAL_BACKTEST_VERSION = "local-af-backtest/v2";

export interface LocalSlotPosition {
  id: string;
  entryPrice: number;
  qty: number;
  rank: number;
  entryBarIndex: number;
  entryTime: string;
  peakHigh: number;
  troughLow: number;
  entryCommission: number;
  entryOrderId: string;
  entryFillId: string;
}

export interface LocalExecutionFillResult {
  order: SimulatedOrder;
  fill: SimulatedFill;
  trade: TradeRecord | null;
  slot: LocalSlotPosition | null;
}

export interface LocalExecutionLedgerConfig {
  initialCapital: number;
  commissionPercent: number;
  processOrdersOnClose: boolean;
}

export interface EnterSlotInput {
  close: number;
  high: number;
  low: number;
  qty: number;
  rank: number;
  barIndex: number;
  time: string;
  nextSlotNo: number;
  reason: string;
}

export interface CloseSlotInput {
  close: number;
  barIndex: number;
  time: string;
  reason: string;
}

export interface PortfolioSnapshotInput {
  barIndex: number;
  time: string;
  markPrice: number;
  orderIds: string[];
  fillIds: string[];
}

export class LocalExecutionLedger {
  public readonly slots: LocalSlotPosition[] = [];
  public readonly trades: TradeRecord[] = [];
  public readonly orders: SimulatedOrder[] = [];
  public readonly fills: SimulatedFill[] = [];
  public readonly portfolioSnapshots: LocalPortfolioSnapshot[] = [];
  private readonly executionTrace: LocalExecutionTraceEntry[] = [];
  private readonly commissionPercent: number;
  private readonly processOrdersOnClose: boolean;
  private orderSequence = 0;
  private fillSequence = 0;
  private snapshotSequence = 0;
  private realizedPnl = 0;
  private cashValue: number;

  public constructor(config: LocalExecutionLedgerConfig) {
    this.commissionPercent = config.commissionPercent;
    this.processOrdersOnClose = config.processOrdersOnClose;
    this.cashValue = config.initialCapital;
  }

  public get cash(): number {
    return this.cashValue;
  }

  public get cumulativeRealizedPnl(): number {
    return this.realizedPnl;
  }

  public updateSlotExtremes(high: number, low: number): void {
    for (const slot of this.slots) {
      slot.peakHigh = Math.max(slot.peakHigh, high);
      slot.troughLow = Math.min(slot.troughLow, low);
    }
  }

  public currentEquity(markPrice: number): number {
    return this.cashValue + this.currentPositionValue(markPrice);
  }

  public currentPositionValue(markPrice: number): number {
    return this.slots.reduce((sum, slot) => sum + slot.qty * markPrice, 0);
  }

  public currentOpenQuantity(): number {
    return this.slots.reduce((sum, slot) => sum + slot.qty, 0);
  }

  public enterSlot(input: EnterSlotInput): LocalExecutionFillResult {
    const slotId = `L_${input.nextSlotNo}`;
    const order = this.createOrder({
      slotId,
      barIndex: input.barIndex,
      time: input.time,
      side: "buy",
      quantity: input.qty,
      price: input.close,
      reason: input.reason,
    });
    const grossValue = input.close * input.qty;
    const commission = grossValue * (this.commissionPercent / 100);
    const netCashChange = -(grossValue + commission);
    this.cashValue += netCashChange;

    const fill = this.createFill({
      order,
      slotId,
      barIndex: input.barIndex,
      time: input.time,
      side: "buy",
      quantity: input.qty,
      price: input.close,
      grossValue,
      commission,
      netCashChange,
      realizedPnl: null,
    });
    const slot: LocalSlotPosition = {
      id: slotId,
      entryPrice: input.close,
      qty: input.qty,
      rank: input.rank,
      entryBarIndex: input.barIndex,
      entryTime: input.time,
      peakHigh: input.high,
      troughLow: input.low,
      entryCommission: commission,
      entryOrderId: order.orderId,
      entryFillId: fill.fillId,
    };
    this.slots.push(slot);
    this.appendExecutionTrace(order, fill);

    return {
      order,
      fill,
      trade: null,
      slot,
    };
  }

  public closeSlot(
    slotIndex: number,
    input: CloseSlotInput,
  ): LocalExecutionFillResult {
    const [slot] = this.slots.splice(slotIndex, 1);
    if (!slot) {
      throw new Error(`Cannot close missing local slot at index ${slotIndex}.`);
    }

    const order = this.createOrder({
      slotId: slot.id,
      barIndex: input.barIndex,
      time: input.time,
      side: "sell",
      quantity: slot.qty,
      price: input.close,
      reason: input.reason,
    });
    const grossValue = input.close * slot.qty;
    const commission = grossValue * (this.commissionPercent / 100);
    const netCashChange = grossValue - commission;
    const costBasis = slot.entryPrice * slot.qty + slot.entryCommission;
    const realizedPnl = netCashChange - costBasis;
    this.cashValue += netCashChange;
    this.realizedPnl += realizedPnl;

    const fill = this.createFill({
      order,
      slotId: slot.id,
      barIndex: input.barIndex,
      time: input.time,
      side: "sell",
      quantity: slot.qty,
      price: input.close,
      grossValue,
      commission,
      netCashChange,
      realizedPnl,
    });
    const trade = tradeRecordSchema.parse({
      entryComment: slot.id,
      entryPrice: roundNumber(slot.entryPrice),
      entryTime: slot.entryTime,
      exitComment: `Close entry(s) order ${slot.id}`,
      exitPrice: roundNumber(input.close),
      exitTime: input.time,
      qty: roundNumber(slot.qty),
      profitValue: roundNumber(realizedPnl),
      profitPercent: roundNumber(costBasis > 0 ? (realizedPnl / costBasis) * 100 : 0),
      runupPercent: roundNumber(((slot.peakHigh - slot.entryPrice) / slot.entryPrice) * 100),
      drawdownPercent: roundNumber(((slot.entryPrice - slot.troughLow) / slot.entryPrice) * 100),
    });
    this.trades.push(trade);
    this.appendExecutionTrace(order, fill);

    return {
      order,
      fill,
      trade,
      slot,
    };
  }

  public closeAllOpenSlots(input: CloseSlotInput): LocalExecutionFillResult[] {
    const results: LocalExecutionFillResult[] = [];
    while (this.slots.length > 0) {
      results.push(this.closeSlot(0, input));
    }
    return results;
  }

  public recordPortfolioSnapshot(
    input: PortfolioSnapshotInput,
  ): LocalPortfolioSnapshot {
    this.snapshotSequence += 1;
    const snapshot = localPortfolioSnapshotSchema.parse({
      snapshotId: formatId("snapshot", this.snapshotSequence),
      barIndex: input.barIndex,
      time: input.time,
      cash: roundNumber(this.cashValue),
      positionValue: roundNumber(this.currentPositionValue(input.markPrice)),
      equity: roundNumber(this.currentEquity(input.markPrice)),
      openSlotCount: this.slots.length,
      openQuantity: roundNumber(this.currentOpenQuantity()),
      realizedPnl: roundNumber(this.realizedPnl),
      orderIds: input.orderIds,
      fillIds: input.fillIds,
    });
    this.portfolioSnapshots.push(snapshot);
    return snapshot;
  }

  public getExecutionTrace(): LocalExecutionTraceEntry[] {
    return this.executionTrace;
  }

  private createOrder(input: {
    slotId: string;
    barIndex: number;
    time: string;
    side: "buy" | "sell";
    quantity: number;
    price: number;
    reason: string;
  }): SimulatedOrder {
    this.orderSequence += 1;
    const order = simulatedOrderSchema.parse({
      orderId: formatId("order", this.orderSequence),
      slotId: input.slotId,
      parentOrderId: null,
      barIndex: input.barIndex,
      time: input.time,
      side: input.side,
      orderType: "market",
      status: "filled",
      quantity: roundNumber(input.quantity),
      requestedPrice: roundNumber(input.price),
      fillPolicy: this.resolveFillPolicy(),
      reason: input.reason,
    });
    this.orders.push(order);
    return order;
  }

  private createFill(input: {
    order: SimulatedOrder;
    slotId: string;
    barIndex: number;
    time: string;
    side: "buy" | "sell";
    quantity: number;
    price: number;
    grossValue: number;
    commission: number;
    netCashChange: number;
    realizedPnl: number | null;
  }): SimulatedFill {
    this.fillSequence += 1;
    const fill = simulatedFillSchema.parse({
      fillId: formatId("fill", this.fillSequence),
      orderId: input.order.orderId,
      slotId: input.slotId,
      barIndex: input.barIndex,
      time: input.time,
      side: input.side,
      quantity: roundNumber(input.quantity),
      price: roundNumber(input.price),
      cost: {
        commissionPercent: this.commissionPercent,
        commission: roundNumber(input.commission),
        grossValue: roundNumber(input.grossValue),
        netCashChange: roundNumber(input.netCashChange),
      },
      realizedPnl: input.realizedPnl == null ? null : roundNumber(input.realizedPnl),
      cashAfter: roundNumber(this.cashValue),
    });
    this.fills.push(fill);
    return fill;
  }

  private appendExecutionTrace(
    order: SimulatedOrder,
    fill: SimulatedFill,
  ): void {
    this.executionTrace.push(
      localExecutionTraceEntrySchema.parse({
        sequence: this.executionTrace.length + 1,
        barIndex: fill.barIndex,
        time: fill.time,
        orderId: order.orderId,
        fillId: fill.fillId,
        slotId: fill.slotId,
        side: fill.side,
        reason: order.reason,
        quantity: fill.quantity,
        price: fill.price,
        commission: fill.cost.commission,
        cashAfter: fill.cashAfter,
        realizedPnl: fill.realizedPnl,
      }),
    );
  }

  private resolveFillPolicy(): SimulatedFillPolicy {
    return this.processOrdersOnClose ? "close" : "next_open";
  }
}

function formatId(prefix: string, value: number): string {
  return `${prefix}-${value.toString().padStart(6, "0")}`;
}

function roundNumber(value: number): number {
  return Math.round(value * 1_000_000) / 1_000_000;
}
