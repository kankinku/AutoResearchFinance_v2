import { readFile, unlink } from "node:fs/promises";
import path from "node:path";

import { writeJson } from "../utils/fs.js";

export type AutonomousLoopRuntimeState = "missing" | "active" | "stale";

export interface AutonomousLoopRuntimeStatus {
  status: AutonomousLoopRuntimeState;
  owner: string;
  pid: number | null;
  pidPath: string;
  heartbeatPath: string;
  staleReason: string | null;
  lastCheckedAt: string;
  heartbeat: Record<string, unknown> | null;
  heartbeatReadError: string | null;
}

export async function reconcileAutonomousLoopRuntime(input: {
  runtimeRoot: string;
  owner: string;
  writeStaleHeartbeat?: boolean;
}): Promise<AutonomousLoopRuntimeStatus> {
  const runtimeRoot = path.resolve(input.runtimeRoot);
  const pidPath = path.join(runtimeRoot, "autonomous-loop.pid");
  const heartbeatPath = path.join(runtimeRoot, "autonomous-loop-heartbeat.json");
  const lastCheckedAt = new Date().toISOString();
  const heartbeatRead = await readHeartbeat(heartbeatPath);
  const heartbeat = heartbeatRead.heartbeat;
  const rawPid = await readFile(pidPath, "utf8").catch(() => null);

  if (rawPid == null) {
    return {
      status: "missing",
      owner: input.owner,
      pid: null,
      pidPath,
      heartbeatPath,
      staleReason: null,
      lastCheckedAt,
      heartbeat,
      heartbeatReadError: heartbeatRead.error,
    };
  }

  const pid = Number.parseInt(rawPid.trim(), 10);
  const staleReason = !Number.isFinite(pid)
    ? "pid_file_invalid"
    : isPidRunning(pid)
      ? null
      : "pid_not_running";

  if (staleReason == null) {
    return {
      status: "active",
      owner: input.owner,
      pid,
      pidPath,
      heartbeatPath,
      staleReason: null,
      lastCheckedAt,
      heartbeat,
      heartbeatReadError: heartbeatRead.error,
    };
  }

  await unlink(pidPath).catch(() => undefined);
  const staleHeartbeat = {
    ...(heartbeat ?? {}),
    pid: Number.isFinite(pid) ? pid : null,
    status: "stale",
    owner: input.owner,
    staleReason,
    lastCheckedAt,
  };
  if (input.writeStaleHeartbeat ?? true) {
    await writeJson(heartbeatPath, staleHeartbeat);
  }

  return {
    status: "stale",
    owner: input.owner,
    pid: Number.isFinite(pid) ? pid : null,
    pidPath,
    heartbeatPath,
    staleReason,
    lastCheckedAt,
    heartbeat: staleHeartbeat,
    heartbeatReadError: heartbeatRead.error,
  };
}

async function readHeartbeat(
  heartbeatPath: string,
): Promise<{ heartbeat: Record<string, unknown> | null; error: string | null }> {
  try {
    const parsed = JSON.parse(await readFile(heartbeatPath, "utf8"));
    return {
      heartbeat:
        parsed && typeof parsed === "object"
          ? (parsed as Record<string, unknown>)
          : null,
      error: null,
    };
  } catch (error) {
    return {
      heartbeat: null,
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

function isPidRunning(pid: number): boolean {
  if (!Number.isInteger(pid) || pid <= 0) {
    return false;
  }
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return (error as NodeJS.ErrnoException).code === "EPERM";
  }
}
