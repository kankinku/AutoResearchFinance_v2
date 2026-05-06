import { mkdir, readFile, unlink, writeFile } from "node:fs/promises";
import path from "node:path";

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
  const heartbeat = await readHeartbeat(heartbeatPath);
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
    await mkdir(runtimeRoot, { recursive: true });
    await writeFile(heartbeatPath, `${JSON.stringify(staleHeartbeat)}\n`, "utf8");
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
  };
}

async function readHeartbeat(
  heartbeatPath: string,
): Promise<Record<string, unknown> | null> {
  try {
    const parsed = JSON.parse(await readFile(heartbeatPath, "utf8"));
    return parsed && typeof parsed === "object"
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
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
