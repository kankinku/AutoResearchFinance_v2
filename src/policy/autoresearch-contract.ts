import path from "node:path";

export const AUTORESEARCH_CONTRACT_VERSION = "finance-autoresearch-contract/v1";
export const MUTATION_AUTHORITY_MODE = "spec_only";
export const STRATEGY_SPEC_MUTATION_AUTHORITY = "strategy_spec";

export const EVALUATION_FIREWALL_PATHS = [
  "src/evaluation/",
  "src/automation/local-backtest/",
  "src/automation/tradingview/",
  "config/objective.*",
  "config/targets/*",
  "src/state/",
] as const;

export const EDITABLE_RESEARCH_PATHS = [
  "strategies/candidates/",
  "strategies/specs/",
  "strategies/indicators/",
] as const;

export type MutationSchemaMode = "strict" | "legacy-recovery-test-only";

export function parseMutationSchemaMode(
  value: string | undefined,
): MutationSchemaMode {
  return value === "legacy-recovery-test-only"
    ? "legacy-recovery-test-only"
    : "strict";
}

export function assertEditableResearchPath(input: {
  workspaceRoot: string;
  targetPath: string;
}): void {
  const workspaceRoot = path.resolve(input.workspaceRoot);
  const targetPath = path.resolve(input.targetPath);
  const allowed = EDITABLE_RESEARCH_PATHS.some((relativePath) => {
    const allowedRoot = path.resolve(workspaceRoot, relativePath.replace(/\/$/, ""));
    return targetPath === allowedRoot || targetPath.startsWith(`${allowedRoot}${path.sep}`);
  });
  if (!allowed) {
    throw new Error(`Candidate artifacts may only be written under editable research paths: ${EDITABLE_RESEARCH_PATHS.join(", ")}`);
  }
}

export function assertNoFirewallPathReference(input: {
  candidateSummary?: string | null;
  nextMutationHints?: string[] | null;
  specPatch?: unknown;
}): void {
  const haystack = [
    input.candidateSummary ?? "",
    ...(input.nextMutationHints ?? []),
    JSON.stringify(input.specPatch ?? {}),
  ]
    .join("\n")
    .toLowerCase();
  const matchedPath = EVALUATION_FIREWALL_PATHS.find((pathPattern) =>
    haystack.includes(pathPattern.toLowerCase().replace(/\*/g, "")),
  );
  if (matchedPath) {
    throw new Error(`Mutation response must not target evaluation firewall path ${matchedPath}.`);
  }
}
