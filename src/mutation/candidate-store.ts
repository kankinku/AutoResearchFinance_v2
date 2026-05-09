import path from "node:path";
import { writeFile } from "node:fs/promises";

import {
  candidateArtifactSchema,
  type CandidateArtifact,
  type ParsedMutationResponse,
} from "../contracts/types.js";
import { ensureCandidateStudyTitle } from "../strategy-source/pine-study.js";
import { createCandidateId, ensureDir, sha256 } from "../utils/fs.js";
import { assertEditableResearchPath } from "../policy/autoresearch-contract.js";
import {
  canonicalAfStrategySpecJson,
  hashAfStrategySpec,
} from "../strategy-spec/hash.js";

export async function persistCandidateArtifact(input: {
  workspaceRoot: string;
  parsedMutation: ParsedMutationResponse;
  parentCandidateId: string | null;
  branchId: string;
}): Promise<CandidateArtifact> {
  const candidateId = createCandidateId();
  const normalizedMutation = ensureCandidateStudyTitle(
    input.parsedMutation.pineScript,
    candidateId,
  );
  const pineHash = sha256(normalizedMutation.source);
  const candidatesDir = path.join(input.workspaceRoot, "strategies", "candidates");
  const specsDir = path.join(input.workspaceRoot, "strategies", "specs");
  const candidatePath = path.join(candidatesDir, `${candidateId}.pine`);
  assertEditableResearchPath({
    workspaceRoot: input.workspaceRoot,
    targetPath: candidatePath,
  });
  await ensureDir(candidatesDir);
  await writeFile(candidatePath, normalizedMutation.source, "utf8");
  let specPath: string | null = null;
  let specHash: string | null = null;
  if (input.parsedMutation.strategySpec) {
    await ensureDir(specsDir);
    specPath = path.join(specsDir, `${candidateId}.json`);
    assertEditableResearchPath({
      workspaceRoot: input.workspaceRoot,
      targetPath: specPath,
    });
    const specJson = canonicalAfStrategySpecJson(input.parsedMutation.strategySpec);
    specHash = hashAfStrategySpec(input.parsedMutation.strategySpec);
    await writeFile(specPath, specJson, "utf8");
  }

  return candidateArtifactSchema.parse({
    candidateId,
    parentId: input.parentCandidateId,
    branchId: input.branchId,
    pinePath: candidatePath,
    pineHash,
    specPath,
    specHash,
    studyTitle: normalizedMutation.studyTitle,
    inventory: input.parsedMutation.inventory,
    candidateSummary: input.parsedMutation.candidateSummary,
    nextMutationHints: input.parsedMutation.nextMutationHints,
  });
}
