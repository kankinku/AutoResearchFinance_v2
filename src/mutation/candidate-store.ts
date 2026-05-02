import path from "node:path";
import { writeFile } from "node:fs/promises";

import {
  candidateArtifactSchema,
  type CandidateArtifact,
  type ParsedMutationResponse,
} from "../contracts/types.js";
import { ensureCandidateStudyTitle } from "../automation/tradingview/pine-study.js";
import { createCandidateId, ensureDir, sha256 } from "../utils/fs.js";

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
  const candidatePath = path.join(candidatesDir, `${candidateId}.pine`);
  await ensureDir(candidatesDir);
  await writeFile(candidatePath, normalizedMutation.source, "utf8");

  return candidateArtifactSchema.parse({
    candidateId,
    parentId: input.parentCandidateId,
    branchId: input.branchId,
    pinePath: candidatePath,
    pineHash,
    studyTitle: normalizedMutation.studyTitle,
    inventory: input.parsedMutation.inventory,
    candidateSummary: input.parsedMutation.candidateSummary,
    nextMutationHints: input.parsedMutation.nextMutationHints,
  });
}
