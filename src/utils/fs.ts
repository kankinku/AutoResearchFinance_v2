import { createHash, randomUUID } from "node:crypto";
import {
  access,
  appendFile,
  copyFile,
  mkdir,
  open,
  readFile,
  rename,
  stat,
  unlink,
  writeFile,
} from "node:fs/promises";
import { createInterface } from "node:readline";
import path from "node:path";
import process from "node:process";

const JSONL_LOCK_RETRY_MS = 100;
const JSONL_LOCK_TIMEOUT_MS = 5_000;
const JSONL_LOCK_STALE_MS = 30_000;

export type JsonlScanIssueKind =
  | "malformed_json"
  | "partial_tail"
  | "schema_error";

export interface JsonlScanIssue {
  kind: JsonlScanIssueKind;
  lineNumber: number;
  message: string;
  rawLinePreview?: string;
}

export interface TolerantJsonlReadResult<T> {
  records: T[];
  issues: JsonlScanIssue[];
}

type JsonlRecordDecoder<T> = (
  parsed: unknown,
  context: {
    lineNumber: number;
    rawLine: string;
  },
) =>
  | {
      success: true;
      record: T;
    }
  | {
      success: false;
      message: string;
      kind?: Extract<JsonlScanIssueKind, "schema_error">;
    };

export async function ensureDir(dirPath: string): Promise<void> {
  await mkdir(dirPath, { recursive: true });
}

export async function fileExists(filePath: string): Promise<boolean> {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}

export async function writeJson(filePath: string, value: unknown): Promise<void> {
  const dirPath = path.dirname(filePath);
  await ensureDir(dirPath);
  const tempPath = path.join(
    dirPath,
    `.${path.basename(filePath)}.${process.pid}.${Date.now()}.${randomUUID()}.tmp`,
  );
  const handle = await open(tempPath, "w");
  try {
    await handle.writeFile(`${JSON.stringify(value, null, 2)}\n`, "utf8");
    await handle.sync();
  } finally {
    await handle.close();
  }

  try {
    await rename(tempPath, filePath);
  } catch (error) {
    await unlink(tempPath).catch(() => undefined);
    throw error;
  }
}

export async function readJson<T>(filePath: string): Promise<T> {
  return JSON.parse(await readFile(filePath, "utf8")) as T;
}

export async function appendJsonl(filePath: string, record: unknown): Promise<void> {
  await ensureDir(path.dirname(filePath));
  await appendFile(filePath, `${JSON.stringify(record)}\n`, "utf8");
}

export async function appendJsonlAtomic(filePath: string, record: unknown): Promise<void> {
  await ensureDir(path.dirname(filePath));
  const lockPath = `${filePath}.lock`;
  await acquireJsonlLock(lockPath);
  try {
    const handle = await open(filePath, "a");
    try {
      await handle.writeFile(`${JSON.stringify(record)}\n`, "utf8");
      await handle.sync();
    } finally {
      await handle.close();
    }
  } finally {
    await releaseJsonlLock(lockPath);
  }
}

export async function readJsonl<T>(filePath: string): Promise<T[]> {
  if (!(await fileExists(filePath))) {
    return [];
  }

  const raw = (await readFile(filePath, "utf8")).trim();
  if (!raw) {
    return [];
  }

  return raw
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => JSON.parse(line) as T);
}

export async function readJsonlStream<T>(
  filePath: string,
  decoder?: JsonlRecordDecoder<T>,
): Promise<T[]> {
  if (!(await fileExists(filePath))) {
    return [];
  }

  const handle = await open(filePath, "r");
  const records: T[] = [];
  let lineNumber = 0;
  try {
    const stream = handle.createReadStream({ encoding: "utf8" });
    const lines = createInterface({
      input: stream,
      crlfDelay: Infinity,
    });

    for await (const rawLine of lines) {
      lineNumber += 1;
      const trimmedLine = rawLine.trim();
      if (!trimmedLine) {
        continue;
      }

      const parsed = JSON.parse(trimmedLine);
      if (!decoder) {
        records.push(parsed as T);
        continue;
      }

      const decoded = decoder(parsed, {
        lineNumber,
        rawLine,
      });
      if (!decoded.success) {
        throw new Error(
          `Invalid JSONL record at ${filePath}:${lineNumber}: ${decoded.message}`,
        );
      }
      records.push(decoded.record);
    }
  } finally {
    await handle.close();
  }

  return records;
}

export async function readJsonlTail<T>(
  filePath: string,
  maxRecords: number,
  maxBytes: number,
): Promise<T[]> {
  if (!(await fileExists(filePath))) {
    return [];
  }

  const fileStat = await stat(filePath);
  if (fileStat.size === 0 || maxRecords <= 0 || maxBytes <= 0) {
    return [];
  }

  const handle = await open(filePath, "r");
  const chunks: string[] = [];
  let position = fileStat.size;
  let bytesReadTotal = 0;
  let newlineCount = 0;

  try {
    while (position > 0 && bytesReadTotal < maxBytes && newlineCount <= maxRecords) {
      const readSize = Math.min(1024 * 1024, position, maxBytes - bytesReadTotal);
      position -= readSize;
      const buffer = Buffer.alloc(readSize);
      const { bytesRead } = await handle.read(buffer, 0, readSize, position);
      if (bytesRead <= 0) {
        break;
      }

      const chunk = buffer.subarray(0, bytesRead).toString("utf8");
      chunks.unshift(chunk);
      bytesReadTotal += bytesRead;
      newlineCount += countNewlines(chunk);
    }
  } finally {
    await handle.close();
  }

  return chunks
    .join("")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .slice(-maxRecords)
    .flatMap((line) => {
      try {
        return [JSON.parse(line) as T];
      } catch {
        return [];
      }
    });
}

export async function scanJsonlTolerant<T = unknown>(
  filePath: string,
  decoder?: JsonlRecordDecoder<T>,
): Promise<TolerantJsonlReadResult<T>> {
  if (!(await fileExists(filePath))) {
    return {
      records: [],
      issues: [],
    };
  }

  const raw = await readFile(filePath, "utf8");
  if (!raw.trim()) {
    return {
      records: [],
      issues: [],
    };
  }

  const issues: JsonlScanIssue[] = [];
  const records: T[] = [];
  const lines = raw.split("\n");

  for (let index = 0; index < lines.length; index += 1) {
    const rawLine = lines[index] ?? "";
    const trimmedLine = rawLine.trim();
    if (!trimmedLine) {
      continue;
    }

    let parsed: unknown;
    try {
      parsed = JSON.parse(trimmedLine);
    } catch (error) {
      const isTailRecord =
        index === lines.length - 1 ||
        lines.slice(index + 1).every((entry) => entry.trim().length === 0);
      issues.push({
        kind: isTailRecord ? "partial_tail" : "malformed_json",
        lineNumber: index + 1,
        message: error instanceof Error ? error.message : String(error),
        rawLinePreview: rawLine.slice(0, 240),
      });
      continue;
    }

    if (!decoder) {
      records.push(parsed as T);
      continue;
    }

    const decoded = decoder(parsed, {
      lineNumber: index + 1,
      rawLine,
    });
    if (decoded.success) {
      records.push(decoded.record);
      continue;
    }

    issues.push({
      kind: decoded.kind ?? "schema_error",
      lineNumber: index + 1,
      message: decoded.message,
      rawLinePreview: rawLine.slice(0, 240),
    });
  }

  return {
    records,
    issues,
  };
}

export function sha256(content: string): string {
  return createHash("sha256").update(content, "utf8").digest("hex");
}

export function sha256Json(value: unknown): string {
  return sha256(JSON.stringify(value));
}

export function createCandidateId(prefix = "cand"): string {
  return `${prefix}-${randomUUID().slice(0, 8)}`;
}

export async function copyIfMissing(sourcePath: string, targetPath: string): Promise<void> {
  if (await fileExists(targetPath)) {
    return;
  }

  await ensureDir(path.dirname(targetPath));
  await copyFile(sourcePath, targetPath);
}

async function acquireJsonlLock(lockPath: string): Promise<void> {
  const startedAt = Date.now();
  const lockPayload = `${JSON.stringify({
    pid: process.pid,
    acquiredAt: new Date().toISOString(),
  })}\n`;

  while (true) {
    try {
      await writeFile(lockPath, lockPayload, {
        encoding: "utf8",
        flag: "wx",
      });
      return;
    } catch (error) {
      if (!isFileExistsError(error)) {
        throw error;
      }

      if (await isStaleJsonlLock(lockPath)) {
        await releaseJsonlLock(lockPath);
        continue;
      }

      if (Date.now() - startedAt >= JSONL_LOCK_TIMEOUT_MS) {
        throw new Error(`Timed out acquiring JSONL append lock: ${lockPath}`);
      }

      await sleep(JSONL_LOCK_RETRY_MS);
    }
  }
}

async function releaseJsonlLock(lockPath: string): Promise<void> {
  try {
    await unlink(lockPath);
  } catch (error) {
    if (!isMissingFileError(error)) {
      throw error;
    }
  }
}

async function isStaleJsonlLock(lockPath: string): Promise<boolean> {
  try {
    const lockStat = await stat(lockPath);
    return Date.now() - lockStat.mtimeMs >= JSONL_LOCK_STALE_MS;
  } catch (error) {
    if (isMissingFileError(error)) {
      return false;
    }
    throw error;
  }
}

function isFileExistsError(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    (error as { code?: string }).code === "EEXIST"
  );
}

function isMissingFileError(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    (error as { code?: string }).code === "ENOENT"
  );
}

function countNewlines(value: string): number {
  let count = 0;
  for (const char of value) {
    if (char === "\n") {
      count += 1;
    }
  }
  return count;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}
