import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

import { describe, expect, test } from "vitest";

import { extractStudyTitle } from "../../src/automation/tradingview/pine-study.js";
import { createPineEvaluationExecutor } from "../../src/cli/executor-factory.js";
import { loadRuntimeEnvironment } from "../../src/cli/runtime-config.js";
import { initializeWorkspace } from "../../src/research/workspace.js";
import { resolveKnowledgePaths } from "../../src/state/knowledge-paths.js";
import { sha256, sha256Json } from "../../src/utils/fs.js";

const maybeRun = process.env.AF_ENABLE_TV_E2E === "1" ? test : test.skip;
const smokeRunTimestamp = new Date().toISOString().replace(/[:.]/g, "-");

function getSmokeRunDir(workspaceRoot: string): string {
  const stateRoot = path.join(workspaceRoot, "state", "pi-autoresearch");
  const knowledgePaths = resolveKnowledgePaths(stateRoot);
  return path.join(
    knowledgePaths.runtimeDir,
    "tradingview-smoke",
    smokeRunTimestamp,
  );
}

async function ensureSmokeRunDir(workspaceRoot: string): Promise<string> {
  const dirPath = getSmokeRunDir(workspaceRoot);
  await mkdir(dirPath, { recursive: true });
  return dirPath;
}

async function writeSmokeJson(
  workspaceRoot: string,
  fileName: string,
  value: unknown,
): Promise<void> {
  const dirPath = await ensureSmokeRunDir(workspaceRoot);
  await writeFile(
    path.join(dirPath, fileName),
    `${JSON.stringify(value, null, 2)}\n`,
    "utf8",
  );
}

async function writeSmokeText(
  workspaceRoot: string,
  fileName: string,
  value: string,
): Promise<void> {
  const dirPath = await ensureSmokeRunDir(workspaceRoot);
  await writeFile(path.join(dirPath, fileName), `${value}\n`, "utf8");
}

async function updateSmokeResult(
  workspaceRoot: string,
  key: "knownGood" | "knownBad",
  payload: Record<string, unknown>,
): Promise<void> {
  const dirPath = await ensureSmokeRunDir(workspaceRoot);
  const resultPath = path.join(dirPath, "smoke-result.json");
  let current: Record<string, unknown> = {};

  try {
    current = JSON.parse(await readFile(resultPath, "utf8")) as Record<string, unknown>;
  } catch {
    current = {};
  }

  current.generatedAt = new Date().toISOString();
  current.timestamp = smokeRunTimestamp;
  current[key] = payload;

  await writeFile(resultPath, `${JSON.stringify(current, null, 2)}\n`, "utf8");
}

async function writeFailureDiagnostic(
  workspaceRoot: string,
  stage: string,
  error: unknown,
  extra: Record<string, unknown> = {},
): Promise<void> {
  const diagnostic = {
    recordedAt: new Date().toISOString(),
    stage,
    message: error instanceof Error ? error.message : String(error),
    stack: error instanceof Error ? error.stack ?? null : null,
    ...extra,
  };
  await writeSmokeJson(workspaceRoot, "failure-diagnostic.json", diagnostic);
  await writeSmokeJson(workspaceRoot, "dom-snapshot.json", diagnostic);
}

describe("TradingView live e2e", () => {
  maybeRun("known-good candidate compiles, applies, and yields a raw report hash", async () => {
    const env = loadRuntimeEnvironment();
    const candidatePath = process.env.AF_TV_E2E_CANDIDATE_PATH;
    if (!candidatePath) {
      await writeFailureDiagnostic(
        env.workspaceRoot,
        "known-good-env",
        new Error("AF_TV_E2E_CANDIDATE_PATH must be set for TradingView E2E runs."),
      );
      await updateSmokeResult(env.workspaceRoot, "knownGood", {
        status: "failed",
        recordedAt: new Date().toISOString(),
        message: "AF_TV_E2E_CANDIDATE_PATH must be set for TradingView E2E runs.",
      });
      throw new Error("AF_TV_E2E_CANDIDATE_PATH must be set for TradingView E2E runs.");
    }

    await initializeWorkspace(env.workspaceRoot);
    const executor = createPineEvaluationExecutor(env, "tradingview-desktop-cdp");
    const pineSource = await readFile(candidatePath, "utf8");
    const studyTitle = extractStudyTitle(pineSource);
    const candidateSourceHash = sha256(pineSource);

    try {
      await executor.prepareChart({
        symbol: env.chartSymbol,
        timeframe: env.chartTimeframe,
        chartType: env.chartType,
      });
      await executor.updateStrategySource(pineSource);
      const compile = await executor.compileStrategy();
      expect(compile.ok).toBe(true);
      const apply = await executor.applyStrategy({
        expectedStudyTitle: studyTitle,
      });
      expect(apply.ok).toBe(true);
      const artifactBundle = await executor.readArtifactBundle({
        expectedStudyTitle: studyTitle,
        maxTrades: env.maxTrades,
      });
      const artifactBundleHash = sha256Json(artifactBundle);
      const rawReportSnapshot =
        (artifactBundle.state?.rawReportSnapshot as Record<string, unknown> | null | undefined) ??
        null;

      expect(compile.ok).toBe(true);
      expect(apply.ok).toBe(true);
      expect(artifactBundle.strategy).toBeTruthy();
      expect(artifactBundle.trades.length).toBeGreaterThan(0);
      expect(artifactBundle.equity.available).toBe(true);
      expect(artifactBundle.rawReportHash).toBeTruthy();
      expect(artifactBundleHash).toBeTruthy();

      await writeSmokeJson(env.workspaceRoot, "known-good.json", {
        recordedAt: new Date().toISOString(),
        candidatePath,
        studyTitle,
        compileOk: compile.ok,
        applyOk: apply.ok,
        metricCount: artifactBundle.strategy
          ? Object.keys(artifactBundle.strategy).length
          : 0,
        tradeCount: artifactBundle.trades.length,
        equityAvailable: artifactBundle.equity.available,
        rawReportHash: artifactBundle.rawReportHash ?? null,
        artifactBundleHash,
        attachDiagnostics:
          apply.attachDiagnostics ?? artifactBundle.attachDiagnostics ?? null,
      });
      await writeSmokeText(
        env.workspaceRoot,
        "candidate-source-hash.txt",
        candidateSourceHash,
      );
      await writeSmokeText(
        env.workspaceRoot,
        "raw-report-hash.txt",
        artifactBundle.rawReportHash ?? "",
      );
      await writeSmokeText(
        env.workspaceRoot,
        "artifact-bundle-hash.txt",
        artifactBundleHash,
      );
      await writeSmokeJson(
        env.workspaceRoot,
        "attach-diagnostics.json",
        apply.attachDiagnostics ?? artifactBundle.attachDiagnostics ?? null,
      );
      if (rawReportSnapshot) {
        await writeSmokeJson(
          env.workspaceRoot,
          "raw-report-snapshot.json",
          rawReportSnapshot,
        );
      }
      await updateSmokeResult(env.workspaceRoot, "knownGood", {
        status: "passed",
        recordedAt: new Date().toISOString(),
        candidatePath,
        compileOk: true,
        applyOk: true,
        rawReportHash: artifactBundle.rawReportHash ?? null,
        artifactBundleHash,
      });
    } catch (error) {
      await writeFailureDiagnostic(env.workspaceRoot, "known-good", error, {
        candidatePath,
        studyTitle,
      });
      await updateSmokeResult(env.workspaceRoot, "knownGood", {
        status: "failed",
        recordedAt: new Date().toISOString(),
        candidatePath,
        message: error instanceof Error ? error.message : String(error),
      });
      throw error;
    } finally {
      await executor.close?.();
    }
  });

  maybeRun("known-bad Pine source fails compile in the live TradingView surface", async () => {
    const env = loadRuntimeEnvironment();
    if (!process.env.AF_TV_E2E_CANDIDATE_PATH) {
      await writeFailureDiagnostic(
        env.workspaceRoot,
        "known-bad-env",
        new Error("AF_TV_E2E_CANDIDATE_PATH must be set for TradingView E2E runs."),
      );
      await updateSmokeResult(env.workspaceRoot, "knownBad", {
        status: "failed",
        recordedAt: new Date().toISOString(),
        message: "AF_TV_E2E_CANDIDATE_PATH must be set for TradingView E2E runs.",
      });
      throw new Error("AF_TV_E2E_CANDIDATE_PATH must be set for TradingView E2E runs.");
    }
    await initializeWorkspace(env.workspaceRoot);
    const executor = createPineEvaluationExecutor(env, "tradingview-desktop-cdp");

    try {
      await executor.prepareChart({
        symbol: env.chartSymbol,
        timeframe: env.chartTimeframe,
        chartType: env.chartType,
      });
      await executor.updateStrategySource("//@version=5\nstrategy('Bad TV E2E', overlay=true)\ninvalid_call(");
      const compile = await executor.compileStrategy();
      await writeSmokeJson(env.workspaceRoot, "known-bad.json", {
        recordedAt: new Date().toISOString(),
        compileOk: compile.ok,
        compileErrors: compile.errors,
        promotionEligibleArtifact: false,
      });
      await updateSmokeResult(env.workspaceRoot, "knownBad", {
        status: compile.ok ? "failed" : "passed",
        recordedAt: new Date().toISOString(),
        compileOk: compile.ok,
        compileErrorCount: compile.errors.length,
      });
      expect(compile.ok).toBe(false);
      expect(compile.errors.length).toBeGreaterThan(0);
    } catch (error) {
      await writeFailureDiagnostic(env.workspaceRoot, "known-bad", error);
      await updateSmokeResult(env.workspaceRoot, "knownBad", {
        status: "failed",
        recordedAt: new Date().toISOString(),
        message: error instanceof Error ? error.message : String(error),
      });
      throw error;
    } finally {
      await executor.close?.();
    }
  });
});
