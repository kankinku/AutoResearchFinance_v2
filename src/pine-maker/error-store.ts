import { readFile } from "node:fs/promises";
import path from "node:path";

import { z } from "zod";

import {
  compileFailureClassSchema,
  type CompileFailureClass,
  type ParsedMutationResponse,
} from "../contracts/types.js";
import {
  normalizeCompileFailureClasses,
} from "../mutation/compile-failure.js";
import {
  inspectGeneratedMutation,
  type PineGenerationInspection,
} from "../mutation/preflight.js";
import { resolveKnowledgePaths } from "../state/knowledge-paths.js";
import {
  appendJsonlAtomic,
  ensureDir,
  fileExists,
  readJsonlTail,
  sha256,
  writeJson,
} from "../utils/fs.js";

export const PINE_MAKER_ERROR_SCHEMA_VERSION = "pine-maker-error/v1";
export const PINE_MAKER_CONTEXT_SCHEMA_VERSION = "pine-maker-context/v1";

export const pineMakerErrorRecordSchema = z.object({
  schemaVersion: z.literal(PINE_MAKER_ERROR_SCHEMA_VERSION),
  recordedAt: z.string().datetime(),
  targetId: z.string().min(1).nullable().default(null),
  candidateId: z.string().min(1).nullable().default(null),
  candidatePath: z.string().min(1).nullable().default(null),
  sourcePath: z.string().min(1).nullable().default(null),
  sourceHash: z.string().min(1).nullable().default(null),
  errorText: z.string().min(1),
  compileFailureClasses: z.array(compileFailureClassSchema).default([]),
  note: z.string().min(1).nullable().default(null),
});

export type PineMakerErrorRecord = z.infer<typeof pineMakerErrorRecordSchema>;

export interface PineMakerPaths {
  rootDir: string;
  errorsPath: string;
  latestContextPath: string;
}

export interface PineMakerRecordErrorInput {
  stateRoot: string;
  targetId?: string | null;
  candidateId?: string | null;
  candidatePath?: string | null;
  sourcePath?: string | null;
  errorText: string;
  note?: string | null;
}

export interface PineMakerInspectionInput {
  stateRoot: string;
  sourcePath: string;
  candidateId?: string | null;
  targetId?: string | null;
  recentLimit?: number;
}

export interface PineMakerInspectionResult {
  sourcePath: string;
  sourceHash: string;
  recentErrors: PineMakerErrorRecord[];
  recentCompileErrors: string[];
  recentCompileFailureClasses: CompileFailureClass[];
  inspection: PineGenerationInspection;
}

export function resolvePineMakerPaths(stateRoot: string): PineMakerPaths {
  const runtimeDir = resolveKnowledgePaths(stateRoot).runtimeDir;
  const rootDir = path.join(runtimeDir, "pine-maker");
  return {
    rootDir,
    errorsPath: path.join(rootDir, "compile-errors.jsonl"),
    latestContextPath: path.join(rootDir, "latest-context.json"),
  };
}

export async function recordPineMakerError(
  input: PineMakerRecordErrorInput,
): Promise<{ record: PineMakerErrorRecord; paths: PineMakerPaths }> {
  const paths = resolvePineMakerPaths(input.stateRoot);
  await ensureDir(paths.rootDir);
  const sourcePath = input.sourcePath ? path.resolve(input.sourcePath) : null;
  const sourceHash =
    sourcePath && (await fileExists(sourcePath))
      ? sha256(await readFile(sourcePath, "utf8"))
      : null;
  const record = pineMakerErrorRecordSchema.parse({
    schemaVersion: PINE_MAKER_ERROR_SCHEMA_VERSION,
    recordedAt: new Date().toISOString(),
    targetId: input.targetId ?? null,
    candidateId: input.candidateId ?? null,
    candidatePath: input.candidatePath ? path.resolve(input.candidatePath) : null,
    sourcePath,
    sourceHash,
    errorText: normalizeErrorText(input.errorText),
    compileFailureClasses: normalizeCompileFailureClasses([input.errorText]),
    note: input.note ?? null,
  });

  await appendJsonlAtomic(paths.errorsPath, record);
  await writeJson(paths.latestContextPath, {
    schemaVersion: PINE_MAKER_CONTEXT_SCHEMA_VERSION,
    updatedAt: record.recordedAt,
    targetId: record.targetId,
    candidateId: record.candidateId,
    latestErrorClass: record.compileFailureClasses[0] ?? null,
    latestErrorText: record.errorText,
    errorsPath: paths.errorsPath,
  });

  return { record, paths };
}

export async function readRecentPineMakerErrors(
  stateRoot: string,
  options: {
    candidateId?: string | null;
    targetId?: string | null;
    limit?: number;
  } = {},
): Promise<PineMakerErrorRecord[]> {
  const paths = resolvePineMakerPaths(stateRoot);
  const records = await readJsonlTail<unknown>(
    paths.errorsPath,
    options.limit ?? 50,
    2 * 1024 * 1024,
  );
  return records
    .flatMap((record) => {
      const parsed = pineMakerErrorRecordSchema.safeParse(record);
      return parsed.success ? [parsed.data] : [];
    })
    .filter((record) => {
      if (options.candidateId && record.candidateId !== options.candidateId) {
        return false;
      }
      if (options.targetId && record.targetId !== options.targetId) {
        return false;
      }
      return true;
    });
}

export async function inspectPineMakerSource(
  input: PineMakerInspectionInput,
): Promise<PineMakerInspectionResult> {
  const sourcePath = path.resolve(input.sourcePath);
  const source = await readFile(sourcePath, "utf8");
  const recentErrors = await readRecentPineMakerErrors(input.stateRoot, {
    candidateId: input.candidateId,
    targetId: input.targetId,
    limit: input.recentLimit,
  });
  const recentCompileErrors = recentErrors.map((record) => record.errorText);
  const recentCompileFailureClasses = normalizePineMakerClasses(recentErrors);
  const parsedMutation = buildSyntheticMutation(source);
  const inspection = inspectGeneratedMutation(parsedMutation, {
    recentCompileErrors,
    recentCompileFailureClasses,
  });

  return {
    sourcePath,
    sourceHash: sha256(source),
    recentErrors,
    recentCompileErrors,
    recentCompileFailureClasses,
    inspection,
  };
}

function normalizeErrorText(errorText: string): string {
  return errorText.trim().replace(/\s+/g, " ");
}

function normalizePineMakerClasses(
  records: PineMakerErrorRecord[],
): CompileFailureClass[] {
  const classes: CompileFailureClass[] = [];
  for (const record of records) {
    for (const failureClass of [
      ...record.compileFailureClasses,
      ...normalizeCompileFailureClasses([record.errorText]),
    ]) {
      if (failureClass && !classes.includes(failureClass)) {
        classes.push(failureClass);
      }
    }
  }
  return classes;
}

function buildSyntheticMutation(source: string): ParsedMutationResponse {
  return {
    candidateSummary: "Pine Maker source inspection",
    nextMutationHints: [],
    pineScript: source,
    inventory: [
      {
        conditionId: "pine-maker-source",
        role: "entry",
        summary: "Synthetic inventory item for Pine Maker preflight.",
        pineLineHints: [1],
      },
    ],
    inventorySource: "inferred",
    missingFields: [],
    inferredFields: ["inventory"],
  };
}
