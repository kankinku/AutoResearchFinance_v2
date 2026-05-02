import { type LocalCompatibilityIssue } from "../../contracts/types.js";
import {
  type AutonomousLocalCompatibility,
  type LocalEvaluationBlockingReason,
} from "../../contracts/autonomous.js";

export function buildLocalCompatibilityStatus(input: {
  compatible: boolean;
  reason: string | null;
  issues: LocalCompatibilityIssue[];
}): AutonomousLocalCompatibility {
  const missingFunctions = input.issues
    .filter((issue) => issue.kind === "missing_function" && issue.field)
    .map((issue) => issue.field as string);
  const missingInputs = input.issues
    .filter((issue) => issue.kind === "missing_input" && issue.field)
    .map((issue) => issue.field as string);
  const unsupportedPatterns = input.issues
    .filter((issue) => issue.kind === "unsupported_pattern")
    .map((issue) => issue.code);

  return {
    compatible: input.compatible,
    unsupportedReason: input.reason,
    missingFunctions,
    missingInputs,
    unsupportedPatterns,
  };
}

export function buildCompatibilityBlockingReasons(input: {
  reason: string | null;
  issues: LocalCompatibilityIssue[];
}): LocalEvaluationBlockingReason[] {
  if (input.issues.length === 0) {
    return [
      {
        kind: "local_unsupported",
        message: input.reason ?? "Local executor reported an unsupported strategy.",
        evidence: {
          reason: input.reason,
        },
        suggestedRepairKind: "local_compatibility_repair",
      },
    ];
  }

  return input.issues.map((issue) => ({
    kind:
      issue.kind === "missing_function"
        ? "missing_required_function"
        : issue.kind === "missing_input"
          ? "missing_required_input"
          : issue.code.startsWith("unsupported_chart_target")
            ? "unsupported_strategy_family"
            : issue.code === "unsupported_strategy_family"
              ? "unsupported_strategy_family"
              : "local_unsupported",
    message: issue.detail,
    evidence: {
      issueCode: issue.code,
      field: issue.field,
      reason: input.reason,
    },
    suggestedRepairKind: "local_compatibility_repair",
  }));
}
