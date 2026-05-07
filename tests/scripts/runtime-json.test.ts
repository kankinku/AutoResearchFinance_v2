import { execFile } from "node:child_process";
import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

import { describe, expect, test } from "vitest";

const execFileAsync = promisify(execFile);
const projectRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
);

describe("runtime-json PowerShell helper", () => {
  test.skipIf(process.platform !== "win32")(
    "writes heartbeat JSON through temp file replacement",
    async () => {
      const root = await mkdtemp(path.join(tmpdir(), "af-atomic-json-"));
      const outputPath = path.join(root, "heartbeat.json");
      const scriptPath = path.join(projectRoot, "scripts", "runtime-json.ps1");
      const command = [
        `. '${escapePowerShellSingleQuoted(scriptPath)}'`,
        `Write-AtomicJson -LiteralPath '${escapePowerShellSingleQuoted(outputPath)}' -Value @{status='running'; iteration=1}`,
        `Write-AtomicJson -LiteralPath '${escapePowerShellSingleQuoted(outputPath)}' -Value @{status='sleeping'; iteration=2}`,
      ].join("; ");

      await execFileAsync("powershell", [
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        command,
      ]);

      const payload = JSON.parse(await readFile(outputPath, "utf8"));
      expect(payload).toEqual({ status: "sleeping", iteration: 2 });
    },
  );
});

function escapePowerShellSingleQuoted(value: string): string {
  return value.replaceAll("'", "''");
}
