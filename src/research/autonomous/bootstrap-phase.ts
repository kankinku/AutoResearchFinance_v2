import path from "node:path";
import { readFile } from "node:fs/promises";

import { loadResearchTarget } from "../../config/target-registry.js";
import {
  type HeadEventRecord,
} from "../../contracts/autonomous.js";
import {
  type ExperimentRecord,
  type MutationProvenance,
  type ParsedMutationResponse,
} from "../../contracts/types.js";
import { persistCandidateArtifact } from "../../mutation/candidate-store.js";
import { inferConditionInventoryFromPine } from "../../mutation/parser.js";
import { renderAfStrategySpecToPine } from "../../strategy-spec/codegen-pine.js";
import { parseAfStrategySpec } from "../../strategy-spec/schema.js";
import {
  AUTORESEARCH_CONTRACT_VERSION,
  STRATEGY_SPEC_MUTATION_AUTHORITY,
} from "../../policy/autoresearch-contract.js";
import { hashAfStrategySpec } from "../../strategy-spec/hash.js";
import { appendCandidateLedgerRecord } from "../../state/jsonl-store.js";
import {
  findActiveChampionCandidateId,
  selectLocalEvaluationRecords,
} from "../../state/autonomous-state.js";
import { fileExists, sha256 } from "../../utils/fs.js";

const BOOTSTRAP_SEED_RELATIVE_PATH = [
  "strategies",
  "specs",
  "baseline.af-spec.json",
];
const BOOTSTRAP_SPEC_DIR = ["strategies", "specs"];

export interface BootstrapCandidatePhaseResult {
  parsedMutation: ParsedMutationResponse;
  candidateArtifact: Awaited<ReturnType<typeof persistCandidateArtifact>>;
  mutationProvenance: MutationProvenance;
}

export function shouldRunBootstrapSeed(input: {
  experiments: ExperimentRecord[];
  headEvents: HeadEventRecord[];
  bootstrapSpecHash?: string | null;
}): boolean {
  const localRecords = selectLocalEvaluationRecords(input.experiments);
  const hasEligibleLocalCandidate = localRecords.some(
    (record) => record.eligibility?.autoSelectionEligible === true,
  );
  if (hasEligibleLocalCandidate) {
    return false;
  }

  const activeChampionId = findActiveChampionCandidateId(input.headEvents);
  if (activeChampionId) {
    const activeChampion = localRecords.find(
      (record) => record.candidateId === activeChampionId,
    );
    return Boolean(
      input.bootstrapSpecHash &&
        activeChampion?.selectionPhase === "bootstrap" &&
        activeChampion.specHash !== input.bootstrapSpecHash,
    );
  }
  if (input.headEvents.length > 0) {
    return false;
  }

  const bootstrapAlreadyAttempted = localRecords.some(
    (record) =>
      record.selectionPhase === "bootstrap" &&
      (!input.bootstrapSpecHash || record.specHash === input.bootstrapSpecHash),
  );
  return !bootstrapAlreadyAttempted;
}

export async function prepareBootstrapCandidate(input: {
  projectRoot: string;
  workspaceRoot: string;
  stateRoot: string;
  runId: string;
  iteration: number;
  targetId?: string;
  signal?: AbortSignal;
}): Promise<BootstrapCandidatePhaseResult> {
  const seed = await loadBootstrapSeedSpec({
    projectRoot: input.projectRoot,
    workspaceRoot: input.workspaceRoot,
    targetId: input.targetId,
  });
  const strategySpec = seed.strategySpec;
  const pineScript = renderAfStrategySpecToPine(strategySpec);
  throwIfAborted(input.signal);
  const inventory = inferConditionInventoryFromPine(pineScript);
  const parsedMutation: ParsedMutationResponse = {
    candidateSummary:
      "Bootstrap local-compatible AF seed used to establish the first fresh-root research baseline champion.",
    nextMutationHints: [
      "Mutate beyond the bootstrap seed once the first champion exists.",
      "Preserve AF local compatibility while increasing novelty and robustness.",
    ],
    pineScript,
    strategySpec,
    specPatch: null,
    inventory,
    inventorySource: "inferred",
    missingFields: [],
    inferredFields: ["inventory"],
  };
  throwIfAborted(input.signal);
  const candidateArtifact = await persistCandidateArtifact({
    workspaceRoot: input.workspaceRoot,
    parsedMutation,
    parentCandidateId: null,
    branchId: "autonomous-bootstrap",
  });
  throwIfAborted(input.signal);
  await appendCandidateLedgerRecord(input.stateRoot, {
    runId: input.runId,
    iteration: input.iteration,
    candidateId: candidateArtifact.candidateId,
    parentCandidateId: candidateArtifact.parentId,
    branchId: candidateArtifact.branchId,
    studyTitle: candidateArtifact.studyTitle,
    candidatePath: candidateArtifact.pinePath,
    candidateHash: candidateArtifact.pineHash,
    contractVersion: AUTORESEARCH_CONTRACT_VERSION,
    mutationAuthority: candidateArtifact.specHash
      ? STRATEGY_SPEC_MUTATION_AUTHORITY
      : null,
    specPath: candidateArtifact.specPath ?? null,
    specHash: candidateArtifact.specHash ?? null,
    candidateSummary: candidateArtifact.candidateSummary,
    nextMutationHints: candidateArtifact.nextMutationHints,
  });

  return {
    parsedMutation,
    candidateArtifact,
    mutationProvenance: {
      briefHash: sha256(
        JSON.stringify({
          operation: "bootstrapSeedBrief",
          bootstrapSource: "local_compatible_seed",
          bootstrapReason: "fresh_state_without_active_champion",
        }),
      ),
      promptHash: sha256(
        JSON.stringify({
          operation: "bootstrapSeed",
          seedSpecPath: seed.path,
        }),
      ),
      responseHash: sha256(seed.rawJson),
      responseSchemaVersion: "parsed-mutation-response/v1",
      parseStatus: "valid",
      inventorySource: parsedMutation.inventorySource,
      inferredFields: parsedMutation.inferredFields,
      missingFields: parsedMutation.missingFields,
    },
  };
}

export async function loadBootstrapSeedSpec(input: {
  projectRoot: string;
  workspaceRoot: string;
  targetId?: string;
}): Promise<{
  path: string;
  rawJson: string;
  strategySpec: ReturnType<typeof parseAfStrategySpec>;
  specHash: string;
}> {
  const seedSpecPath = await resolveBootstrapSeedSpecPath(input);
  if (!(await fileExists(seedSpecPath))) {
    throw new Error(`Bootstrap seed spec is missing: ${seedSpecPath}`);
  }

  const rawJson = await readFile(seedSpecPath, "utf8");
  const strategySpec = parseAfStrategySpec(JSON.parse(rawJson));
  return {
    path: seedSpecPath,
    rawJson,
    strategySpec,
    specHash: hashAfStrategySpec(strategySpec),
  };
}

export async function resolveBootstrapSeedSpecPath(input: {
  projectRoot: string;
  workspaceRoot: string;
  targetId?: string;
}): Promise<string> {
  const targetSeedFile = input.targetId
    ? loadResearchTarget({
        projectRoot: input.projectRoot,
        workspaceRoot: input.workspaceRoot,
        targetId: input.targetId,
      }).bootstrapSeedSpecFile
    : undefined;
  const targetScopedSeedFile =
    targetSeedFile ?? (input.targetId ? `baseline.${input.targetId}.af-spec.json` : null);
  const candidateRelativePaths = [
    targetScopedSeedFile
      ? [...BOOTSTRAP_SPEC_DIR, assertSafeBootstrapSeedFile(targetScopedSeedFile)]
      : null,
    BOOTSTRAP_SEED_RELATIVE_PATH,
  ].filter((value): value is string[] => value != null);

  for (const relativePath of candidateRelativePaths) {
    for (const root of [input.workspaceRoot, input.projectRoot]) {
      const candidatePath = path.join(root, ...relativePath);
      if (await fileExists(candidatePath)) {
        return candidatePath;
      }
    }
  }

  return path.join(input.projectRoot, ...BOOTSTRAP_SEED_RELATIVE_PATH);
}

function assertSafeBootstrapSeedFile(fileName: string): string {
  if (
    path.isAbsolute(fileName) ||
    fileName.includes("/") ||
    fileName.includes("\\") ||
    fileName.includes("..")
  ) {
    throw new Error(
      `Invalid bootstrapSeedSpecFile "${fileName}". Use a file name under strategies/specs.`,
    );
  }
  return fileName;
}

function throwIfAborted(signal: AbortSignal | undefined): void {
  if (!signal?.aborted) {
    return;
  }
  const reason = signal.reason;
  throw reason instanceof Error ? reason : new Error("Autonomous phase was aborted.");
}
