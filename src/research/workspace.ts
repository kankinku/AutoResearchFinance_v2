import { readFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

import { loadObjectiveConfig } from "../config/objective.js";
import { resolveDefaultProjectRoot, resolveStateRoot } from "../cli/runtime-config.js";
import { copyIfMissing, ensureDir, fileExists } from "../utils/fs.js";
import { migrateLegacyKnowledgeLayout, syncKnowledgeCatalog } from "../state/knowledge-catalog.js";
import { rebuildIndexes } from "../state/index-builder.js";
import { ensureStateRoot } from "../state/jsonl-store.js";
import { resolveKnowledgePaths } from "../state/knowledge-paths.js";
import { ensureActiveSeedBaseline } from "./seed-strategy.js";

export interface WorkspaceInitializationInput {
  projectRoot?: string;
  workspaceRoot: string;
  stateRoot?: string;
}

export interface WorkspaceBootstrapDiagnostics {
  projectRoot: string;
  workspaceRoot: string;
  stateRoot: string;
  missingTemplateFiles: string[];
  missingRuntimeContext: string[];
  copiedFiles: string[];
  createdDirectories: string[];
}

export interface WorkspaceInitializationResult {
  diagnostics: WorkspaceBootstrapDiagnostics;
}

export class WorkspaceBootstrapError extends Error {
  public readonly diagnostics: WorkspaceBootstrapDiagnostics;

  public constructor(message: string, diagnostics: WorkspaceBootstrapDiagnostics) {
    super(message);
    this.name = "WorkspaceBootstrapError";
    this.diagnostics = diagnostics;
  }
}

export async function initializeWorkspace(
  input: string | WorkspaceInitializationInput,
): Promise<WorkspaceInitializationResult> {
  const normalizedInput = normalizeWorkspaceInitializationInput(input);
  const diagnostics: WorkspaceBootstrapDiagnostics = {
    projectRoot: normalizedInput.projectRoot,
    workspaceRoot: normalizedInput.workspaceRoot,
    stateRoot: normalizedInput.stateRoot,
    missingTemplateFiles: [],
    missingRuntimeContext: [],
    copiedFiles: [],
    createdDirectories: [],
  };

  const directories = [
    path.join(normalizedInput.workspaceRoot, "config"),
    path.join(normalizedInput.workspaceRoot, "config", "targets"),
    path.join(normalizedInput.workspaceRoot, "strategies", "source"),
    path.join(normalizedInput.workspaceRoot, "strategies", "candidates"),
    normalizedInput.stateRoot,
  ];
  for (const directory of directories) {
    await ensureDir(directory);
    diagnostics.createdDirectories.push(directory);
  }

  const requiredTemplates = [
    {
      source: path.join(normalizedInput.projectRoot, "config", "objective.qqq-120m.json"),
      target: path.join(normalizedInput.workspaceRoot, "config", "objective.qqq-120m.json"),
    },
    {
      source: path.join(normalizedInput.projectRoot, "config", "objective.qqq-60m.json"),
      target: path.join(normalizedInput.workspaceRoot, "config", "objective.qqq-60m.json"),
    },
    {
      source: path.join(
        normalizedInput.projectRoot,
        "config",
        "targets",
        "qqq-120m-af.json",
      ),
      target: path.join(
        normalizedInput.workspaceRoot,
        "config",
        "targets",
        "qqq-120m-af.json",
      ),
    },
    {
      source: path.join(
        normalizedInput.projectRoot,
        "config",
        "targets",
        "qqq-60m-af-dryrun.json",
      ),
      target: path.join(
        normalizedInput.workspaceRoot,
        "config",
        "targets",
        "qqq-60m-af-dryrun.json",
      ),
    },
    {
      source: path.join(normalizedInput.projectRoot, "strategies", "source", "seed_primary.pine"),
      target: path.join(normalizedInput.workspaceRoot, "strategies", "source", "seed_primary.pine"),
    },
    {
      source: path.join(normalizedInput.projectRoot, "strategies", "source", "runtime_target.pine"),
      target: path.join(normalizedInput.workspaceRoot, "strategies", "source", "runtime_target.pine"),
    },
  ];

  for (const template of requiredTemplates) {
    if (!(await fileExists(template.source))) {
      diagnostics.missingTemplateFiles.push(template.source);
      continue;
    }
    const targetExisted = await fileExists(template.target);
    await copyIfMissing(template.source, template.target);
    if (!targetExisted) {
      diagnostics.copiedFiles.push(template.target);
    }
  }

  await seedRuntimeContext(normalizedInput, diagnostics);
  await ensureStateRoot(normalizedInput.stateRoot);

  if (diagnostics.missingTemplateFiles.length > 0) {
    throw new WorkspaceBootstrapError(
      `Workspace bootstrap is missing required template files: ${diagnostics.missingTemplateFiles.join(", ")}`,
      diagnostics,
    );
  }

  await ensureActiveSeedBaseline(normalizedInput.workspaceRoot);

  const objective = await loadObjectiveConfig(normalizedInput.workspaceRoot);
  await syncKnowledgeCatalog(normalizedInput.workspaceRoot, objective);
  await migrateLegacyKnowledgeLayout(normalizedInput.workspaceRoot);
  await rebuildIndexes(normalizedInput.stateRoot);

  return {
    diagnostics,
  };
}

export async function readRuntimeTarget(
  input: string | WorkspaceInitializationInput,
): Promise<string> {
  const normalizedInput = normalizeWorkspaceInitializationInput(input);
  const runtimeTargetPath = path.join(
    normalizedInput.workspaceRoot,
    "strategies",
    "source",
    "runtime_target.pine",
  );
  if (!(await fileExists(runtimeTargetPath))) {
    await initializeWorkspace(normalizedInput);
  }
  return readFile(runtimeTargetPath, "utf8");
}

function normalizeWorkspaceInitializationInput(
  input: string | WorkspaceInitializationInput,
): Required<WorkspaceInitializationInput> {
  if (typeof input === "string") {
    const workspaceRoot = path.resolve(process.env.AF_WORKSPACE_ROOT ?? input);
    return {
      projectRoot: path.resolve(process.env.AF_PROJECT_ROOT ?? resolveDefaultProjectRoot()),
      workspaceRoot,
      stateRoot: path.resolve(process.env.AF_STATE_ROOT ?? resolveStateRoot(workspaceRoot)),
    };
  }

  return {
    projectRoot: path.resolve(input.projectRoot ?? resolveDefaultProjectRoot()),
    workspaceRoot: path.resolve(input.workspaceRoot),
    stateRoot: path.resolve(input.stateRoot ?? resolveStateRoot(input.workspaceRoot)),
  };
}

async function seedRuntimeContext(
  input: Required<WorkspaceInitializationInput>,
  diagnostics: WorkspaceBootstrapDiagnostics,
): Promise<void> {
  const targetPath = resolveKnowledgePaths(input.stateRoot).qqqTwoHourContextPath;
  if (await fileExists(targetPath)) {
    return;
  }

  const projectStateRoot = path.join(input.projectRoot, "state", "pi-autoresearch");
  const sourcePath = resolveKnowledgePaths(projectStateRoot).qqqTwoHourContextPath;
  if (!(await fileExists(sourcePath))) {
    diagnostics.missingRuntimeContext.push(sourcePath);
    return;
  }

  await copyIfMissing(sourcePath, targetPath);
  diagnostics.copiedFiles.push(targetPath);
}
