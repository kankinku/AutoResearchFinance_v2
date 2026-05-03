import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, describe, expect, test } from "vitest";

import { loadRuntimeEnvironment } from "../../src/cli/runtime-config.js";

const originalEnv = { ...process.env };

afterEach(() => {
  process.env = { ...originalEnv };
});

describe("runtime config", () => {
  test("defaults external TradingView verification to opt-in manual paths", async () => {
    delete process.env.PINE_PROMOTION_VERIFICATION_EXECUTOR;
    delete process.env.AF_PROMOTION_VERIFICATION_EXECUTOR;
    delete process.env.AF_AUTO_PROCESS_CALIBRATION;
    delete process.env.AF_CALIBRATION_BUDGET;
    delete process.env.PINE_EVALUATION_EXECUTOR;
    delete process.env.AF_EVALUATION_EXECUTOR;

    const workspaceRoot = await mkdtemp(path.join(tmpdir(), "af-runtime-config-"));
    const stateRoot = path.join(workspaceRoot, "state", "pi-autoresearch");
    const env = loadRuntimeEnvironment({
      cwd: workspaceRoot,
      overrides: {
        projectRoot: process.cwd(),
        workspaceRoot,
        stateRoot,
      },
    });

    expect(env.evaluationExecutor).toBe("local-backtest");
    expect(env.promotionVerificationExecutor).toBe("none");
    expect(env.autoProcessCalibration).toBe(false);
    expect(env.calibrationBudget).toBe(3);
    expect(env.mutationSchemaMode).toBe("strict");
  });
});
