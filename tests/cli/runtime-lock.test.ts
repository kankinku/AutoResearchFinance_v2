import { access, mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { describe, expect, test } from "vitest";

import { acquireRuntimeCommandLock } from "../../src/cli/runtime-lock.js";

describe("runtime command lock", () => {
  test("blocks a second active command for the same runtime root", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-runtime-lock-"));
    const runtimeRoot = path.join(root, "runtime");
    const lock = await acquireRuntimeCommandLock({
      runtimeRoot,
      commandName: "run-autonomous-loop",
    });

    try {
      await expect(
        acquireRuntimeCommandLock({
          runtimeRoot,
          commandName: "run-autonomous-loop",
        }),
      ).rejects.toThrow(/already appears to be running/);
    } finally {
      await lock.release();
    }

    await expect(access(lock.lockPath)).rejects.toThrow();
  });

  test("replaces stale command locks before acquiring", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "af-runtime-stale-lock-"));
    const runtimeRoot = path.join(root, "runtime");
    const lockPath = path.join(runtimeRoot, "dashboard.lock");
    await mkdir(runtimeRoot, { recursive: true });
    await writeFile(
      lockPath,
      `${JSON.stringify({
        commandName: "dashboard",
        pid: 99999999,
        token: "stale",
        acquiredAt: "2026-01-01T00:00:00.000Z",
      })}\n`,
      "utf8",
    );

    const lock = await acquireRuntimeCommandLock({
      runtimeRoot,
      commandName: "dashboard",
    });

    try {
      const payload = JSON.parse(await readFile(lockPath, "utf8")) as {
        pid: number;
        token: string;
      };
      expect(payload.pid).toBe(process.pid);
      expect(payload.token).toBe(lock.token);
    } finally {
      await lock.release();
    }
  });
});
