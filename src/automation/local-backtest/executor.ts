import {
  applyResultSchema,
  artifactBundleSchema,
  compileResultSchema,
  executorCompatibilityResultSchema,
  syncArtifactSchema,
  type ArtifactBundle,
  type ChartTarget,
  type CompileResult,
  type ExecutorCapability,
  type SyncArtifact,
} from "../../contracts/types.js";
import { type ExecutorHealth, type PineEvaluationExecutor } from "../common/executor.js";
import {
  getAfLocalCompatibilityContract,
  parseAfStrategyConfig,
  type AfStrategyConfig,
} from "./af-config.js";
import { simulateAfStrategy } from "./af-simulator.js";
import { loadLocalBacktestBars } from "./context.js";

interface LocalBacktestExecutorConfig {
  workspaceRoot: string;
  stateRoot?: string;
}

interface ParsedSourceState {
  config: AfStrategyConfig;
  source: string;
}

type LocalSimulationResult = ReturnType<typeof simulateAfStrategy>;

export class LocalAfBacktestExecutor implements PineEvaluationExecutor {
  public readonly role = "primary_local_backtest";
  public readonly evidenceAuthority = "local_model";
  public readonly supportedStrategyFamilies = ["AF"];
  public readonly supportedSymbols = ["QQQ", "BTC", "BTCUSD", "BTCUSDT"];
  public readonly supportedTimeframes = ["15", "15m", "120m", "2h", "120"];
  private readonly workspaceRoot: string;
  private readonly stateRoot: string | undefined;
  private currentSource = "";
  private parsedState: ParsedSourceState | null = null;
  private simulationCache: {
    source: string;
    result: LocalSimulationResult;
  } | null = null;
  private lastCompile: CompileResult | null = null;
  private lastChartTarget: ChartTarget | null = null;

  public constructor(config: LocalBacktestExecutorConfig) {
    this.workspaceRoot = config.workspaceRoot;
    this.stateRoot = config.stateRoot;
  }

  public getCapability(): ExecutorCapability {
    return {
      kind: "local-af-backtest",
      authoritative: false,
      supportedSymbols: this.supportedSymbols,
      supportedTimeframes: this.supportedTimeframes,
      supportedStrategyFamilies: this.supportedStrategyFamilies,
      confidenceLevel: "screening",
      role: this.role,
      evidenceAuthority: this.evidenceAuthority,
    };
  }

  public async healthCheck(): Promise<ExecutorHealth> {
    return {
      healthy: true,
      status: "ready",
      detail: "Local AF backtest executor is available.",
    };
  }

  public getCompatibilityContract() {
    return getAfLocalCompatibilityContract();
  }

  public async prepareChart(input: ChartTarget): Promise<void> {
    this.lastChartTarget = input;
    const normalizedTimeframe = normalizeTimeframe(input.timeframe);
    const normalizedSymbol = normalizeSymbol(input.symbol);
    if (!isSupportedLocalTarget(normalizedSymbol, normalizedTimeframe)) {
      throw new Error(
        `Local backtest executor does not support chart target ${input.symbol}:${input.timeframe}.`,
      );
    }
  }

  public async updateStrategySource(source: string): Promise<void> {
    this.currentSource = source;
    this.parsedState = null;
    this.simulationCache = null;
  }

  public assessCompatibility(input: {
    source: string;
    chartTarget: ChartTarget;
  }) {
    const normalizedTimeframe = normalizeTimeframe(input.chartTarget.timeframe);
    const normalizedSymbol = normalizeSymbol(input.chartTarget.symbol);
    if (!isSupportedLocalTarget(normalizedSymbol, normalizedTimeframe)) {
      return executorCompatibilityResultSchema.parse({
        supported: false,
        reasonCode: "unsupported_chart_target",
        detail: `Local backtest executor does not support chart target ${input.chartTarget.symbol}:${input.chartTarget.timeframe}.`,
        issues: [
          {
            kind: "unsupported_pattern",
            code: "unsupported_chart_target",
            field: "chartTarget",
            detail: `Local backtest executor does not support chart target ${input.chartTarget.symbol}:${input.chartTarget.timeframe}.`,
          },
        ],
      });
    }

    const parsed = parseAfStrategyConfig(input.source);
    if (parsed.compatibilityIssues.length > 0) {
      return executorCompatibilityResultSchema.parse({
        supported: false,
        reasonCode: "unsupported_strategy_family",
        detail: parsed.compatibilityIssues.map((issue) => issue.code).join(", "),
        issues: parsed.compatibilityIssues,
      });
    }

    return executorCompatibilityResultSchema.parse({
      supported: true,
      reasonCode: null,
      detail: null,
      issues: [],
    });
  }

  public async compileStrategy(): Promise<CompileResult> {
    try {
      const parsed = this.requireParsedState();
      const compile = compileResultSchema.parse({
        ok: parsed.config.studyTitle != null,
        errors: parsed.config.studyTitle == null ? ["Failed to extract strategy title."] : [],
      });
      this.lastCompile = compile;
      return compile;
    } catch (error) {
      const compile = compileResultSchema.parse({
        ok: false,
        errors: [error instanceof Error ? error.message : String(error)],
      });
      this.lastCompile = compile;
      return compile;
    }
  }

  public async applyStrategy(input?: { expectedStudyTitle?: string | null }) {
    const config = this.requireParsedState().config;
    return applyResultSchema.parse({
      ok: true,
      message: "Local backtest module prepared candidate for simulation.",
      attachDiagnostics: {
        expectedStudyTitle: input?.expectedStudyTitle ?? config.studyTitle,
        detectedStudyTitle: config.studyTitle,
        exactTitleMatched:
          (input?.expectedStudyTitle ?? config.studyTitle) === config.studyTitle,
        staleStudySuspected: false,
        recoveryActions: [],
      },
      fallbackActions: [],
    });
  }

  public async readArtifactBundle(input?: {
    expectedStudyTitle?: string | null;
    maxTrades?: number;
  }): Promise<ArtifactBundle> {
    const parsed = this.requireParsedState();
    const simulation = await this.getSimulation(parsed);
    const limitedTrades =
      input?.maxTrades == null
        ? simulation.artifactBundle.trades
        : simulation.artifactBundle.trades.slice(0, input.maxTrades);

    return artifactBundleSchema.parse({
      ...simulation.artifactBundle,
      trades: limitedTrades,
      attachDiagnostics: {
        expectedStudyTitle: input?.expectedStudyTitle ?? parsed.config.studyTitle,
        detectedStudyTitle: parsed.config.studyTitle,
        exactTitleMatched:
          (input?.expectedStudyTitle ?? parsed.config.studyTitle) ===
          parsed.config.studyTitle,
        staleStudySuspected: false,
        recoveryActions: [],
      },
      state: {
        ...simulation.artifactBundle.state,
        engine: "local-backtest",
        chartTarget: this.lastChartTarget,
      },
    });
  }

  public async buildSyncArtifact(input: {
    chartTarget: ChartTarget;
    compile: CompileResult;
  }): Promise<SyncArtifact> {
    return syncArtifactSchema.parse({
      chartTarget: input.chartTarget,
      compile: input.compile,
      stateAfter: {
        engine: "local-backtest",
        sourceLength: this.currentSource.length,
      },
    });
  }

  private requireParsedState(): ParsedSourceState {
    if (this.parsedState) {
      return this.parsedState;
    }
    if (!this.currentSource) {
      throw new Error("Local backtest executor did not receive a Pine source.");
    }

    const parsed = parseAfStrategyConfig(this.currentSource);
    if (parsed.compatibilityIssues.length > 0) {
      throw new Error(
        `Local backtest executor does not support this candidate cleanly: ${parsed.compatibilityIssues.map((issue) => issue.code).join(", ")}`,
      );
    }

    this.parsedState = {
      config: parsed.config,
      source: this.currentSource,
    };
    return this.parsedState;
  }

  private async loadBars() {
    return loadLocalBacktestBars(this.workspaceRoot, {
      stateRoot: this.stateRoot,
      chartTarget: this.lastChartTarget ?? undefined,
    });
  }

  private async getSimulation(parsed: ParsedSourceState): Promise<LocalSimulationResult> {
    if (this.simulationCache?.source === parsed.source) {
      return this.simulationCache.result;
    }

    const bars = await this.loadBars();
    const result = simulateAfStrategy(bars, parsed.config);
    this.simulationCache = {
      source: parsed.source,
      result,
    };
    return result;
  }
}

function normalizeSymbol(value: string): string {
  const bare = value.trim().toUpperCase().split(":").at(-1) ?? value.trim().toUpperCase();
  if (bare === "BTC" || bare === "BTCUSD" || bare === "BTCUSDT" || bare === "BTC-USD") {
    return "BTC";
  }
  return bare;
}

function normalizeTimeframe(value: string): string {
  const normalized = value.trim().toLowerCase();
  if (normalized === "120" || normalized === "120m") {
    return "2h";
  }
  if (normalized === "15") {
    return "15m";
  }
  return normalized;
}

function isSupportedLocalTarget(symbol: string, timeframe: string): boolean {
  return (
    (symbol === "QQQ" && timeframe === "2h") ||
    (symbol === "BTC" && timeframe === "15m")
  );
}
