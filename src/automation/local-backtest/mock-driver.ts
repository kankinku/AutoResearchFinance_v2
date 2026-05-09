import {
  applyResultSchema,
  artifactBundleSchema,
  backtestMetricsSchema,
  compileResultSchema,
  type ApplyResult,
  type ArtifactBundle,
  type BacktestMetrics,
  type ChartTarget,
  type CompileResult,
  type ExecutorCapability,
  type ExecutorCompatibilityResult,
  type TradeRecord,
} from "../../contracts/types.js";
import { type ExecutorHealth, type PineEvaluationExecutor } from "../common/executor.js";

export interface MockPineEvaluationExecutorOptions {
  compile?: CompileResult;
  apply?: ApplyResult;
  artifactBundle?: ArtifactBundle;
  capability?: Partial<ExecutorCapability>;
  compatibility?: ExecutorCompatibilityResult;
  prepareChartError?: string;
  prepareChartErrorSequence?: string[];
  updateStrategySourceError?: string;
  compileError?: string;
  compileSequence?: Array<{ ok: boolean; errors?: string[] }>;
  applyError?: string;
  readArtifactError?: string;
  metrics?: BacktestMetrics;
  trades?: TradeRecord[];
  equity?: Partial<ArtifactBundle["equity"]>;
  state?: Record<string, unknown>;
  ablations?: Record<string, BacktestMetrics>;
  rawReportHash?: string | null;
  reportDiagnostics?: Record<string, unknown>;
}

export function createMockPineEvaluationExecutor(
  options: MockPineEvaluationExecutorOptions = {},
): PineEvaluationExecutor {
  let source = "";
  let chartTarget: ChartTarget | null = null;
  let prepareChartCallCount = 0;
  let compileCallCount = 0;
  return {
    role: "primary_local_backtest",
    evidenceAuthority: "local_model",
    supportedStrategyFamilies: ["AF"],
    supportedSymbols: ["QQQ", "BTC", "BTCUSD", "BTCUSDT"],
    supportedTimeframes: ["15", "15m", "120", "120m", "2h"],
    getCapability(): ExecutorCapability {
      return {
        kind: "local-af-backtest",
        authoritative: true,
        supportedSymbols: this.supportedSymbols,
        supportedTimeframes: this.supportedTimeframes,
        supportedStrategyFamilies: this.supportedStrategyFamilies,
        confidenceLevel: "verification",
        role: this.role,
        evidenceAuthority: this.evidenceAuthority,
        ...options.capability,
      };
    },
    async healthCheck(): Promise<ExecutorHealth> {
      return {
        healthy: true,
        status: "ready",
        detail: "Mock local backtest executor is available.",
      };
    },
    async assessCompatibility() {
      return (
        options.compatibility ?? {
          supported: true,
          reasonCode: null,
          detail: null,
          issues: [],
        }
      );
    },
    async prepareChart(input: ChartTarget): Promise<void> {
      const sequenceError =
        options.prepareChartErrorSequence?.[
          Math.min(
            prepareChartCallCount,
            (options.prepareChartErrorSequence?.length ?? 1) - 1,
          )
        ];
      prepareChartCallCount += 1;
      if (sequenceError ?? options.prepareChartError) {
        throw new Error(sequenceError ?? options.prepareChartError);
      }
      chartTarget = input;
    },
    async updateStrategySource(input: string): Promise<void> {
      if (options.updateStrategySourceError) {
        throw new Error(options.updateStrategySourceError);
      }
      source = input;
    },
    async compileStrategy(): Promise<CompileResult> {
      if (options.compileError) {
        throw new Error(options.compileError);
      }
      const sequenceResult =
        options.compileSequence?.[
          Math.min(compileCallCount, (options.compileSequence?.length ?? 1) - 1)
        ];
      compileCallCount += 1;
      return compileResultSchema.parse({
        ok: sequenceResult?.ok ?? options.compile?.ok ?? true,
        errors: sequenceResult?.errors ?? options.compile?.errors ?? [],
      });
    },
    async applyStrategy(): Promise<ApplyResult> {
      if (options.applyError) {
        throw new Error(options.applyError);
      }
      return (
        options.apply ??
        applyResultSchema.parse({
          ok: true,
          message: "Mock local executor applied strategy.",
          attachDiagnostics: {
            expectedStudyTitle: null,
            detectedStudyTitle: null,
            exactTitleMatched: true,
            staleStudySuspected: false,
            recoveryActions: [],
          },
          fallbackActions: [],
        })
      );
    },
    async readArtifactBundle(): Promise<ArtifactBundle> {
      if (options.readArtifactError) {
        throw new Error(options.readArtifactError);
      }
      return (
        options.artifactBundle ??
        artifactBundleSchema.parse({
          strategy: backtestMetricsSchema.parse(options.metrics ?? defaultMetrics()),
          trades: options.trades ?? [],
          equity: {
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
            ...(options.equity ?? {}),
          },
          attachDiagnostics:
            options.apply?.attachDiagnostics ?? {
              expectedStudyTitle: null,
              detectedStudyTitle: null,
              exactTitleMatched: true,
              staleStudySuspected: false,
              recoveryActions: [],
            },
          rawReportHash: options.rawReportHash ?? "local-mock-raw-report-hash",
          state: {
            ...(options.state ?? {}),
            engine: "local-mock",
            sourceLength: source.length,
            chartTarget,
            reportDiagnostics:
              options.reportDiagnostics ?? {
                hasNetProfit: true,
                hasTotalTrades: true,
                hasMaxDrawdown: true,
                hasProfitFactor: true,
                hasWinRate: true,
                hasTrades: true,
                hasEquitySummary: options.equity?.available ?? true,
                hasRawReport: (options.rawReportHash ?? "local-mock-raw-report-hash") !== null,
                missingFields: [],
                parseWarnings: [],
                parserVersion: "local-mock/v1",
              },
          },
        })
      );
    },
    async evaluateAblation(input) {
      return options.ablations?.[input.condition.conditionId] ?? null;
    },
    async close(): Promise<void> {
      return;
    },
  };
}

function defaultMetrics(): BacktestMetrics {
  return {
    netProfitPercent: 1,
    postFeeNetProfitPercent: 0.95,
    profitFactor: 1.4,
    maxStrategyDrawdownPercent: 0.5,
    percentProfitable: 60,
    totalTrades: 10,
    avgTradePercent: 0.1,
  };
}
