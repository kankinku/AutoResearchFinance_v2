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
    const env = loadRuntimeEnvironment({
      cwd: workspaceRoot,
      overrides: {
        projectRoot: process.cwd(),
        workspaceRoot,
      },
    });

    expect(env.evaluationExecutor).toBe("local-backtest");
    expect(env.promotionVerificationExecutor).toBe("none");
    expect(env.autoProcessCalibration).toBe(false);
    expect(env.calibrationBudget).toBe(3);
    expect(env.mutationSchemaMode).toBe("strict");
    expect(env.researchTargetId).toBe("qqq-120m-af");
    expect(env.stateRoot).toBe(
      path.join(workspaceRoot, "state", "targets", "qqq-120m-af", "pi-autoresearch"),
    );
    expect(env.researchModeConfig).toEqual({
      mode: "continuous_improvement",
      source: "default",
    });
  });

  test("uses target-scoped state when a target override is provided", async () => {
    delete process.env.TRADINGVIEW_CHART_SYMBOL;
    delete process.env.TRADINGVIEW_CHART_TIMEFRAME;

    const workspaceRoot = await mkdtemp(path.join(tmpdir(), "af-runtime-btc-target-"));
    const env = loadRuntimeEnvironment({
      cwd: workspaceRoot,
      targetId: "btc-15m-af",
      overrides: {
        projectRoot: process.cwd(),
        workspaceRoot,
      },
    });

    expect(env.researchTargetId).toBe("btc-15m-af");
    expect(env.chartSymbol).toBe("BTCUSD");
    expect(env.chartTimeframe).toBe("15");
    expect(env.stateRoot).toBe(
      path.join(workspaceRoot, "state", "targets", "btc-15m-af", "pi-autoresearch"),
    );
  });

  test("does not treat cleanup-runtime target as a research target", async () => {
    const workspaceRoot = await mkdtemp(path.join(tmpdir(), "af-runtime-cleanup-target-"));
    const env = loadRuntimeEnvironment({
      argv: ["cleanup-runtime", "--target", "tradingview-cache"],
      cwd: workspaceRoot,
      overrides: {
        projectRoot: process.cwd(),
        workspaceRoot,
      },
    });

    expect(env.researchTargetId).toBe("qqq-120m-af");
  });

  test("rejects conflicting target and chart environment", async () => {
    process.env.TRADINGVIEW_CHART_SYMBOL = "BTCUSD";
    process.env.TRADINGVIEW_CHART_TIMEFRAME = "15";

    const workspaceRoot = await mkdtemp(path.join(tmpdir(), "af-runtime-chart-conflict-"));

    expect(() =>
      loadRuntimeEnvironment({
        cwd: workspaceRoot,
        targetId: "qqq-120m-af",
        overrides: {
          projectRoot: process.cwd(),
          workspaceRoot,
        },
      }),
    ).toThrow(/Chart symbol conflict/);
  });

  test("resolves research mode from CLI before environment", async () => {
    process.env.AF_RESEARCH_MODE = "continuous_improvement";
    process.env.AF_RESEARCH_CRITERION = "trade_count";

    const workspaceRoot = await mkdtemp(path.join(tmpdir(), "af-runtime-mode-"));
    const env = loadRuntimeEnvironment({
      argv: [
        "run-autonomous-loop",
        "--research-mode",
        "criterion_focus",
        "--criterion",
        "local_tv_parity",
      ],
      cwd: workspaceRoot,
      overrides: {
        projectRoot: process.cwd(),
        workspaceRoot,
        stateRoot: path.join(workspaceRoot, "state", "pi-autoresearch"),
      },
    });

    expect(env.researchModeConfig).toEqual({
      mode: "criterion_focus",
      criterion: "local_tv_parity",
      source: "cli",
    });
  });

  test("accepts TradingView web Playwright as an opt-in verification executor", async () => {
    process.env.AF_PROMOTION_VERIFICATION_EXECUTOR = "tradingview-web-playwright";
    process.env.TRADINGVIEW_WEB_CDP_URL = "http://127.0.0.1:9223";
    process.env.TRADINGVIEW_WEB_CHART_URL = "https://www.tradingview.com/chart/";

    const workspaceRoot = await mkdtemp(path.join(tmpdir(), "af-runtime-web-tv-"));
    const env = loadRuntimeEnvironment({
      cwd: workspaceRoot,
      overrides: {
        projectRoot: process.cwd(),
        workspaceRoot,
        stateRoot: path.join(workspaceRoot, "state", "pi-autoresearch"),
      },
    });

    expect(env.promotionVerificationExecutor).toBe("tradingview-web-playwright");
    expect(env.tradingViewWebCdpUrl).toBe("http://127.0.0.1:9223");
    expect(env.tradingViewWebChartUrl).toBe("https://www.tradingview.com/chart/");
  });

  test("infers indicator request mode from CLI indicator goal", async () => {
    process.env.AF_RESEARCH_MODE = "criterion_focus";
    process.env.AF_RESEARCH_CRITERION = "trade_count";

    const workspaceRoot = await mkdtemp(path.join(tmpdir(), "af-runtime-indicator-"));
    const env = loadRuntimeEnvironment({
      argv: [
        "generate-indicator",
        "--indicator-goal",
        "short-term peak confirmation",
      ],
      cwd: workspaceRoot,
      overrides: {
        projectRoot: process.cwd(),
        workspaceRoot,
        stateRoot: path.join(workspaceRoot, "state", "pi-autoresearch"),
      },
    });

    expect(env.researchModeConfig).toEqual({
      mode: "indicator_request",
      indicatorRequest: "short-term peak confirmation",
      source: "cli",
    });
  });

  test("rejects unknown research criteria", async () => {
    const workspaceRoot = await mkdtemp(path.join(tmpdir(), "af-runtime-bad-criterion-"));

    expect(() =>
      loadRuntimeEnvironment({
        argv: ["run-autonomous-loop", "--research-mode", "criterion_focus", "--criterion", "sharpe"],
        cwd: workspaceRoot,
        overrides: {
          projectRoot: process.cwd(),
          workspaceRoot,
          stateRoot: path.join(workspaceRoot, "state", "pi-autoresearch"),
        },
      }),
    ).toThrow(/Invalid criterion "sharpe"/);
  });

  test("rejects criteria outside criterion focus mode", async () => {
    const workspaceRoot = await mkdtemp(path.join(tmpdir(), "af-runtime-bad-combo-"));

    expect(() =>
      loadRuntimeEnvironment({
        argv: [
          "generate-indicator",
          "--research-mode",
          "indicator_request",
          "--criterion",
          "trade_count",
          "--indicator-goal",
          "short-term peak confirmation",
        ],
        cwd: workspaceRoot,
        overrides: {
          projectRoot: process.cwd(),
          workspaceRoot,
          stateRoot: path.join(workspaceRoot, "state", "pi-autoresearch"),
        },
      }),
    ).toThrow(/--criterion is only valid/);
  });

  test("rejects indicator request mode without a goal", async () => {
    const workspaceRoot = await mkdtemp(path.join(tmpdir(), "af-runtime-missing-goal-"));

    expect(() =>
      loadRuntimeEnvironment({
        argv: ["generate-indicator", "--research-mode", "indicator_request"],
        cwd: workspaceRoot,
        overrides: {
          projectRoot: process.cwd(),
          workspaceRoot,
          stateRoot: path.join(workspaceRoot, "state", "pi-autoresearch"),
        },
      }),
    ).toThrow(/indicator_request mode requires/);
  });
});
