import {
  type ApplyResult,
  type ArtifactBundle,
  type ExecutorCapability,
  type ExecutorRole,
  type EvidenceAuthority,
  type ExecutorCompatibilityResult,
  type BacktestMetrics,
  type ChartTarget,
  type CompileResult,
  type ConditionInventoryItem,
  type LocalCompatibilityContract,
  type SurfaceRecoveryAction,
  type SyncArtifact,
  type VerificationRuntimeFailureKind,
} from "../../contracts/types.js";

export interface ExecutorHealth {
  healthy: boolean;
  status: "ready" | "degraded" | "unavailable";
  detail: string | null;
}

export interface PineEvaluationExecutor {
  readonly role: ExecutorRole;
  readonly evidenceAuthority: EvidenceAuthority;
  readonly supportedStrategyFamilies: string[];
  readonly supportedSymbols: string[];
  readonly supportedTimeframes: string[];
  getCapability(): ExecutorCapability;
  healthCheck(): Promise<ExecutorHealth>;
  getCompatibilityContract?(): LocalCompatibilityContract | null;
  prepareChart(input: ChartTarget): Promise<void>;
  assessCompatibility?(input: {
    source: string;
    chartTarget: ChartTarget;
  }): Promise<ExecutorCompatibilityResult> | ExecutorCompatibilityResult;
  updateStrategySource(source: string): Promise<void>;
  compileStrategy(): Promise<CompileResult>;
  applyStrategy(input?: { expectedStudyTitle?: string | null }): Promise<ApplyResult>;
  readArtifactBundle(input?: {
    expectedStudyTitle?: string | null;
    maxTrades?: number;
  }): Promise<ArtifactBundle>;
  buildSyncArtifact?(input: {
    chartTarget: ChartTarget;
    compile: CompileResult;
    apply?: ApplyResult;
  }): Promise<SyncArtifact> | SyncArtifact;
  recoverSurface?(input: {
    action: SurfaceRecoveryAction;
    chartTarget: ChartTarget;
    failureKind: VerificationRuntimeFailureKind;
  }): Promise<void>;
  evaluateAblation?(input: {
    condition: ConditionInventoryItem;
    source: string;
  }): Promise<BacktestMetrics | null>;
  close?(): Promise<void>;
}
