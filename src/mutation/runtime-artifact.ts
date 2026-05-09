import path from "node:path";

import {
  DEFAULT_RESEARCH_TARGET_ID,
  resolveTargetStateRoot,
} from "../config/target-registry.js";
import { resolveKnowledgePaths } from "../state/knowledge-paths.js";
import { createCandidateId, writeJson } from "../utils/fs.js";

export async function writeMutationRuntimeArtifact(input: {
  workspaceRoot: string;
  stateRoot?: string;
  iteration: number;
  stage: string;
  payload: unknown;
}): Promise<string> {
  const stateRoot =
    input.stateRoot ??
    resolveTargetStateRoot({
      workspaceRoot: input.workspaceRoot,
      targetId: process.env.AF_RESEARCH_TARGET_ID ?? DEFAULT_RESEARCH_TARGET_ID,
    });
  const runtimeDir = resolveKnowledgePaths(stateRoot).runtimeDir;
  const filePath = path.join(
    runtimeDir,
    `mutation-${input.stage}-${String(input.iteration).padStart(2, "0")}-${createCandidateId("evt")}.json`,
  );
  await writeJson(filePath, {
    stage: input.stage,
    iteration: input.iteration,
    generatedAt: new Date().toISOString(),
    payload: input.payload,
  });
  return filePath;
}
