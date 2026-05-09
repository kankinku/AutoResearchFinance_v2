import { mkdir, open, readFile, unlink } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

export interface RuntimeCommandLock {
  commandName: string;
  lockPath: string;
  pid: number;
  token: string;
  acquiredAt: string;
  release: () => Promise<void>;
}

interface RuntimeCommandLockPayload {
  commandName?: string;
  pid?: number;
  token?: string;
  acquiredAt?: string;
}

export async function acquireRuntimeCommandLock(input: {
  runtimeRoot: string;
  commandName: string;
}): Promise<RuntimeCommandLock> {
  const runtimeRoot = path.resolve(input.runtimeRoot);
  const lockPath = path.join(runtimeRoot, `${input.commandName}.lock`);
  const token = `${process.pid}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const acquiredAt = new Date().toISOString();

  await mkdir(runtimeRoot, { recursive: true });

  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const handle = await open(lockPath, "wx");
      try {
        await handle.writeFile(
          `${JSON.stringify({
            commandName: input.commandName,
            pid: process.pid,
            token,
            acquiredAt,
          })}\n`,
          "utf8",
        );
      } finally {
        await handle.close();
      }
      return {
        commandName: input.commandName,
        lockPath,
        pid: process.pid,
        token,
        acquiredAt,
        release: () => releaseRuntimeCommandLock(lockPath, token),
      };
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "EEXIST") {
        throw error;
      }

      const existing = await readRuntimeCommandLock(lockPath);
      if (isRuntimeCommandLockStale(existing)) {
        await unlink(lockPath).catch(() => undefined);
        continue;
      }

      throw new Error(
        `${input.commandName} already appears to be running with PID ${
          existing?.pid ?? "unknown"
        }. Stop the existing AF process before starting another one.`,
      );
    }
  }

  throw new Error(`Unable to acquire runtime lock: ${lockPath}`);
}

export async function withRuntimeCommandLock<T>(
  input: {
    runtimeRoot: string;
    commandName: string;
  },
  callback: () => Promise<T>,
): Promise<T> {
  const lock = await acquireRuntimeCommandLock(input);
  try {
    return await callback();
  } finally {
    await lock.release();
  }
}

async function readRuntimeCommandLock(
  lockPath: string,
): Promise<RuntimeCommandLockPayload | null> {
  try {
    const parsed = JSON.parse(await readFile(lockPath, "utf8"));
    return parsed && typeof parsed === "object"
      ? (parsed as RuntimeCommandLockPayload)
      : null;
  } catch {
    return null;
  }
}

function isRuntimeCommandLockStale(
  payload: RuntimeCommandLockPayload | null,
): boolean {
  if (!payload || !Number.isInteger(payload.pid) || Number(payload.pid) <= 0) {
    return true;
  }
  if (!isPidRunning(Number(payload.pid))) {
    return true;
  }
  return false;
}

async function releaseRuntimeCommandLock(
  lockPath: string,
  token: string,
): Promise<void> {
  const payload = await readRuntimeCommandLock(lockPath);
  if (payload?.token !== token || payload.pid !== process.pid) {
    return;
  }
  await unlink(lockPath).catch(() => undefined);
}

function isPidRunning(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return (error as NodeJS.ErrnoException).code === "EPERM";
  }
}
