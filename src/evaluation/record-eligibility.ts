import { existsSync } from "node:fs";

import {
  type ExperimentArtifactPaths,
  type ExperimentRecord,
  type MutationProvenance,
  type RecordEra,
} from "../contracts/types.js";

export const CURRENT_MUTATION_RESPONSE_SCHEMA_VERSION =
  "parsed-mutation-response/v1";

export type EligibilitySeverity = "error" | "warning";

export interface EligibilityIssue {
  code: string;
  message: string;
  severity: EligibilitySeverity;
}

export interface EligibilityResult {
  ok: boolean;
  issues: EligibilityIssue[];
}

export interface EligibilityContext {
  experimentsByCandidateId: Map<string, ExperimentRecord[]>;
}

export type InvalidRecordClassification =
  | "invalid_verified_view"
  | "invalid_promotion"
  | "invalid_promoted_head"
  | "invalid_artifact"
  | "invalid_provenance"
  | "invalid_executor"
  | "invalid_fallback"
  | "invalid_legacy_mix";

export interface InvalidRecordViewEntry {
  candidateId: string;
  iteration: number | null;
  decision: string;
  classification: InvalidRecordClassification;
  messages: string[];
}

type RecordMetaLike = {
  schemaVersion?: string | null;
  artifactBundleHash?: string | null;
  promotedFromRunId?: string | null;
  promotedFromIteration?: number | null;
  promotedFromRecordHash?: string | null;
};

type EvidenceLike = Pick<
  ExperimentRecord,
  | "candidatePath"
  | "candidateHash"
  | "artifactPaths"
  | "artifactBundle"
  | "artifactBundleHash"
  | "artifactSummary"
  | "recordMeta"
>;

const VERIFIED_VIEW_DECISIONS = new Set(["verified_improvement", "promoted_head"]);

const buildResult = (issues: EligibilityIssue[]): EligibilityResult => ({
  ok: issues.every((issue) => issue.severity !== "error"),
  issues,
});

const pushIssue = (
  issues: EligibilityIssue[],
  code: string,
  message: string,
  severity: EligibilitySeverity = "error",
): void => {
  issues.push({ code, message, severity });
};

export function resolveRecordEra(record: {
  decision: string;
  recordEra?: RecordEra;
  recordMeta?: { schemaVersion?: string | null } | null;
}): RecordEra {
  if (record.recordEra) {
    return record.recordEra;
  }
  if (record.recordMeta?.schemaVersion?.endsWith("/v2")) {
    return "v2";
  }
  if (record.recordMeta?.schemaVersion?.endsWith("/v3")) {
    return "v3";
  }
  if (record.recordMeta?.schemaVersion?.endsWith("/v4")) {
    return "v3";
  }
  if (record.decision.startsWith("accepted_")) {
    return "legacy";
  }
  return "v2";
}

export function collectPromotionEvidenceIssueDetails(
  record: EvidenceLike,
): EligibilityIssue[] {
  const issues: EligibilityIssue[] = [];

  if (!record.candidatePath) {
    pushIssue(issues, "candidate_path_missing", "Candidate source path is missing.");
  } else if (!existsSync(record.candidatePath)) {
    pushIssue(issues, "candidate_file_missing", "Candidate source file is missing.");
  }

  if (!record.candidateHash) {
    pushIssue(issues, "candidate_hash_missing", "Candidate source hash is missing.");
  }

  if (!(record.recordMeta?.artifactBundleHash ?? record.artifactBundleHash)) {
    pushIssue(
      issues,
      "artifact_bundle_hash_missing",
      "artifactBundleHash is missing from recordMeta or experiment record.",
    );
  }

  if (!(record.artifactBundle?.rawReportHash ?? record.artifactSummary?.rawReportHash)) {
    pushIssue(
      issues,
      "raw_report_hash_missing",
      "TradingView raw report hash is missing from artifactBundle or artifactSummary.",
    );
  }

  if (!record.artifactPaths?.backtestArtifact) {
    pushIssue(
      issues,
      "backtest_artifact_path_missing",
      "Primary backtest artifact path is missing.",
    );
  }

  for (const [artifactKey, artifactPath] of artifactPathEntries(record.artifactPaths)) {
    if (!existsSync(artifactPath)) {
      pushIssue(
        issues,
        "artifact_file_missing",
        `Artifact path "${artifactKey}" is missing.`,
      );
    }
  }

  return issues;
}

function artifactPathEntries(
  artifactPaths?: ExperimentArtifactPaths,
): Array<[string, string]> {
  return Object.entries(artifactPaths ?? {}).filter(
    (entry): entry is [string, string] => typeof entry[1] === "string",
  );
}

export function collectPromotionEvidenceIssues(record: EvidenceLike): string[] {
  return collectPromotionEvidenceIssueDetails(record).map((issue) => issue.message);
}

function collectPromotionProvenanceIssueDetails(
  mutationProvenance?: MutationProvenance | null,
): EligibilityIssue[] {
  const issues: EligibilityIssue[] = [];

  if (!mutationProvenance) {
    pushIssue(
      issues,
      "mutation_provenance_missing",
      "mutationProvenance is missing.",
    );
    return issues;
  }

  if (mutationProvenance.parseStatus !== "valid") {
    pushIssue(
      issues,
      "mutation_provenance_parse_status",
      "mutationProvenance.parseStatus must be valid for promotion.",
    );
  }
  if (mutationProvenance.inventorySource !== "llm") {
    pushIssue(
      issues,
      "mutation_provenance_inventory_source",
      "mutationProvenance.inventorySource must be llm for promotion.",
    );
  }
  if (!mutationProvenance.briefHash) {
    pushIssue(
      issues,
      "mutation_provenance_brief_hash_missing",
      "mutationProvenance.briefHash is missing.",
    );
  }
  if (!mutationProvenance.promptHash) {
    pushIssue(
      issues,
      "mutation_provenance_prompt_hash_missing",
      "mutationProvenance.promptHash is missing.",
    );
  }
  if (!mutationProvenance.responseHash) {
    pushIssue(
      issues,
      "mutation_provenance_response_hash_missing",
      "mutationProvenance.responseHash is missing.",
    );
  }
  if (
    mutationProvenance.responseSchemaVersion !==
    CURRENT_MUTATION_RESPONSE_SCHEMA_VERSION
  ) {
    pushIssue(
      issues,
      "mutation_provenance_response_schema_version",
      `mutationProvenance.responseSchemaVersion must match ${CURRENT_MUTATION_RESPONSE_SCHEMA_VERSION} for promotion.`,
    );
  }
  if (mutationProvenance.inferredFields.length > 0) {
    pushIssue(
      issues,
      "mutation_provenance_inferred_fields",
      "mutationProvenance.inferredFields must be empty for promotion.",
    );
  }
  if (mutationProvenance.missingFields.length > 0) {
    pushIssue(
      issues,
      "mutation_provenance_missing_fields",
      "mutationProvenance.missingFields must be empty for promotion.",
    );
  }

  return issues;
}

export function collectPromotionProvenanceIssues(
  mutationProvenance?: MutationProvenance | null,
): string[] {
  return collectPromotionProvenanceIssueDetails(mutationProvenance).map(
    (issue) => issue.message,
  );
}

export function buildEligibilityContext(
  records: ExperimentRecord[],
): EligibilityContext {
  const experimentsByCandidateId = new Map<string, ExperimentRecord[]>();
  for (const record of records) {
    const current = experimentsByCandidateId.get(record.candidateId) ?? [];
    current.push(record);
    experimentsByCandidateId.set(record.candidateId, current);
  }

  return { experimentsByCandidateId };
}

export function claimsVerifiedView(record: ExperimentRecord): boolean {
  return (
    VERIFIED_VIEW_DECISIONS.has(record.decision) ||
    record.verificationStatus === "verified" ||
    record.promotionStatus === "verified_improvement" ||
    record.promotionStatus === "promoted_head"
  );
}

export function claimsPromotion(record: ExperimentRecord): boolean {
  return (
    record.promotionReady === true ||
    record.decision === "promoted_head" ||
    record.promotionStatus === "promoted_head"
  );
}

export function claimsPromotedHead(record: ExperimentRecord): boolean {
  return (
    record.decision === "promoted_head" ||
    record.promotionStatus === "promoted_head"
  );
}

export function evaluateVerifiedViewEligibility(
  record: ExperimentRecord,
): EligibilityResult {
  const issues: EligibilityIssue[] = [];

  if (resolveRecordEra(record) === "legacy") {
    pushIssue(
      issues,
      "legacy_record",
      "Legacy accepted records cannot satisfy the current verified-view contract.",
    );
  }
  if (!VERIFIED_VIEW_DECISIONS.has(record.decision)) {
    pushIssue(
      issues,
      "verified_view_decision",
      "Verified-view records must have decision=verified_improvement or decision=promoted_head.",
    );
  }
  if (record.verificationStatus !== "verified") {
    pushIssue(
      issues,
      "verification_status_invalid",
      "Candidate has not completed authoritative verification successfully.",
    );
  }
  if (record.fallbackEvaluation != null) {
    pushIssue(
      issues,
      "fallback_record",
      "Fallback evidence records cannot satisfy the verified-view contract.",
    );
  }
  if (
    !record.executorCapability?.authoritative ||
    record.executorCapability.kind !== "tradingview-live"
  ) {
    pushIssue(
      issues,
      "non_authoritative_executor",
      "Non-authoritative or local screening records cannot satisfy the verified-view contract.",
    );
  }
  if (!record.artifactValidation?.verificationReady) {
    pushIssue(
      issues,
      "verification_artifact_incomplete",
      "Artifact completeness is insufficient for verified-view inclusion.",
    );
  }
  if (record.verificationFailureReason != null) {
    pushIssue(
      issues,
      "verification_failure_reason_present",
      "Verification records with failure reasons cannot satisfy the verified-view contract.",
    );
  }
  if (record.verificationRuntimeFailureKind != null) {
    pushIssue(
      issues,
      "verification_runtime_failure_present",
      "Verification runtime failure records cannot satisfy the verified-view contract.",
    );
  }
  if (record.mutationParseStatus !== "valid") {
    pushIssue(
      issues,
      "mutation_parse_status_invalid",
      "mutationParseStatus must be valid for verified-view inclusion.",
    );
  }

  issues.push(...collectPromotionEvidenceIssueDetails(record));
  issues.push(...collectPromotionProvenanceIssueDetails(record.mutationProvenance));

  return buildResult(issues);
}

export function evaluatePromotionEligibility(
  record: ExperimentRecord,
): EligibilityResult {
  const issues = [...evaluateVerifiedViewEligibility(record).issues];

  if (record.decision !== "verified_improvement") {
    pushIssue(
      issues,
      "promotion_decision_invalid",
      "Only authoritative verified_improvement records can be promoted.",
    );
  }
  if (!record.promotionReady) {
    pushIssue(
      issues,
      "promotion_ready_false",
      "Candidate is verified but not promotion-ready. Re-run verification after improving TradingView artifact completeness.",
    );
  }
  if (!record.artifactValidation?.promotionReady) {
    pushIssue(
      issues,
      "promotion_artifact_incomplete",
      "Artifact completeness is insufficient for promotion.",
    );
  }

  return buildResult(issues);
}

export function evaluatePromotedHeadEligibility(
  record: ExperimentRecord,
  context: EligibilityContext,
): EligibilityResult {
  const issues = [...evaluateVerifiedViewEligibility(record).issues];

  if (record.decision !== "promoted_head") {
    pushIssue(
      issues,
      "promoted_head_decision_invalid",
      "promoted_head eligibility requires decision=promoted_head.",
    );
  }
  if (record.promotionStatus !== "promoted_head") {
    pushIssue(
      issues,
      "promoted_head_status_invalid",
      "promoted_head eligibility requires promotionStatus=promoted_head.",
    );
  }
  if (!record.promotionReady) {
    pushIssue(
      issues,
      "promotion_ready_false",
      "Candidate is verified but not promotion-ready. Re-run verification after improving TradingView artifact completeness.",
    );
  }
  if (!record.artifactValidation?.promotionReady) {
    pushIssue(
      issues,
      "promotion_artifact_incomplete",
      "Artifact completeness is insufficient for promotion.",
    );
  }

  const linkageMeta = (record.recordMeta ?? {}) as RecordMetaLike;
  if (
    !linkageMeta.promotedFromRunId ||
    linkageMeta.promotedFromIteration == null ||
    !linkageMeta.promotedFromRecordHash
  ) {
    pushIssue(
      issues,
      "promoted_head_linkage_missing",
      "promoted_head record is missing promotedFromRunId/promotedFromIteration/promotedFromRecordHash linkage.",
    );
    return buildResult(issues);
  }

  const candidateRecords = context.experimentsByCandidateId.get(record.candidateId) ?? [];
  const sourceRecord =
    candidateRecords.find(
      (candidateRecord) =>
        candidateRecord.runId === linkageMeta.promotedFromRunId &&
        candidateRecord.iteration === linkageMeta.promotedFromIteration &&
        candidateRecord.recordMeta?.recordHash === linkageMeta.promotedFromRecordHash,
    ) ?? null;

  if (!sourceRecord) {
    pushIssue(
      issues,
      "promoted_head_source_missing",
      "promoted_head record does not reference an existing verified source record.",
    );
    return buildResult(issues);
  }

  if (sourceRecord.decision !== "verified_improvement") {
    pushIssue(
      issues,
      "promoted_head_source_decision_invalid",
      "promoted_head linkage must reference a verified_improvement source record.",
    );
  }

  const sourcePromotion = evaluatePromotionEligibility(sourceRecord);
  for (const issue of sourcePromotion.issues) {
    pushIssue(
      issues,
      "promoted_head_source_invalid",
      `Linked source record is not promotion-eligible: ${issue.message}`,
    );
  }

  const sourceRecordedAt = Date.parse(sourceRecord.recordedAt ?? "");
  const promotedRecordedAt = Date.parse(record.recordedAt ?? "");
  if (
    !Number.isFinite(sourceRecordedAt) ||
    !Number.isFinite(promotedRecordedAt) ||
    sourceRecordedAt >= promotedRecordedAt
  ) {
    pushIssue(
      issues,
      "promoted_head_source_order_invalid",
      "promoted_head record must be recorded after its verified source record.",
    );
  }

  return buildResult(issues);
}

export function assertPromotionEligible(record: ExperimentRecord): void {
  const result = evaluatePromotionEligibility(record);
  if (!result.ok) {
    throw new Error(result.issues[0]?.message ?? "Promotion eligibility failed.");
  }
}

function classifyInvalidRecord(
  record: ExperimentRecord,
  issues: EligibilityIssue[],
): InvalidRecordClassification {
  const codes = new Set(issues.map((issue) => issue.code));

  if (claimsPromotedHead(record)) {
    return "invalid_promoted_head";
  }
  if (codes.has("fallback_record")) {
    return "invalid_fallback";
  }
  if (codes.has("legacy_record")) {
    return "invalid_legacy_mix";
  }
  if (
    codes.has("non_authoritative_executor") ||
    record.executorCapability?.authoritative === false
  ) {
    return "invalid_executor";
  }
  if (
    [...codes].some(
      (code) =>
        code.startsWith("mutation_") ||
        code === "mutation_parse_status_invalid",
    )
  ) {
    return "invalid_provenance";
  }
  if (
    [...codes].some(
      (code) =>
        code.startsWith("candidate_") ||
        code.startsWith("artifact_") ||
        code === "raw_report_hash_missing" ||
        code === "backtest_artifact_path_missing" ||
        code === "verification_artifact_incomplete" ||
        code === "promotion_artifact_incomplete",
    )
  ) {
    return "invalid_artifact";
  }
  if (claimsPromotion(record)) {
    return "invalid_promotion";
  }
  return "invalid_verified_view";
}

export function collectCurrentRecordEligibilityIssues(
  record: ExperimentRecord,
  context: EligibilityContext,
): EligibilityIssue[] {
  if (record.fallbackEvaluation != null || resolveRecordEra(record) !== "v2") {
    return [];
  }
  if (claimsPromotedHead(record)) {
    return evaluatePromotedHeadEligibility(record, context).issues;
  }
  if (claimsPromotion(record)) {
    return evaluatePromotionEligibility(record).issues;
  }
  if (claimsVerifiedView(record)) {
    return evaluateVerifiedViewEligibility(record).issues;
  }
  return [];
}

export function buildInvalidRecordViewEntries(
  records: ExperimentRecord[],
): InvalidRecordViewEntry[] {
  const context = buildEligibilityContext(records);
  const entries: InvalidRecordViewEntry[] = [];

  for (const record of records) {
    if (record.fallbackEvaluation != null || resolveRecordEra(record) !== "v2") {
      continue;
    }

    const issues = collectCurrentRecordEligibilityIssues(record, context).filter(
      (issue) => issue.severity === "error",
    );
    if (issues.length === 0) {
      continue;
    }

    entries.push({
      candidateId: record.candidateId,
      iteration: record.iteration ?? null,
      decision: record.decision,
      classification: classifyInvalidRecord(record, issues),
      messages: issues.map((issue) => issue.message),
    });
  }

  return entries;
}

export function selectVerifiedViewRecords(
  records: ExperimentRecord[],
): ExperimentRecord[] {
  const context = buildEligibilityContext(records);
  return records.filter((record) =>
    claimsPromotedHead(record)
      ? evaluatePromotedHeadEligibility(record, context).ok
      : evaluateVerifiedViewEligibility(record).ok,
  );
}

export function selectPromotionEligibleRecords(
  records: ExperimentRecord[],
): ExperimentRecord[] {
  return records.filter((record) => evaluatePromotionEligibility(record).ok);
}

export function selectPromotedHeadRecords(
  records: ExperimentRecord[],
): ExperimentRecord[] {
  const context = buildEligibilityContext(records);
  return records.filter((record) => evaluatePromotedHeadEligibility(record, context).ok);
}
