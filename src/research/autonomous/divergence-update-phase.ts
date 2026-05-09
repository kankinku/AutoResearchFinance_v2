import {
  localTvParitySummarySchema,
  type BacktestMetrics,
  type TraceEventV1,
  type TradeRecord,
} from "../../contracts/types.js";
import {
  type AutonomousExperimentRecord,
  type CalibrationEventRecord,
  type DivergenceSeverity,
  type LocalConfidenceEventRecord,
} from "../../contracts/autonomous.js";
import {
  appendCalibrationEventRecord,
  appendLocalConfidenceEventRecord,
} from "../../state/jsonl-store.js";
import { createCandidateId, sha256Json } from "../../utils/fs.js";
import {
  isOrderBearingTraceEvent,
  normalizeTraceEventForParity,
} from "../../automation/local-backtest/trace-artifact.js";

const LOW_DIVERGENCE_BONUS = 0.05;
const MEDIUM_DIVERGENCE_PENALTY = 0.04;
const HIGH_DIVERGENCE_PENALTY = 0.1;
const CONFIDENCE_WINDOW = 3;
const STRUCTURE_STOP_WORDS = new Set([
  "a",
  "all",
  "an",
  "and",
  "any",
  "are",
  "as",
  "at",
  "be",
  "by",
  "can",
  "for",
  "from",
  "if",
  "in",
  "into",
  "is",
  "it",
  "its",
  "new",
  "no",
  "of",
  "on",
  "or",
  "path",
  "remain",
  "remains",
  "same",
  "so",
  "that",
  "the",
  "their",
  "them",
  "through",
  "to",
  "under",
  "using",
  "when",
  "while",
  "with",
]);

export interface LocalConfidenceSignal {
  structureFamilyHash: string | null;
  currentConfidence: number | null;
  localConfidenceBonus: number;
  divergencePenalty: number;
  divergenceSeverity: DivergenceSeverity | null;
  recentEventCount: number;
}

export interface LocalConfidenceSummary {
  generatedAt: string;
  totalUpdates: number;
  familyCount: number;
  recentCalibrationSummary: string;
  highDivergenceFamilies: string[];
  lowDivergenceFamilies: string[];
  confidenceAdjustmentSummary: string;
  calibrationAwareInstruction: string;
  families: Array<{
    structureFamilyHash: string;
    currentConfidence: number;
    localConfidenceBonus: number;
    divergencePenalty: number;
    divergenceSeverity: DivergenceSeverity;
    recentEventCount: number;
    candidateId: string;
    sourceCalibrationEventId: string | null;
    recordedAt: string | null;
  }>;
}

export function buildLocalTvParity(input: {
  localMetrics: BacktestMetrics | null | undefined;
  tvMetrics: BacktestMetrics | null | undefined;
  localTrades?: TradeRecord[] | null;
  tvTrades?: TradeRecord[] | null;
  localEventTrace?: Array<Record<string, unknown>> | null;
  tvEventTrace?: Array<Record<string, unknown>> | null;
}) {
  if (!input.localMetrics || !input.tvMetrics) {
    return localTvParitySummarySchema.parse({
      status: "not_comparable",
      tradeCountDelta: null,
      netProfitPctDelta: null,
      maxDrawdownPctDelta: null,
      profitFactorDelta: null,
      winRateDelta: null,
      tradeParity: buildTradeParity(input.localTrades, input.tvTrades),
      eventParity: buildEventParity(input.localEventTrace, input.tvEventTrace),
    });
  }

  const tradeCountDelta = input.tvMetrics.totalTrades - input.localMetrics.totalTrades;
  const netProfitPctDelta =
    input.tvMetrics.postFeeNetProfitPercent -
    input.localMetrics.postFeeNetProfitPercent;
  const maxDrawdownPctDelta =
    input.tvMetrics.maxStrategyDrawdownPercent -
    input.localMetrics.maxStrategyDrawdownPercent;
  const profitFactorDelta =
    input.tvMetrics.profitFactor - input.localMetrics.profitFactor;
  const winRateDelta =
    input.tvMetrics.percentProfitable - input.localMetrics.percentProfitable;
  const metricStatus: "matched" | "minor_drift" | "major_drift" =
    Math.abs(netProfitPctDelta) <= 2 &&
    Math.abs(maxDrawdownPctDelta) <= 2 &&
    Math.abs(tradeCountDelta) <= 1
      ? "matched"
      : Math.abs(netProfitPctDelta) <= 6 &&
          Math.abs(maxDrawdownPctDelta) <= 5 &&
          Math.abs(tradeCountDelta) <= 25
        ? "minor_drift"
        : "major_drift";
  const tradeParity = buildTradeParity(input.localTrades, input.tvTrades);
  const eventParity = buildEventParity(input.localEventTrace, input.tvEventTrace);
  const status = worstParityStatus([
    metricStatus,
    (tradeParity?.status ?? "not_comparable") as
      | "matched"
      | "minor_drift"
      | "major_drift"
      | "not_comparable",
    (eventParity?.status ?? "not_comparable") as
      | "matched"
      | "minor_drift"
      | "major_drift"
      | "not_comparable",
  ]);

  return localTvParitySummarySchema.parse({
    status,
    tradeCountDelta,
    netProfitPctDelta,
    maxDrawdownPctDelta,
    profitFactorDelta,
    winRateDelta,
    tradeParity,
    eventParity,
  });
}

function buildTradeParity(
  localTrades: TradeRecord[] | null | undefined,
  tvTrades: TradeRecord[] | null | undefined,
) {
  if (!localTrades?.length || !tvTrades?.length) {
    return {
      status: "not_comparable" as const,
      entryTimeMatchRatio: null,
      exitTimeMatchRatio: null,
      profitSignMatchRatio: null,
      orderCountDelta: tvTrades?.length != null && localTrades?.length != null
        ? tvTrades.length - localTrades.length
        : null,
    };
  }

  const comparableCount = Math.min(localTrades.length, tvTrades.length);
  let entryMatches = 0;
  let exitMatches = 0;
  let profitSignMatches = 0;
  for (let index = 0; index < comparableCount; index += 1) {
    const localTrade = localTrades[index];
    const tvTrade = tvTrades[index];
    if (normalizeTime(localTrade.entryTime) === normalizeTime(tvTrade.entryTime)) {
      entryMatches += 1;
    }
    if (normalizeTime(localTrade.exitTime) === normalizeTime(tvTrade.exitTime)) {
      exitMatches += 1;
    }
    if (Math.sign(localTrade.profitValue ?? 0) === Math.sign(tvTrade.profitValue ?? 0)) {
      profitSignMatches += 1;
    }
  }

  const entryTimeMatchRatio = entryMatches / comparableCount;
  const exitTimeMatchRatio = exitMatches / comparableCount;
  const profitSignMatchRatio = profitSignMatches / comparableCount;
  const orderCountDelta = tvTrades.length - localTrades.length;
  const status =
    Math.abs(orderCountDelta) <= 1 &&
    entryTimeMatchRatio >= 0.95 &&
    exitTimeMatchRatio >= 0.95 &&
    profitSignMatchRatio >= 0.95
      ? "matched"
      : Math.abs(orderCountDelta) <= 3 &&
          entryTimeMatchRatio >= 0.8 &&
          exitTimeMatchRatio >= 0.8 &&
          profitSignMatchRatio >= 0.8
        ? "minor_drift"
        : "major_drift";

  return {
    status,
    entryTimeMatchRatio: roundRatio(entryTimeMatchRatio),
    exitTimeMatchRatio: roundRatio(exitTimeMatchRatio),
    profitSignMatchRatio: roundRatio(profitSignMatchRatio),
    orderCountDelta,
  };
}

function buildEventParity(
  localEventTrace: Array<Record<string, unknown>> | null | undefined,
  tvEventTrace: Array<Record<string, unknown>> | null | undefined,
) {
  const localEvents = normalizeOrderBearingTrace(localEventTrace);
  const tvEvents = normalizeOrderBearingTrace(tvEventTrace);
  if (!localEvents.length || !tvEvents.length) {
    return {
      status: "not_comparable" as const,
      eventMatchRatio: null,
      entryPassMatchRatio: null,
      exitReasonMatchRatio: null,
    };
  }

  const comparableCount = Math.min(localEvents.length, tvEvents.length);
  let eventMatches = 0;
  let entryPassMatches = 0;
  let exitReasonMatches = 0;
  for (let index = 0; index < comparableCount; index += 1) {
    const localEvent = localEvents[index];
    const tvEvent = tvEvents[index];
    if (
      localEvent.finalBullEvent === tvEvent.finalBullEvent &&
      localEvent.finalBearEvent === tvEvent.finalBearEvent
    ) {
      eventMatches += 1;
    }
    if (localEvent.entryPass === tvEvent.entryPass) {
      entryPassMatches += 1;
    }
    if (localEvent.exitReason === tvEvent.exitReason) {
      exitReasonMatches += 1;
    }
  }

  const eventMatchRatio = eventMatches / comparableCount;
  const entryPassMatchRatio = entryPassMatches / comparableCount;
  const exitReasonMatchRatio = exitReasonMatches / comparableCount;
  const status =
    eventMatchRatio >= 0.95 &&
    entryPassMatchRatio >= 0.95 &&
    exitReasonMatchRatio >= 0.95
      ? "matched"
      : eventMatchRatio >= 0.8 && entryPassMatchRatio >= 0.8
        ? "minor_drift"
        : "major_drift";

  return {
    status,
    eventMatchRatio: roundRatio(eventMatchRatio),
    entryPassMatchRatio: roundRatio(entryPassMatchRatio),
    exitReasonMatchRatio: roundRatio(exitReasonMatchRatio),
  };
}

function normalizeOrderBearingTrace(
  trace: Array<Record<string, unknown>> | null | undefined,
) {
  const normalized =
    trace
      ?.map((entry) => normalizeTraceEventForParity(entry))
      .filter((entry): entry is TraceEventV1 => entry != null) ?? [];
  return normalized.filter(isOrderBearingTraceEvent);
}

function worstParityStatus(
  statuses: Array<"matched" | "minor_drift" | "major_drift" | "not_comparable">,
): "matched" | "minor_drift" | "major_drift" | "not_comparable" {
  if (statuses.includes("major_drift")) {
    return "major_drift";
  }
  if (statuses.includes("not_comparable")) {
    return "not_comparable";
  }
  if (statuses.includes("minor_drift")) {
    return "minor_drift";
  }
  return "matched";
}

function normalizeTime(value: string | null | undefined): string | null {
  return value?.trim() || null;
}

function roundRatio(value: number): number {
  return Math.round(value * 10_000) / 10_000;
}

export function resolveStructureFamilyHash(input: {
  noveltyFingerprint?:
    | { fingerprintFamily?: string | null; structureSignature?: string | null; tokens?: string[] }
    | null
    | undefined;
  candidateId?: string | null;
  conditionInventory?:
    | Array<{ conditionId?: string | null; role?: string | null; summary?: string | null }>
    | null
    | undefined;
}): string | null {
  const normalizedInventory = normalizeStructureInventory(input.conditionInventory);
  const modeTokens = normalizeStructureModeTokens(input.noveltyFingerprint?.tokens ?? []);
  if (normalizedInventory.length > 0 || modeTokens.length > 0) {
    return sha256Json({
      normalizedInventory,
      modeTokens,
    });
  }

  const fingerprintFamily = input.noveltyFingerprint?.fingerprintFamily;
  if (fingerprintFamily && fingerprintFamily.trim().length > 0) {
    return fingerprintFamily;
  }

  const structureSignature = input.noveltyFingerprint?.structureSignature;
  const tokens =
    input.noveltyFingerprint?.tokens?.filter(
      (value): value is string => typeof value === "string" && value.trim().length > 0,
    ) ?? [];
  if (
    !structureSignature &&
    tokens.length === 0 &&
    normalizedInventory.length === 0 &&
    !input.candidateId
  ) {
    return null;
  }

  return sha256Json({
    structureSignature: structureSignature ?? null,
    tokens,
    normalizedInventory,
    candidateId: input.candidateId ?? null,
  });
}

export function resolveLocalConfidenceSignal(input: {
  confidenceEvents: LocalConfidenceEventRecord[];
  structureFamilyHash: string | null;
}): LocalConfidenceSignal {
  if (!input.structureFamilyHash) {
    return {
      structureFamilyHash: null,
      currentConfidence: null,
      localConfidenceBonus: 0,
      divergencePenalty: 0,
      divergenceSeverity: null,
      recentEventCount: 0,
    };
  }

  const matching = input.confidenceEvents
    .filter((event) => event.structureFamilyHash === input.structureFamilyHash)
    .sort(compareRecordedAtAscending);
  const latest = matching.at(-1);
  if (!latest) {
    return {
      structureFamilyHash: input.structureFamilyHash,
      currentConfidence: null,
      localConfidenceBonus: 0,
      divergencePenalty: 0,
      divergenceSeverity: null,
      recentEventCount: 0,
    };
  }

  return {
    structureFamilyHash: input.structureFamilyHash,
    currentConfidence: latest.nextConfidence,
    localConfidenceBonus: latest.localConfidenceBonus,
    divergencePenalty: latest.divergencePenalty,
    divergenceSeverity: latest.divergenceSeverity,
    recentEventCount: matching.slice(-CONFIDENCE_WINDOW).length,
  };
}

export function buildLocalConfidenceSummary(
  events: LocalConfidenceEventRecord[],
): LocalConfidenceSummary {
  const latestByFamily = new Map<string, LocalConfidenceEventRecord>();
  for (const event of [...events].sort(compareRecordedAtAscending)) {
    latestByFamily.set(event.structureFamilyHash, event);
  }

  const families = [...latestByFamily.values()]
    .sort(compareRecordedAtDescending)
    .map((event) => ({
      structureFamilyHash: event.structureFamilyHash,
      currentConfidence: event.nextConfidence,
      localConfidenceBonus: event.localConfidenceBonus,
      divergencePenalty: event.divergencePenalty,
      divergenceSeverity: event.divergenceSeverity,
      recentEventCount: events.filter(
        (candidate) => candidate.structureFamilyHash === event.structureFamilyHash,
      ).length,
      candidateId: event.candidateId,
      sourceCalibrationEventId: event.sourceCalibrationEventId,
      recordedAt: event.recordedAt ?? null,
    }));

  const highDivergenceFamilies = families
    .filter((entry) => entry.divergenceSeverity === "high")
    .map((entry) => entry.structureFamilyHash)
    .slice(0, 5);
  const lowDivergenceFamilies = families
    .filter((entry) => entry.localConfidenceBonus > 0)
    .map((entry) => entry.structureFamilyHash)
    .slice(0, 5);
  const recentCalibrationSummary =
    events.length === 0
      ? "No external calibration history remains. Use neutral local confidence and keep local-first exploration running."
      : `Calibration history is active across ${latestByFamily.size} structure families and ${events.length} confidence updates.`;
  const confidenceAdjustmentSummary =
    events.length === 0
      ? "No confidence adjustments are active yet."
      : `Positive local confidence is active for ${lowDivergenceFamilies.length} families; divergence penalties are active for ${highDivergenceFamilies.length} families with repeated drift.`;
  const calibrationAwareInstruction =
    events.length === 0
      ? "Use neutral calibration guidance. Do not block local-first exploration while calibration history is empty."
      : [
          lowDivergenceFamilies.length > 0
            ? `Prefer low-divergence families first: ${lowDivergenceFamilies.join(", ")}.`
            : "No low-divergence family is currently preferred.",
          highDivergenceFamilies.length > 0
            ? `Be cautious with high-divergence families: ${highDivergenceFamilies.join(", ")}.`
            : "No high-divergence family is currently penalized.",
        ].join(" ");

  return {
    generatedAt: new Date().toISOString(),
    totalUpdates: events.length,
    familyCount: latestByFamily.size,
    recentCalibrationSummary,
    highDivergenceFamilies,
    lowDivergenceFamilies,
    confidenceAdjustmentSummary,
    calibrationAwareInstruction,
    families,
  };
}

export async function appendDivergenceEvent(input: {
  stateRoot: string;
  runId: string;
  iteration: number;
  localRecord: AutonomousExperimentRecord;
  tvRecord: AutonomousExperimentRecord;
  localConfidenceAfter: number;
}): Promise<CalibrationEventRecord> {
  return appendCalibrationEventRecord(input.stateRoot, {
    calibrationEventId: createCandidateId("calibration"),
    runId: input.runId,
    iteration: input.iteration,
    eventKind: "local_tv_divergence_measured",
    candidateId: input.localRecord.candidateId,
    structureFamilyHash: resolveStructureFamilyHash({
      noveltyFingerprint: input.localRecord.noveltyFingerprint,
      candidateId: input.localRecord.candidateId,
      conditionInventory: input.localRecord.conditionInventory,
    }),
    fingerprintFamily:
      input.localRecord.noveltyFingerprint?.fingerprintFamily ?? null,
    queueState: "processed",
    queueReason: "tv_calibration_completed",
    tvHealthAtQueueTime: "healthy",
    localConfidenceBefore: input.localRecord.localConfidence,
    localConfidenceAfter: input.localConfidenceAfter,
    parity: input.tvRecord.localTvParity,
    tvDecision: input.tvRecord.decision,
  });
}

export async function appendLocalConfidenceUpdate(input: {
  stateRoot: string;
  runId: string;
  iteration: number;
  candidateId: string;
  structureFamilyHash: string | null;
  sourceCalibrationEventId: string | null;
  parityStatus:
    | "matched"
    | "minor_drift"
    | "major_drift"
    | "not_comparable"
    | null
    | undefined;
  previousConfidenceEvents: LocalConfidenceEventRecord[];
}): Promise<LocalConfidenceEventRecord | null> {
  if (!input.structureFamilyHash || !input.parityStatus || input.parityStatus === "not_comparable") {
    return null;
  }

  const familyHistory = input.previousConfidenceEvents
    .filter((event) => event.structureFamilyHash === input.structureFamilyHash)
    .sort(compareRecordedAtAscending);
  const previousConfidence =
    familyHistory.at(-1)?.nextConfidence ?? 1;
  const currentSeverity = mapParityStatusToSeverity(input.parityStatus);
  const window = [
    ...familyHistory.slice(-(CONFIDENCE_WINDOW - 1)).map((event) => event.divergenceSeverity),
    currentSeverity,
  ];
  const aggregateSeverity = classifyAggregateSeverity(window);
  const nextConfidence = roundConfidence(
    average(window.map(mapSeverityToConfidenceScore)),
  );
  const localConfidenceBonus =
    aggregateSeverity === "low" ? LOW_DIVERGENCE_BONUS : 0;
  const divergencePenalty =
    aggregateSeverity === "high"
      ? HIGH_DIVERGENCE_PENALTY
      : aggregateSeverity === "medium"
        ? MEDIUM_DIVERGENCE_PENALTY
        : 0;

  return appendLocalConfidenceEventRecord(input.stateRoot, {
    confidenceEventId: createCandidateId("confidence"),
    runId: input.runId,
    iteration: input.iteration,
    eventKind: "local_confidence_updated",
    candidateId: input.candidateId,
    sourceCalibrationEventId: input.sourceCalibrationEventId,
    structureFamilyHash: input.structureFamilyHash,
    divergenceSeverity: aggregateSeverity,
    previousConfidence,
    nextConfidence,
    localConfidenceBonus,
    divergencePenalty,
    reason: buildConfidenceReason(window, aggregateSeverity),
  });
}

function mapParityStatusToSeverity(
  status: "matched" | "minor_drift" | "major_drift",
): DivergenceSeverity {
  switch (status) {
    case "matched":
      return "low";
    case "minor_drift":
      return "medium";
    default:
      return "high";
  }
}

function mapSeverityToConfidenceScore(severity: DivergenceSeverity): number {
  switch (severity) {
    case "low":
      return 1;
    case "medium":
      return 0.76;
    case "high":
      return 0.5;
  }
}

function classifyAggregateSeverity(
  severities: DivergenceSeverity[],
): DivergenceSeverity {
  if (severities.includes("high")) {
    return "high";
  }
  if (severities.includes("medium")) {
    return "medium";
  }
  return "low";
}

function buildConfidenceReason(
  severities: DivergenceSeverity[],
  aggregateSeverity: DivergenceSeverity,
): string {
  const windowSummary = severities.join(", ");
  if (aggregateSeverity === "low") {
    return `Recent calibration window remained low divergence (${windowSummary}), so local confidence bonus was enabled.`;
  }
  if (aggregateSeverity === "medium") {
    return `Recent calibration window contains medium divergence (${windowSummary}), so a mild divergence penalty was applied.`;
  }
  return `Recent calibration window contains high divergence (${windowSummary}), so a strong divergence penalty was applied.`;
}

function compareRecordedAtAscending(
  left: { recordedAt?: string | null },
  right: { recordedAt?: string | null },
): number {
  return normalizeRecordedAt(left.recordedAt) - normalizeRecordedAt(right.recordedAt);
}

function compareRecordedAtDescending(
  left: { recordedAt?: string | null },
  right: { recordedAt?: string | null },
): number {
  return normalizeRecordedAt(right.recordedAt) - normalizeRecordedAt(left.recordedAt);
}

function normalizeStructureInventory(
  conditionInventory:
    | Array<{ conditionId?: string | null; role?: string | null; summary?: string | null }>
    | null
    | undefined,
): string[] {
  return (conditionInventory ?? [])
    .map((entry) => {
      const role =
        typeof entry.role === "string" && entry.role.trim().length > 0
          ? entry.role.trim().toLowerCase()
          : "unknown";
      const descriptor = normalizeStructureDescriptor(entry);
      return descriptor ? `${role}:${descriptor}` : null;
    })
    .filter((value): value is string => value != null)
    .sort();
}

function normalizeStructureModeTokens(tokens: string[]): string[] {
  return tokens
    .filter((token) =>
      token.startsWith("trendMode:") ||
      token.startsWith("sameBarConflictMode:") ||
      token.startsWith("replacement:") ||
      token.startsWith("supertrend:") ||
      token.startsWith("weak_exit:") ||
      token.startsWith("counter_trend:") ||
      token.startsWith("riskoff_close_all:") ||
      token.startsWith("b1_filter:"),
    )
    .map((token) => token.trim().toLowerCase())
    .filter((value, index, array) => array.indexOf(value) === index)
    .sort();
}

function normalizeStructureDescriptor(entry: {
  conditionId?: string | null;
  role?: string | null;
  summary?: string | null;
}): string {
  const normalizedText = normalizeStructureText(
    `${entry.conditionId ?? ""} ${entry.summary ?? ""}`,
  );
  const role =
    typeof entry.role === "string" && entry.role.trim().length > 0
      ? entry.role.trim().toLowerCase()
      : "unknown";
  const archetype = resolveStructureArchetype(role, normalizedText);
  if (archetype) {
    return archetype;
  }

  const keywords = normalizedText
    .split(/\s+/)
    .map((token) => token.trim())
    .filter(
      (token) =>
        token.length >= 3 &&
        !STRUCTURE_STOP_WORDS.has(token) &&
        !/^\d+$/.test(token),
    );
  const uniqueKeywords = [...new Set(keywords)].sort().slice(0, 8);
  if (uniqueKeywords.length > 0) {
    return uniqueKeywords.join("_");
  }

  const normalizedConditionId = normalizeStructureText(entry.conditionId ?? "")
    .split(/\s+/)
    .filter((token) => token.length >= 3)
    .slice(0, 6)
    .join("_");
  return normalizedConditionId || "generic";
}

function resolveStructureArchetype(role: string, normalizedText: string): string | null {
  if (role === "entry") {
    if (
      normalizedText.includes("bull") &&
      (normalizedText.includes("exhaustion") || normalizedText.includes("bullrank"))
    ) {
      return "bull_exhaustion_primary";
    }
    if (
      normalizedText.includes("riskoff") &&
      (normalizedText.includes("reduced") ||
        normalizedText.includes("block") ||
        normalizedText.includes("allow") ||
        normalizedText.includes("bypass") ||
        normalizedText.includes("retention") ||
        normalizedText.includes("density"))
    ) {
      return "riskoff_entry_relaxed";
    }
    if (
      normalizedText.includes("extension") &&
      (normalizedText.includes("bullrank") || normalizedText.includes("weak"))
    ) {
      return "bull_extension_reduced";
    }
    if (normalizedText.includes("confirm")) {
      return "entry_confirmation_relaxed";
    }
    if (normalizedText.includes("samebar") || normalizedText.includes("conflict")) {
      return "samebar_conflict_adjusted";
    }
  }

  if (role === "exit") {
    if (normalizedText.includes("weakrange")) {
      return "weakrange_exit";
    }
    if (normalizedText.includes("staged") && normalizedText.includes("bear")) {
      return "staged_bear_exit";
    }
  }

  if (normalizedText.includes("slot")) {
    return `${role}_slot_management`;
  }

  return null;
}

function normalizeStructureText(value: string): string {
  return value
    .toLowerCase()
    .replace(/\brisk[\s-]*off\b/g, "riskoff")
    .replace(/\bsame[\s-]*bar\b/g, "samebar")
    .replace(/\bstrong[\s-]*wins\b/g, "strongwins")
    .replace(/\b(b1|b2|b3|bconf)\b/g, "bullrank")
    .replace(/\b(s1|s2|s3|sconf)\b/g, "bearrank")
    .replace(/\bbullish\b/g, "bull")
    .replace(/\bbearish\b/g, "bear")
    .replace(/\bentries\b/g, "entry")
    .replace(/\bexits\b/g, "exit")
    .replace(/\bconfirmation(s)?\b/g, "confirm")
    .replace(/\boverextension\b/g, "extension")
    .replace(/\bweak[\s-]*range\b/g, "weakrange")
    .replace(
      /\b(loosen|loosened|relax|relaxed|remove|removed|bypass|bypassed|neutralized|disabled)\b/g,
      "reduced",
    )
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function normalizeRecordedAt(value: string | null | undefined): number {
  const parsed = Date.parse(value ?? "");
  return Number.isFinite(parsed) ? parsed : 0;
}

function average(values: number[]): number {
  if (values.length === 0) {
    return 1;
  }
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function roundConfidence(value: number): number {
  return Math.round(Math.max(0, Math.min(1, value)) * 10_000) / 10_000;
}
