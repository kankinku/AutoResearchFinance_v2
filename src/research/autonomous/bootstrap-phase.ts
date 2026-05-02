import path from "node:path";
import { readFile } from "node:fs/promises";

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
import { appendCandidateLedgerRecord } from "../../state/jsonl-store.js";
import {
  findActiveChampionCandidateId,
  selectLocalEvaluationRecords,
} from "../../state/autonomous-state.js";
import { fileExists, sha256 } from "../../utils/fs.js";

const BOOTSTRAP_SEED_RELATIVE_PATH = [
  "strategies",
  "candidates",
  "cand-42ed2fa4.pine",
];

export interface BootstrapCandidatePhaseResult {
  parsedMutation: ParsedMutationResponse;
  candidateArtifact: Awaited<ReturnType<typeof persistCandidateArtifact>>;
  mutationProvenance: MutationProvenance;
}

export function shouldRunBootstrapSeed(input: {
  experiments: ExperimentRecord[];
  headEvents: HeadEventRecord[];
}): boolean {
  if (findActiveChampionCandidateId(input.headEvents)) {
    return false;
  }
  if (input.headEvents.length > 0) {
    return false;
  }

  const localRecords = selectLocalEvaluationRecords(input.experiments);
  const hasEligibleLocalCandidate = localRecords.some(
    (record) => record.eligibility?.autoSelectionEligible === true,
  );
  if (hasEligibleLocalCandidate) {
    return false;
  }

  const bootstrapAlreadyAttempted = localRecords.some(
    (record) => record.selectionPhase === "bootstrap",
  );
  return !bootstrapAlreadyAttempted;
}

export async function prepareBootstrapCandidate(input: {
  projectRoot: string;
  workspaceRoot: string;
  stateRoot: string;
  runId: string;
  iteration: number;
  signal?: AbortSignal;
}): Promise<BootstrapCandidatePhaseResult> {
  const seedPath = path.join(input.projectRoot, ...BOOTSTRAP_SEED_RELATIVE_PATH);
  if (!(await fileExists(seedPath))) {
    throw new Error(`Bootstrap seed is missing: ${seedPath}`);
  }

  const pineScript = await readFile(seedPath, "utf8");
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
          seedPath,
        }),
      ),
      responseHash: sha256(pineScript),
      responseSchemaVersion: "parsed-mutation-response/v1",
      parseStatus: "valid",
      inventorySource: parsedMutation.inventorySource,
      inferredFields: parsedMutation.inferredFields,
      missingFields: parsedMutation.missingFields,
    },
  };
}

function throwIfAborted(signal: AbortSignal | undefined): void {
  if (!signal?.aborted) {
    return;
  }
  const reason = signal.reason;
  throw reason instanceof Error ? reason : new Error("Autonomous phase was aborted.");
}
