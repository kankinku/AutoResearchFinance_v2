import { existsSync } from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { config as loadDotEnv } from "dotenv";
import { z } from "zod";

import {
  DEFAULT_RESEARCH_TARGET_ID,
  loadResearchTarget,
} from "../config/target-registry.js";
import { resolveKnowledgePaths } from "../state/knowledge-paths.js";
import {
  parseMutationSchemaMode,
} from "../policy/autoresearch-contract.js";
import {
  criterionKeySchema,
  evaluationExecutorNameSchema,
  researchModeConfigSchema,
  researchModeSchema,
  type CriterionKey,
  type EvaluationExecutorName,
  type ResearchMode,
  type ResearchModeConfig,
} from "../contracts/types.js";

loadDotEnv();

const runtimeEnvironmentSchema = z.object({
  projectRoot: z.string().min(1),
  workspaceRoot: z.string().min(1),
  stateRoot: z.string().min(1),
  traceRoot: z.string().min(1).optional(),
  artifactRoot: z.string().min(1).optional(),
  evidenceRoot: z.string().min(1).optional(),
  runtimeRoot: z.string().min(1).optional(),
  researchTargetId: z.string().min(1),
  openAiAuthMode: z.enum(["api_key", "oauth_proxy"]),
  openAiBaseUrl: z.string().min(1),
  openAiModel: z.string().min(1),
  openAiApiKey: z.string().optional(),
  openAiRequestTimeoutMs: z.number().int().positive().default(180_000),
  openAiMaxRetries: z.number().int().positive().default(3),
  openAiOauthProxyCommand: z.string().min(1),
  openAiOauthAuthFilePath: z.string().optional(),
  mutationStaticResponsePath: z.string().optional(),
  evaluationUseMock: z.boolean(),
  evaluationExecutor: evaluationExecutorNameSchema,
  promotionVerificationExecutor: z.enum([
    "none",
    "local-backtest",
    "tradingview-desktop-cdp",
    "tradingview-web-playwright",
  ]),
  tradingViewDesktopPath: z.string().optional(),
  tradingViewCdpUrl: z.string().optional(),
  tradingViewWebCdpUrl: z.string().optional(),
  tradingViewWebProfileDir: z.string().optional(),
  tradingViewWebChartUrl: z.string().optional(),
  tradingViewWebBrowserPath: z.string().optional(),
  tradingViewWebHeadless: z.boolean().optional(),
  pineEditorTimeoutMs: z.number().int().positive().default(15_000),
  tradingViewCdpCommandTimeoutMs: z.number().int().positive().default(8_000),
  chartSymbol: z.string().default("QQQ"),
  chartTimeframe: z.string().default("120"),
  chartType: z.string().default("candles"),
  maxTrades: z.number().int().positive().default(50),
  researchRefreshEveryTasks: z.number().int().positive().default(3),
  alphaXivMcpUrl: z.string().url().default("https://api.alphaxiv.org/mcp/v1"),
  alphaXivMcpBearerToken: z.string().optional(),
  alphaXivAuthFilePath: z.string().optional(),
  alphaXivSessionFilePath: z.string().optional(),
  tvCalibrationMode: z.enum(["live", "mock-recovered"]).default("live"),
  mutationSchemaMode: z.enum(["strict", "legacy-recovery-test-only"]).default("strict"),
  researchModeConfig: researchModeConfigSchema.default({
    mode: "continuous_improvement",
    source: "default",
  }),
  autonomousBootstrapMode: z.enum(["auto", "disabled"]).default("auto"),
  autoProcessCalibration: z.boolean().default(false),
  calibrationBudget: z.number().int().positive().default(3),
  calibrationTimeoutMs: z.number().int().positive().default(30_000),
  strategyReviewMode: z.enum(["off", "selective", "all"]).default("selective"),
  strategyReviewDeepBudget: z.number().int().nonnegative().default(3),
  strategyReviewMinConfidence: z.number().min(0).max(1).default(0.7),
  strategyReviewQuarantineConfidence: z.number().min(0).max(1).default(0.85),
});

export type RuntimeEnvironment = z.infer<typeof runtimeEnvironmentSchema>;

export interface RuntimePathOverrides {
  projectRoot?: string;
  workspaceRoot?: string;
  stateRoot?: string;
}

function parseEvaluationExecutor(value: string | undefined): EvaluationExecutorName {
  return evaluationExecutorNameSchema.safeParse(value).success
    ? (value as EvaluationExecutorName)
    : "local-backtest";
}

function parsePromotionVerificationExecutor(
  value: string | undefined,
): "none" | EvaluationExecutorName {
  if (
    value === "none" ||
    value === "local-backtest" ||
    value === "tradingview-desktop-cdp" ||
    value === "tradingview-web-playwright"
  ) {
    return value;
  }

  return "none";
}

export function loadRuntimeEnvironment(options?: {
  argv?: string[];
  cwd?: string;
  overrides?: RuntimePathOverrides;
}): RuntimeEnvironment {
  const argv = options?.argv ?? process.argv.slice(2);
  const cwd = options?.cwd ?? process.cwd();
  const cliOverrides = parseCliPathOverrides(argv);
  const projectRoot = path.resolve(
    options?.overrides?.projectRoot ??
      cliOverrides.projectRoot ??
      process.env.AF_PROJECT_ROOT ??
      resolveDefaultProjectRoot(),
  );
  const workspaceRoot = path.resolve(
    options?.overrides?.workspaceRoot ??
      cliOverrides.workspaceRoot ??
      process.env.AF_WORKSPACE_ROOT ??
      cwd,
  );
  const stateRoot = path.resolve(
    options?.overrides?.stateRoot ??
      cliOverrides.stateRoot ??
      process.env.AF_STATE_ROOT ??
      resolveStateRoot(workspaceRoot),
  );
  process.env.AF_PROJECT_ROOT = projectRoot;
  process.env.AF_WORKSPACE_ROOT = workspaceRoot;
  process.env.AF_STATE_ROOT = stateRoot;
  const knowledgePaths = resolveKnowledgePaths(stateRoot);
  const researchTargetId =
    process.env.AF_RESEARCH_TARGET_ID ?? DEFAULT_RESEARCH_TARGET_ID;
  const researchTarget = loadResearchTarget({
    projectRoot,
    workspaceRoot,
    targetId: researchTargetId,
  });
  const openAiAuthMode =
    process.env.OPENAI_AUTH_MODE === "api_key" ? "api_key" : "oauth_proxy";
  const defaultOpenAiBaseUrl =
    openAiAuthMode === "oauth_proxy"
      ? "http://127.0.0.1:10531/v1"
      : "https://api.openai.com/v1";
  const evaluationExecutor = parseEvaluationExecutor(
    process.env.PINE_EVALUATION_EXECUTOR ?? process.env.AF_EVALUATION_EXECUTOR,
  );
  const env = runtimeEnvironmentSchema.parse({
    projectRoot,
    workspaceRoot,
    stateRoot,
    traceRoot: knowledgePaths.tracesDir,
    artifactRoot: knowledgePaths.artifactDir,
    evidenceRoot: knowledgePaths.evidenceDir,
    runtimeRoot: knowledgePaths.runtimeDir,
    researchTargetId,
    openAiAuthMode,
    openAiBaseUrl: process.env.OPENAI_BASE_URL ?? defaultOpenAiBaseUrl,
    openAiModel: process.env.OPENAI_MODEL ?? "gpt-5.4",
    openAiApiKey: process.env.OPENAI_API_KEY,
    openAiRequestTimeoutMs: Number.parseInt(
      process.env.OPENAI_REQUEST_TIMEOUT_MS ?? "180000",
      10,
    ),
    openAiMaxRetries: Number.parseInt(
      process.env.OPENAI_MAX_RETRIES ?? "3",
      10,
    ),
    openAiOauthProxyCommand:
      process.env.OPENAI_OAUTH_PROXY_COMMAND ?? "npx openai-oauth",
    openAiOauthAuthFilePath: process.env.OPENAI_OAUTH_AUTH_FILE || undefined,
    mutationStaticResponsePath: process.env.MUTATION_STATIC_RESPONSE_PATH || undefined,
    evaluationUseMock:
      process.env.PINE_EVALUATION_USE_MOCK === "true" ||
      process.env.TRADINGVIEW_USE_MOCK === "true",
    evaluationExecutor,
    promotionVerificationExecutor: parsePromotionVerificationExecutor(
      process.env.PINE_PROMOTION_VERIFICATION_EXECUTOR ??
        process.env.AF_PROMOTION_VERIFICATION_EXECUTOR,
    ),
    tradingViewDesktopPath: process.env.TRADINGVIEW_DESKTOP_PATH || undefined,
    tradingViewCdpUrl: process.env.TRADINGVIEW_CDP_URL || undefined,
    tradingViewWebCdpUrl: process.env.TRADINGVIEW_WEB_CDP_URL || undefined,
    tradingViewWebProfileDir: process.env.TRADINGVIEW_WEB_PROFILE_DIR
      ? path.resolve(process.env.TRADINGVIEW_WEB_PROFILE_DIR)
      : undefined,
    tradingViewWebChartUrl: process.env.TRADINGVIEW_WEB_CHART_URL || undefined,
    tradingViewWebBrowserPath:
      process.env.TRADINGVIEW_WEB_BROWSER_PATH || undefined,
    tradingViewWebHeadless:
      process.env.TRADINGVIEW_WEB_HEADLESS == null
        ? undefined
        : process.env.TRADINGVIEW_WEB_HEADLESS === "true",
    pineEditorTimeoutMs: Number.parseInt(
      process.env.AF_PINE_EDITOR_TIMEOUT_MS ??
        process.env.TRADINGVIEW_PINE_EDITOR_TIMEOUT_MS ??
        "15000",
      10,
    ),
    tradingViewCdpCommandTimeoutMs: Number.parseInt(
      process.env.AF_TRADINGVIEW_CDP_COMMAND_TIMEOUT_MS ?? "8000",
      10,
    ),
    chartSymbol: process.env.TRADINGVIEW_CHART_SYMBOL ?? researchTarget.symbol,
    chartTimeframe:
      process.env.TRADINGVIEW_CHART_TIMEFRAME ?? researchTarget.timeframe,
    chartType: process.env.TRADINGVIEW_CHART_TYPE ?? "candles",
    maxTrades: Number.parseInt(process.env.TRADINGVIEW_MAX_TRADES ?? "50", 10),
    researchRefreshEveryTasks: Number.parseInt(
      process.env.RESEARCH_REFRESH_EVERY_TASKS ?? "3",
      10,
    ),
    alphaXivMcpUrl: process.env.ALPHAXIV_MCP_URL ?? "https://api.alphaxiv.org/mcp/v1",
    alphaXivMcpBearerToken: process.env.ALPHAXIV_MCP_BEARER_TOKEN || undefined,
    alphaXivAuthFilePath: process.env.ALPHAXIV_AUTH_FILE || undefined,
    alphaXivSessionFilePath: process.env.ALPHAXIV_SESSION_FILE || undefined,
    tvCalibrationMode:
      process.env.AF_TV_CALIBRATION_MODE === "mock-recovered"
        ? "mock-recovered"
        : "live",
    mutationSchemaMode: parseMutationSchemaMode(process.env.AF_MUTATION_SCHEMA_MODE),
    researchModeConfig: resolveResearchModeConfig({
      argv,
      env: process.env,
    }),
    autonomousBootstrapMode:
      process.env.AF_AUTONOMOUS_BOOTSTRAP_MODE === "disabled"
        ? "disabled"
        : "auto",
    autoProcessCalibration:
      process.env.AF_AUTO_PROCESS_CALIBRATION == null
        ? false
        : process.env.AF_AUTO_PROCESS_CALIBRATION === "true",
    calibrationBudget: Number.parseInt(
      process.env.AF_CALIBRATION_BUDGET ?? "3",
      10,
    ),
    calibrationTimeoutMs: Number.parseInt(
      process.env.AF_CALIBRATION_TIMEOUT_MS ?? "30000",
      10,
    ),
    strategyReviewMode: parseStrategyReviewMode(process.env.AF_STRATEGY_REVIEW_MODE),
    strategyReviewDeepBudget: Number.parseInt(
      process.env.AF_STRATEGY_REVIEW_DEEP_BUDGET ?? "3",
      10,
    ),
    strategyReviewMinConfidence: Number.parseFloat(
      process.env.AF_STRATEGY_REVIEW_MIN_CONFIDENCE ?? "0.70",
    ),
    strategyReviewQuarantineConfidence: Number.parseFloat(
      process.env.AF_STRATEGY_REVIEW_QUARANTINE_CONFIDENCE ?? "0.85",
    ),
  });

  assertNoLegacyExecutorConfig();
  assertNoMockPolicy(env);
  return env;
}

export function resolveResearchModeConfig(input: {
  argv?: string[];
  env?: NodeJS.ProcessEnv;
} = {}): ResearchModeConfig {
  const argv = input.argv ?? [];
  const env = input.env ?? process.env;
  const cliMode = readCliOption(argv, "--research-mode");
  const envMode = env.AF_RESEARCH_MODE;
  const cliCriterion = readCliOption(argv, "--criterion");
  const cliIndicatorRequest = readCliOption(argv, "--indicator-goal");
  const envCriterion = env.AF_RESEARCH_CRITERION;
  const envIndicatorRequest = env.AF_INDICATOR_GOAL;
  const source: ResearchModeConfig["source"] =
    cliMode || cliCriterion || cliIndicatorRequest
    ? "cli"
    : envMode || envCriterion || envIndicatorRequest
      ? "env"
      : "default";
  const mode = parseResearchMode(
    cliMode ??
      (cliIndicatorRequest
        ? "indicator_request"
        : envMode ?? (envIndicatorRequest ? "indicator_request" : "continuous_improvement")),
  );
  const criterion = parseOptionalCriterion(
    cliCriterion ?? (cliIndicatorRequest ? undefined : envCriterion),
  );
  const indicatorRequest =
    cliIndicatorRequest ?? (cliCriterion ? undefined : envIndicatorRequest) ?? undefined;

  if (criterion && mode !== "criterion_focus") {
    throw new Error("--criterion is only valid when research mode is criterion_focus.");
  }
  if (mode === "indicator_request" && criterion) {
    throw new Error("indicator_request mode cannot be combined with --criterion.");
  }
  if (mode === "indicator_request" && !indicatorRequest) {
    throw new Error("indicator_request mode requires --indicator-goal or AF_INDICATOR_GOAL.");
  }
  if (indicatorRequest && mode !== "indicator_request") {
    throw new Error("--indicator-goal is only valid when research mode is indicator_request.");
  }

  return researchModeConfigSchema.parse({
    mode,
    criterion,
    indicatorRequest,
    source,
  });
}

export function parseResearchMode(value: string): ResearchMode {
  const parsed = researchModeSchema.safeParse(value);
  if (!parsed.success) {
    throw new Error(
      `Invalid research mode "${value}". Expected continuous_improvement, criterion_focus, or indicator_request.`,
    );
  }
  return parsed.data;
}

export function parseOptionalCriterion(
  value: string | undefined,
): CriterionKey | undefined {
  if (value == null || value.trim() === "") {
    return undefined;
  }
  const parsed = criterionKeySchema.safeParse(value);
  if (!parsed.success) {
    throw new Error(
      `Invalid criterion "${value}". Expected one of ${criterionKeySchema.options.join(", ")}.`,
    );
  }
  return parsed.data;
}

function parseStrategyReviewMode(value: string | undefined): "off" | "selective" | "all" {
  if (value === "off" || value === "all") {
    return value;
  }
  return "selective";
}

export function assertNoMockPolicy(env: RuntimeEnvironment): void {
  if (env.evaluationUseMock) {
    throw new Error(
      "Mock Pine evaluation executors are forbidden. Remove PINE_EVALUATION_USE_MOCK=true or TRADINGVIEW_USE_MOCK=true from the environment.",
    );
  }

  if (env.mutationStaticResponsePath) {
    throw new Error(
      "Static mutation responses are forbidden. Remove MUTATION_STATIC_RESPONSE_PATH from the environment.",
    );
  }
}

function assertNoLegacyExecutorConfig(): void {
  if (process.env.TRADINGVIEW_DRIVER) {
    throw new Error(
      "TRADINGVIEW_DRIVER is no longer configurable. AF uses the built-in TradingView CDP executors.",
    );
  }

  if (process.env.TRADINGVIEW_HERMES_COMMAND || process.env.TRADINGVIEW_HERMES_CWD) {
    throw new Error(
      "Hermes is not part of AF. Remove TRADINGVIEW_HERMES_COMMAND and TRADINGVIEW_HERMES_CWD from the environment.",
    );
  }
}

export function resolveStateRoot(workspaceRoot: string): string {
  return path.join(workspaceRoot, "state", "pi-autoresearch");
}

export function resolveDefaultProjectRoot(): string {
  const moduleDir = path.dirname(fileURLToPath(import.meta.url));
  return (
    findProjectRootFrom(moduleDir) ?? path.resolve(moduleDir, "..", "..")
  );
}

function findProjectRootFrom(startDir: string): string | null {
  let current = path.resolve(startDir);
  const filesystemRoot = path.parse(current).root;

  while (true) {
    if (isProjectRootCandidate(current)) {
      return current;
    }
    if (current === filesystemRoot) {
      return null;
    }
    current = path.dirname(current);
  }
}

function isProjectRootCandidate(candidateRoot: string): boolean {
  return (
    existsSync(path.join(candidateRoot, "package.json")) &&
    existsSync(path.join(candidateRoot, "config")) &&
    existsSync(path.join(candidateRoot, "strategies", "source"))
  );
}

function parseCliPathOverrides(argv: string[]): RuntimePathOverrides {
  return {
    projectRoot: readCliOption(argv, "--project-root"),
    workspaceRoot: readCliOption(argv, "--workspace-root"),
    stateRoot: readCliOption(argv, "--state-root"),
  };
}

function readCliOption(argv: string[], flag: string): string | undefined {
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === flag) {
      return argv[index + 1];
    }
    if (value.startsWith(`${flag}=`)) {
      return value.slice(flag.length + 1);
    }
  }
  return undefined;
}
