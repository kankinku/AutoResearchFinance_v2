import {
  CURRENT_MUTATION_RESPONSE_SCHEMA_VERSION,
  assertPromotionEligible as assertSharedPromotionEligible,
  collectPromotionEvidenceIssues,
  collectPromotionProvenanceIssues,
  resolveRecordEra,
} from "./record-eligibility.js";
import {
  type ArtifactValidationResult,
  type DecisionCode,
  type ExperimentRecord,
  type ExecutorCapability,
  type FallbackEvaluation,
  type MutationProvenance,
  type NormalizedDecisionCategory,
  type ObjectiveBreakdown,
  type PromotionStatus,
  type RecordEra,
  type VerificationFailureReason,
  type VerificationStatus,
} from "../contracts/types.js";
import { isArtifactPromotionReady, isArtifactVerificationReady } from "./artifact-validation.js";

export {
  CURRENT_MUTATION_RESPONSE_SCHEMA_VERSION,
  collectPromotionEvidenceIssues,
  collectPromotionProvenanceIssues,
  resolveRecordEra,
};

export function normalizeDecisionCode(decision: string): DecisionCode | string {
  switch (decision) {
    case "accepted_improvement":
      return "legacy_screening_improvement";
    case "accepted_no_improvement":
      return "legacy_valid_no_promotion";
    default:
      return decision;
  }
}

export function categorizeDecision(decision: string): NormalizedDecisionCategory {
  const normalized = normalizeDecisionCode(decision);
  switch (normalized) {
    case "verified_improvement":
      return "verified";
    case "promoted_head":
      return "promoted";
    case "screening_improvement":
    case "valid_no_promotion":
      return "screening";
    case "legacy_screening_improvement":
      return "legacy_screening_improvement";
    case "legacy_valid_no_promotion":
      return "legacy_valid_no_promotion";
    case "verification_fail":
      return "runtime_failure";
    case "artifact_incomplete":
      return "artifact_failure";
    default:
      return "failure";
  }
}

export function classifyScreeningDecision(
  breakdown: ObjectiveBreakdown,
  acceptedHeadScore: number | null,
): DecisionCode {
  if (!breakdown.hardGatesPassed) {
    return "hard_gate_fail";
  }

  if (breakdown.softGuardrailBreached) {
    return "soft_regress";
  }

  if (acceptedHeadScore === null || breakdown.score > acceptedHeadScore) {
    return "screening_improvement";
  }

  return "valid_no_promotion";
}

export function classifyAuthoritativeDecision(input: {
  breakdown: ObjectiveBreakdown;
  acceptedHeadScore: number | null;
  artifactValidation: ArtifactValidationResult;
}): DecisionCode {
  if (!isArtifactVerificationReady(input.artifactValidation)) {
    return "artifact_incomplete";
  }

  if (!input.breakdown.hardGatesPassed) {
    return "hard_gate_fail";
  }

  if (input.breakdown.softGuardrailBreached) {
    return "soft_regress";
  }

  if (
    input.acceptedHeadScore === null ||
    input.breakdown.score > input.acceptedHeadScore
  ) {
    return "verified_improvement";
  }

  return "valid_no_promotion";
}

export function deriveVerificationStatus(input: {
  decision: DecisionCode;
  executorCapability: ExecutorCapability;
  usedVerificationExecutor: boolean;
}): VerificationStatus {
  if (input.decision === "promoted_head") {
    return "verified";
  }

  if (!input.usedVerificationExecutor && !input.executorCapability.authoritative) {
    return "not_requested";
  }

  if (isAuthoritativeVerifiedDecision(input.decision)) {
    return "verified";
  }

  return "verification_failed";
}

export function derivePromotionStatus(input: {
  decision: DecisionCode;
  executorCapability: ExecutorCapability;
}): PromotionStatus {
  if (input.decision === "promoted_head") {
    return "promoted_head";
  }
  if (input.decision === "verified_improvement") {
    return "verified_improvement";
  }
  if (input.decision === "verification_fail") {
    return "verification_failed";
  }
  if (input.decision === "screening_improvement") {
    return input.executorCapability.authoritative
      ? "verification_pending"
      : "screening_only";
  }
  return "not_promoted";
}

export function deriveVerificationFailureReason(input: {
  decision: DecisionCode;
  screeningDecision?: DecisionCode | null;
  artifactValidation?: ArtifactValidationResult | null;
  hadRuntimeFailure?: boolean;
  wasBacktestEmpty?: boolean;
  usedVerificationExecutor: boolean;
}): VerificationFailureReason {
  if (isAuthoritativeVerifiedDecision(input.decision)) {
    return null;
  }
  if (input.decision === "artifact_incomplete") {
    return "verification_artifact_incomplete";
  }
  if (input.hadRuntimeFailure) {
    return "verification_runtime_failure";
  }
  if (input.wasBacktestEmpty) {
    return "verification_empty_report";
  }
  if (
    input.usedVerificationExecutor &&
    input.screeningDecision === "screening_improvement" &&
    input.decision === "verification_fail"
  ) {
    return "screening_false_positive";
  }
  if (
    input.decision === "verification_fail" &&
    input.artifactValidation &&
    !isArtifactVerificationReady(input.artifactValidation)
  ) {
    return "verification_artifact_incomplete";
  }
  if (input.decision === "verification_fail") {
    return "verification_metric_regress";
  }
  return null;
}

export function derivePromotionReadiness(input: {
  decision: DecisionCode;
  artifactValidation?: ArtifactValidationResult | null;
  executorCapability?: ExecutorCapability | null;
  verificationStatus?: VerificationStatus | null;
  fallbackEvaluation?: FallbackEvaluation | null;
  mutationProvenance?: MutationProvenance | null;
}): boolean {
  if (input.decision === "promoted_head") {
    return true;
  }
  if (input.decision !== "verified_improvement") {
    return false;
  }
  if (input.verificationStatus != null && input.verificationStatus !== "verified") {
    return false;
  }
  if (
    input.executorCapability != null &&
    (!input.executorCapability.authoritative ||
      input.executorCapability.kind !== "tradingview-live")
  ) {
    return false;
  }
  if (input.fallbackEvaluation != null) {
    return false;
  }
  if (collectPromotionProvenanceIssues(input.mutationProvenance).length > 0) {
    return false;
  }
  return (
    input.artifactValidation != null &&
    isArtifactPromotionReady(input.artifactValidation)
  );
}

export function isImprovementDecision(decision: string): boolean {
  const normalized = normalizeDecisionCode(decision);
  return (
    normalized === "screening_improvement" ||
    normalized === "verified_improvement" ||
    normalized === "promoted_head" ||
    normalized === "legacy_screening_improvement"
  );
}

export function assertPromotionEligible(record: ExperimentRecord): void {
  assertSharedPromotionEligible(record);
}

function isAuthoritativeVerifiedDecision(decision: DecisionCode): boolean {
  return (
    decision === "verified_improvement" ||
    decision === "valid_no_promotion" ||
    decision === "hard_gate_fail" ||
    decision === "soft_regress" ||
    decision === "promoted_head"
  );
}
