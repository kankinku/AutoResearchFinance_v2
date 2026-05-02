import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";

import {
  type SeedStrategyReference,
} from "../contracts/types.js";
import { ensureDir, fileExists, sha256 } from "../utils/fs.js";

function sourceDir(workspaceRoot: string): string {
  return path.join(workspaceRoot, "strategies", "source");
}

export function resolveSeedPrimaryPath(workspaceRoot: string): string {
  return path.join(sourceDir(workspaceRoot), "seed_primary.pine");
}

export function resolveActiveBaselinePath(workspaceRoot: string): string {
  return path.join(sourceDir(workspaceRoot), "baseline.pine");
}

function isLegacyBaseline(source: string): boolean {
  return source.includes('strategy("AF Baseline QQQ 120"');
}

export async function ensureActiveSeedBaseline(workspaceRoot: string): Promise<void> {
  const dir = sourceDir(workspaceRoot);
  const curatedPath = resolveSeedPrimaryPath(workspaceRoot);
  const baselinePath = resolveActiveBaselinePath(workspaceRoot);
  await ensureDir(dir);

  if (!(await fileExists(curatedPath))) {
    throw new Error(`Curated seed is missing: ${curatedPath}`);
  }

  const curated = await readFile(curatedPath, "utf8");
  if (!(await fileExists(baselinePath))) {
    await writeFile(baselinePath, curated, "utf8");
    return;
  }

  const baseline = await readFile(baselinePath, "utf8");
  if (isLegacyBaseline(baseline)) {
    await writeFile(baselinePath, curated, "utf8");
  }
}

export async function readActiveBaseline(workspaceRoot: string): Promise<string> {
  await ensureActiveSeedBaseline(workspaceRoot);
  return readFile(resolveActiveBaselinePath(workspaceRoot), "utf8");
}

export async function loadSeedStrategyReference(
  workspaceRoot: string,
): Promise<SeedStrategyReference & { candidateHash: string }> {
  const curatedPath = resolveSeedPrimaryPath(workspaceRoot);
  const source = await readFile(curatedPath, "utf8");
  const titleMatch = source.match(/strategy\((['"])(.*?)\1/);

  return {
    candidateId: "seed_primary",
    summary:
      "Curated exhaustion seed strategy used as the AF research anchor. Preserve the exhaustion count sequence, confirmation logic, slot-based scaling and replacement, and staged bearish exit behavior unless explicitly improving one of those core blocks.",
    studyTitle: titleMatch?.[2] ?? null,
    candidateHash: sha256(source),
  };
}
