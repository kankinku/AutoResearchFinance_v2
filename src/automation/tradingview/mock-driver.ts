import {
  applyResultSchema,
  artifactBundleSchema,
  backtestMetricsSchema,
  compileResultSchema,
  type ExecutorCapability,
  type ExecutorCompatibilityResult,
  type BacktestMetrics,
  type TraceEventV1,
  type TradeRecord,
} from "../../contracts/types.js";
import { type PineEvaluationExecutor } from "./types.js";
import { type ExecutorHealth } from "../common/executor.js";

const defaultMetrics: BacktestMetrics = {
  netProfitPercent: 12,
  postFeeNetProfitPercent: 10,
  profitFactor: 1.8,
  maxStrategyDrawdownPercent: 11,
  percentProfitable: 58,
  totalTrades: 60,
  avgTradePercent: 0.3,
};

export function createMockPineEvaluationExecutor(config?: {
  capability?: Partial<ExecutorCapability>;
  compatibility?: ExecutorCompatibilityResult;
  prepareChartError?: string;
  prepareChartErrorSequence?: string[];
  updateStrategySourceError?: string;
  readArtifactBundleError?: string;
  compile?: { ok: boolean; errors?: string[] };
  compileSequence?: Array<{ ok: boolean; errors?: string[] }>;
  apply?: {
    ok: boolean;
    message: string;
    attachDiagnostics?: {
      expectedStudyTitle: string | null;
      detectedStudyTitle: string | null;
      exactTitleMatched: boolean;
      staleStudySuspected: boolean;
      recoveryActions?: string[];
    };
    fallbackActions?: string[];
  };
  metrics?: BacktestMetrics;
  trades?: TradeRecord[];
  equity?: {
    available: boolean;
    pointsAvailable: boolean;
    pointCount: number;
    finalEquity?: number | null;
    maxDrawdownPercent?: number | null;
    points?: Array<{ time: string; value: number }>;
  };
  state?: Record<string, unknown>;
  ablations?: Record<string, BacktestMetrics>;
  rawReportHash?: string | null;
  reportDiagnostics?: Record<string, unknown>;
}): PineEvaluationExecutor {
  let currentSource = "";
  let prepareChartCallCount = 0;
  let compileCallCount = 0;
  const capability: ExecutorCapability = {
    kind: "mock",
    authoritative: true,
    supportedSymbols: ["QQQ"],
    supportedTimeframes: ["120m", "2h", "120"],
    supportedStrategyFamilies: ["AF", "mock"],
    confidenceLevel: "verification",
    ...config?.capability,
  };

  return {
    role: capability.role ?? "external_calibration",
    evidenceAuthority: capability.evidenceAuthority ?? "external_tv",
    supportedStrategyFamilies: capability.supportedStrategyFamilies,
    supportedSymbols: capability.supportedSymbols,
    supportedTimeframes: capability.supportedTimeframes,
    getCapability() {
      return capability;
    },
    async healthCheck(): Promise<ExecutorHealth> {
      return {
        healthy: true,
        status: "ready",
        detail: "Mock Pine executor is available.",
      };
    },
    async assessCompatibility() {
      return (
        config?.compatibility ?? {
          supported: true,
          reasonCode: null,
          detail: null,
          issues: [],
        }
      );
    },
    async prepareChart() {
      const sequenceError =
        config?.prepareChartErrorSequence?.[
          Math.min(
            prepareChartCallCount,
            (config.prepareChartErrorSequence?.length ?? 1) - 1,
          )
        ];
      prepareChartCallCount += 1;
      if (sequenceError ?? config?.prepareChartError) {
        throw new Error(sequenceError ?? config?.prepareChartError);
      }
      return;
    },
    async updateStrategySource(source: string) {
      if (config?.updateStrategySourceError) {
        throw new Error(config.updateStrategySourceError);
      }
      currentSource = source;
    },
    async compileStrategy() {
      const sequenceResult = config?.compileSequence?.[
        Math.min(compileCallCount, (config.compileSequence?.length ?? 1) - 1)
      ];
      compileCallCount += 1;
      return compileResultSchema.parse({
        ok: sequenceResult?.ok ?? config?.compile?.ok ?? true,
        errors: sequenceResult?.errors ?? config?.compile?.errors ?? [],
      });
    },
    async applyStrategy(input) {
      return applyResultSchema.parse({
        ok: config?.apply?.ok ?? true,
        message: config?.apply?.message ?? "applied",
        attachDiagnostics:
          config?.apply?.attachDiagnostics ?? {
            expectedStudyTitle: input?.expectedStudyTitle ?? null,
            detectedStudyTitle: input?.expectedStudyTitle ?? null,
            exactTitleMatched: true,
            staleStudySuspected: false,
            recoveryActions: [],
          },
        fallbackActions: config?.apply?.fallbackActions ?? [],
      });
    },
    async readArtifactBundle(input) {
      if (config?.readArtifactBundleError) {
        throw new Error(config.readArtifactBundleError);
      }
      if (!currentSource) {
        throw new Error("Strategy source was not updated before reading metrics.");
      }
      const strategy = backtestMetricsSchema.parse(config?.metrics ?? defaultMetrics);
      const trades = config?.trades ?? [];
      const eventTrace = Array.isArray(config?.state?.eventTrace)
        ? config.state.eventTrace
        : buildMockEventTraceFromTrades(trades);
      const applyResult = applyResultSchema.parse(
        config?.apply ?? {
          ok: true,
          message: "applied",
          attachDiagnostics: {
            expectedStudyTitle: input?.expectedStudyTitle ?? null,
            detectedStudyTitle: input?.expectedStudyTitle ?? null,
            exactTitleMatched: true,
            staleStudySuspected: false,
            recoveryActions: [],
          },
          fallbackActions: [],
        },
      );
      return artifactBundleSchema.parse({
        strategy,
        trades,
        equity:
          config?.equity ??
          {
            available: true,
            unavailableReason: null,
            pointsAvailable: true,
            pointCount: 2,
            finalEquity: 10100,
            maxDrawdownPercent: 4.2,
            points: [
              { time: "2026-04-20T00:00:00.000Z", value: 10000 },
              { time: "2026-04-20T02:00:00.000Z", value: 10100 },
            ],
          },
        attachDiagnostics: applyResult.attachDiagnostics,
        rawReportHash: config?.rawReportHash ?? "mock-raw-report-hash",
        state: {
          ...(config?.state ?? {}),
          eventTrace,
          reportDiagnostics:
            config?.reportDiagnostics ??
            {
              hasNetProfit: true,
              hasTotalTrades: true,
              hasMaxDrawdown: true,
              hasProfitFactor: true,
              hasWinRate: true,
              hasTrades: true,
              hasEquitySummary: config?.equity?.available ?? true,
              hasRawReport: (config?.rawReportHash ?? "mock-raw-report-hash") !== null,
              missingFields: [],
              parseWarnings: [],
              parserVersion: "mock-report/v2",
            },
        },
      });
    },
    async evaluateAblation(input) {
      const metrics = config?.ablations?.[input.condition.conditionId];
      return metrics ? backtestMetricsSchema.parse(metrics) : null;
    },
  };
}

function buildMockEventTraceFromTrades(trades: TradeRecord[]): TraceEventV1[] {
  return trades.flatMap((trade, index) => {
    const entryEvent: TraceEventV1 = {
      barIndex: index * 2,
      time: trade.entryTime ?? `mock-entry-${index}`,
      orderAction: "entry",
      finalBullEvent: 1,
      finalBearEvent: 0,
      entryPass: true,
      entryRank: 1,
      exitReason: null,
      slotCount: 1,
    };
    const exitEvent: TraceEventV1 = {
      barIndex: index * 2 + 1,
      time: trade.exitTime ?? `mock-exit-${index}`,
      orderAction: "exit",
      finalBullEvent: 0,
      finalBearEvent: 1,
      entryPass: false,
      entryRank: 0,
      exitReason: trade.exitComment ?? "exit",
      slotCount: 0,
    };
    return [entryEvent, exitEvent];
  });
}
