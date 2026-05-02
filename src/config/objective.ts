import { readFile } from "node:fs/promises";
import path from "node:path";

import { objectiveConfigSchema, type ObjectiveConfig } from "../contracts/types.js";
import {
  DEFAULT_RESEARCH_TARGET_ID,
  loadResearchTarget,
} from "./target-registry.js";
import { fileExists } from "../utils/fs.js";
import { resolveDefaultProjectRoot } from "../cli/runtime-config.js";

export async function loadObjectiveConfig(
  workspaceRoot: string,
  targetId = process.env.AF_RESEARCH_TARGET_ID ?? DEFAULT_RESEARCH_TARGET_ID,
): Promise<ObjectiveConfig> {
  const target = loadResearchTarget({
    projectRoot: process.env.AF_PROJECT_ROOT ?? resolveDefaultProjectRoot(),
    workspaceRoot,
    targetId,
  });
  const workspacePath = path.join(workspaceRoot, "config", target.objectivePolicyFile);
  const fallbackPath = path.join(process.cwd(), "config", target.objectivePolicyFile);
  const filePath = (await fileExists(workspacePath)) ? workspacePath : fallbackPath;
  const raw = await readFile(filePath, "utf8");
  return objectiveConfigSchema.parse(JSON.parse(raw));
}
