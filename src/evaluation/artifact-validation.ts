import {
  artifactValidationResultSchema,
  type ArtifactBundle,
  type ArtifactValidationResult,
  type ExecutorCapability,
} from "../contracts/types.js";

const DEFAULT_PARSER_VERSION = "artifact-validation/v2";
const AUTHORITATIVE_COMPLETENESS_MIN = 0.75;
const PROMOTION_READINESS_MIN = 0.8;
const EQUITY_FIELD = "equity_summary";
const VERIFICATION_THRESHOLD_FIELD = "verification_completeness_threshold";
const PROMOTION_THRESHOLD_FIELD = "promotion_completeness_threshold";

export function validateArtifactBundle(input: {
  artifactBundle: ArtifactBundle;
  executorCapability: ExecutorCapability;
}): ArtifactValidationResult {
  const metrics = input.artifactBundle.strategy;
  const reportDiagnostics = readReportDiagnostics(input.artifactBundle);
  const hasMetrics = metrics !== null;
  const hasNetProfit = reportDiagnostics?.hasNetProfit ?? hasMetrics;
  const hasTotalTrades = reportDiagnostics?.hasTotalTrades ?? hasMetrics;
  const hasMaxDrawdown = reportDiagnostics?.hasMaxDrawdown ?? hasMetrics;
  const hasProfitFactor = reportDiagnostics?.hasProfitFactor ?? hasMetrics;
  const hasWinRate = reportDiagnostics?.hasWinRate ?? hasMetrics;
  const hasTrades =
    reportDiagnostics?.hasTrades ??
    (Array.isArray(input.artifactBundle.trades) &&
      ((input.artifactBundle.trades?.length ?? 0) > 0 ||
        ((metrics?.totalTrades ?? 0) === 0 && hasMetrics)));
  const hasEquitySummary =
    reportDiagnostics?.hasEquitySummary ??
    (input.artifactBundle.equity.available ||
      input.artifactBundle.equity.pointsAvailable);
  const hasRawReport =
    reportDiagnostics?.hasRawReport ?? Boolean(input.artifactBundle.rawReportHash);

  const missingFields = [
    ...(reportDiagnostics?.missingFields ?? []),
    ...collectFallbackMissingFields({
      hasMetrics,
      hasNetProfit,
      hasTotalTrades,
      hasMaxDrawdown,
      hasProfitFactor,
      hasWinRate,
      hasTrades,
      hasEquitySummary,
      hasRawReport,
      executorCapability: input.executorCapability,
    }),
  ].filter((value, index, values) => values.indexOf(value) === index);

  const completenessParts = [
    hasNetProfit ? 1 : 0,
    hasTotalTrades ? 1 : 0,
    hasMaxDrawdown ? 1 : 0,
    hasProfitFactor ? 1 : 0,
    hasWinRate ? 1 : 0,
    hasTrades ? 1 : 0,
    hasEquitySummary ? 1 : 0,
    1,
  ];
  const completenessScore =
    Math.round(
      (completenessParts.reduce((sum, part) => sum + part, 0) /
        completenessParts.length) *
        1_000_000,
    ) / 1_000_000;
  const verificationReady =
    hasNetProfit &&
    hasTotalTrades &&
    hasMaxDrawdown &&
    hasProfitFactor &&
    hasWinRate &&
    completenessScore >= AUTHORITATIVE_COMPLETENESS_MIN;
  const missingForVerification = collectVerificationMissingFields({
    hasNetProfit,
    hasTotalTrades,
    hasMaxDrawdown,
    hasProfitFactor,
    hasWinRate,
    hasRawReport: true,
    completenessScore,
  });
  const promotionReady =
    verificationReady &&
    hasTrades &&
    hasEquitySummary &&
    completenessScore >= PROMOTION_READINESS_MIN;
  const missingForPromotion = collectPromotionMissingFields({
    missingForVerification,
    hasTrades,
    hasEquitySummary,
    completenessScore,
  });

  return artifactValidationResultSchema.parse({
    hasMetrics,
    hasNetProfit,
    hasTotalTrades,
    hasMaxDrawdown,
    hasProfitFactor,
    hasWinRate,
    hasTrades,
    hasEquitySummary,
    hasRawReport,
    verificationReady,
    promotionReady,
    completenessScore,
    missingFields,
    missingForVerification,
    missingForPromotion,
    parseWarnings: reportDiagnostics?.parseWarnings ?? [],
    parserVersion: reportDiagnostics?.parserVersion ?? DEFAULT_PARSER_VERSION,
  });
}

export function isArtifactVerificationReady(
  validation: ArtifactValidationResult,
): boolean {
  return validation.verificationReady;
}

export function isArtifactPromotionReady(
  validation: ArtifactValidationResult,
): boolean {
  return validation.promotionReady;
}

function readReportDiagnostics(
  bundle: ArtifactBundle,
):
  | {
      hasNetProfit?: boolean;
      hasTotalTrades?: boolean;
      hasMaxDrawdown?: boolean;
      hasProfitFactor?: boolean;
      hasWinRate?: boolean;
      hasTrades?: boolean;
      hasEquitySummary?: boolean;
      hasRawReport?: boolean;
      missingFields?: string[];
      parseWarnings?: string[];
      parserVersion?: string;
    }
  | null {
  const raw =
    bundle.state && typeof bundle.state === "object"
      ? (bundle.state.reportDiagnostics as Record<string, unknown> | undefined)
      : undefined;
  if (!raw || typeof raw !== "object") {
    return null;
  }
  return {
    hasNetProfit: typeof raw.hasNetProfit === "boolean" ? raw.hasNetProfit : undefined,
    hasTotalTrades:
      typeof raw.hasTotalTrades === "boolean" ? raw.hasTotalTrades : undefined,
    hasMaxDrawdown:
      typeof raw.hasMaxDrawdown === "boolean" ? raw.hasMaxDrawdown : undefined,
    hasProfitFactor:
      typeof raw.hasProfitFactor === "boolean" ? raw.hasProfitFactor : undefined,
    hasWinRate: typeof raw.hasWinRate === "boolean" ? raw.hasWinRate : undefined,
    hasTrades: typeof raw.hasTrades === "boolean" ? raw.hasTrades : undefined,
    hasEquitySummary:
      typeof raw.hasEquitySummary === "boolean" ? raw.hasEquitySummary : undefined,
    hasRawReport: typeof raw.hasRawReport === "boolean" ? raw.hasRawReport : undefined,
    missingFields: Array.isArray(raw.missingFields)
      ? raw.missingFields.filter((entry): entry is string => typeof entry === "string")
      : undefined,
    parseWarnings: Array.isArray(raw.parseWarnings)
      ? raw.parseWarnings.filter((entry): entry is string => typeof entry === "string")
      : undefined,
    parserVersion:
      typeof raw.parserVersion === "string" && raw.parserVersion.length > 0
        ? raw.parserVersion
        : undefined,
  };
}

function collectFallbackMissingFields(input: {
  hasMetrics: boolean;
  hasNetProfit: boolean;
  hasTotalTrades: boolean;
  hasMaxDrawdown: boolean;
  hasProfitFactor: boolean;
  hasWinRate: boolean;
  hasTrades: boolean;
  hasEquitySummary: boolean;
  hasRawReport: boolean;
  executorCapability: ExecutorCapability;
}): string[] {
  const missingFields: string[] = [];
  if (!input.hasMetrics) {
    missingFields.push("metrics");
  }
  if (!input.hasNetProfit) {
    missingFields.push("net_profit");
  }
  if (!input.hasTotalTrades) {
    missingFields.push("total_trades");
  }
  if (!input.hasMaxDrawdown) {
    missingFields.push("max_drawdown");
  }
  if (!input.hasProfitFactor) {
    missingFields.push("profit_factor");
  }
  if (!input.hasWinRate) {
    missingFields.push("win_rate");
  }
  if (!input.hasTrades) {
    missingFields.push("trades");
  }
  if (!input.hasEquitySummary) {
    missingFields.push(EQUITY_FIELD);
  }
  return missingFields;
}

function collectVerificationMissingFields(input: {
  hasNetProfit: boolean;
  hasTotalTrades: boolean;
  hasMaxDrawdown: boolean;
  hasProfitFactor: boolean;
  hasWinRate: boolean;
  hasRawReport: boolean;
  completenessScore: number;
}): string[] {
  const missingFields: string[] = [];
  if (!input.hasNetProfit) {
    missingFields.push("net_profit");
  }
  if (!input.hasTotalTrades) {
    missingFields.push("total_trades");
  }
  if (!input.hasMaxDrawdown) {
    missingFields.push("max_drawdown");
  }
  if (!input.hasProfitFactor) {
    missingFields.push("profit_factor");
  }
  if (!input.hasWinRate) {
    missingFields.push("win_rate");
  }
  if (input.completenessScore < AUTHORITATIVE_COMPLETENESS_MIN) {
    missingFields.push(VERIFICATION_THRESHOLD_FIELD);
  }
  return missingFields;
}

function collectPromotionMissingFields(input: {
  missingForVerification: string[];
  hasTrades: boolean;
  hasEquitySummary: boolean;
  completenessScore: number;
}): string[] {
  const missingFields = [...input.missingForVerification];
  if (!input.hasTrades) {
    missingFields.push("trades");
  }
  if (!input.hasEquitySummary) {
    missingFields.push(EQUITY_FIELD);
  }
  if (input.completenessScore < PROMOTION_READINESS_MIN) {
    missingFields.push(PROMOTION_THRESHOLD_FIELD);
  }
  return missingFields.filter(
    (value, index, values) => values.indexOf(value) === index,
  );
}
