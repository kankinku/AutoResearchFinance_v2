import { existsSync, readdirSync, readFileSync } from "node:fs";
import path from "node:path";

import { z } from "zod";

const researchTargetSchema = z.object({
  id: z.string().min(1),
  symbol: z.string().min(1),
  timeframe: z.string().min(1),
  strategyFamily: z.literal("AF"),
  primaryExecutor: z.literal("local-af-backtest"),
  externalCalibrationExecutor: z.enum(["tradingview"]).nullable().default("tradingview"),
  objectivePolicyFile: z.string().min(1),
  noveltyPolicy: z.string().min(1),
  calibrationPolicy: z.string().min(1),
});

export type ResearchTarget = z.infer<typeof researchTargetSchema>;

export const DEFAULT_RESEARCH_TARGET_ID = "qqq-120m-af";

export function resolveTargetStateRoot(input: {
  workspaceRoot: string;
  targetId: string;
}): string {
  return path.join(
    input.workspaceRoot,
    "state",
    "targets",
    input.targetId,
    "pi-autoresearch",
  );
}

export function resolveLegacySharedStateRoot(workspaceRoot: string): string {
  return path.join(workspaceRoot, "state", "pi-autoresearch");
}

export function loadResearchTarget(input: {
  projectRoot: string;
  workspaceRoot?: string;
  targetId?: string;
}): ResearchTarget {
  const targetId = input.targetId ?? DEFAULT_RESEARCH_TARGET_ID;
  const targetFileName = `${targetId}.json`;
  const candidatePaths = [
    input.workspaceRoot
      ? path.join(input.workspaceRoot, "config", "targets", targetFileName)
      : null,
    path.join(input.projectRoot, "config", "targets", targetFileName),
  ].filter((value): value is string => value != null);

  for (const candidatePath of candidatePaths) {
    try {
      const raw = readFileSync(candidatePath, "utf8");
      return researchTargetSchema.parse(JSON.parse(raw));
    } catch {
      continue;
    }
  }

  throw new Error(`Unable to load research target config for ${targetId}.`);
}

export function loadAllResearchTargets(input: {
  projectRoot: string;
  workspaceRoot?: string;
}): ResearchTarget[] {
  const targetDirs = [
    path.join(input.projectRoot, "config", "targets"),
    input.workspaceRoot ? path.join(input.workspaceRoot, "config", "targets") : null,
  ].filter((value): value is string => value != null);
  const byId = new Map<string, ResearchTarget>();

  for (const targetDir of targetDirs) {
    if (!existsSync(targetDir)) {
      continue;
    }
    for (const entry of readdirSync(targetDir, { withFileTypes: true })) {
      if (!entry.isFile() || !entry.name.endsWith(".json")) {
        continue;
      }
      try {
        const raw = readFileSync(path.join(targetDir, entry.name), "utf8");
        const target = researchTargetSchema.parse(JSON.parse(raw));
        byId.set(target.id, target);
      } catch {
        continue;
      }
    }
  }

  return [...byId.values()].sort((left, right) => left.id.localeCompare(right.id));
}
