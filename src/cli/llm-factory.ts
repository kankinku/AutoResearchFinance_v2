import {
  createOpenAiCompatibleLlmClient,
  type MutationLlmClient,
} from "../mutation/llm-client.js";
import { ensureOpenAiAuthReady } from "./openai-oauth.js";
import { type RuntimeEnvironment } from "./runtime-config.js";

export async function createMutationLlmClient(
  env: RuntimeEnvironment,
): Promise<MutationLlmClient> {
  if (env.mutationStaticResponsePath) {
    throw new Error(
      "Static mutation responses are forbidden by project policy. Configure a live LLM endpoint instead.",
    );
  }

  await ensureOpenAiAuthReady(env);

  const liveClient = createOpenAiCompatibleLlmClient({
    baseUrl: env.openAiBaseUrl,
    model: env.openAiModel,
    apiKey: env.openAiApiKey,
    requestTimeoutMs: env.openAiRequestTimeoutMs,
  });

  return {
    generateMutation(input) {
      return withOpenAiAuthRetry(env, () => liveClient.generateMutation(input));
    },
    generateIndicator(input) {
      return withOpenAiAuthRetry(env, () => {
        if (!liveClient.generateIndicator) {
          throw new Error("Live LLM client does not support indicator generation.");
        }
        return liveClient.generateIndicator(input);
      });
    },
    generateConditionAblation(input) {
      return withOpenAiAuthRetry(env, () =>
        liveClient.generateConditionAblation(input),
      );
    },
    repairMutation(input) {
      return withOpenAiAuthRetry(env, () => liveClient.repairMutation(input));
    },
    reviewStrategy(input) {
      return withOpenAiAuthRetry(env, () => {
        if (!liveClient.reviewStrategy) {
          throw new Error("Live LLM client does not support strategy review.");
        }
        return liveClient.reviewStrategy(input);
      });
    },
  };
}

const RETRYABLE_OPENAI_PATTERNS = [
  /Failed to reach OpenAI-compatible endpoint/i,
  /OpenAI-compatible endpoint .* timed out/i,
  /fetch failed/i,
  /status 500/i,
  /status 429/i,
  /status 502/i,
  /status 503/i,
  /status 504/i,
];

async function withOpenAiAuthRetry<T>(
  env: RuntimeEnvironment,
  operation: () => Promise<T>,
): Promise<T> {
  let lastError: unknown;
  const maxAttempts = Math.max(1, env.openAiMaxRetries + 1);
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    try {
      return await operation();
    } catch (error) {
      lastError = error;
      const hasRemainingAttempts = attempt < maxAttempts - 1;
      if (!hasRemainingAttempts || !isRetryableOpenAiError(error)) {
        throw error;
      }
      await ensureOpenAiAuthReady(env, {
        forceRestartProxy: shouldForceRestartProxy(env, error),
      });
      await delay(resolveRetryDelayMs(attempt));
    }
  }

  throw lastError;
}

function isRetryableOpenAiError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error);
  return RETRYABLE_OPENAI_PATTERNS.some((pattern) => pattern.test(message));
}

const FORCE_PROXY_RESTART_PATTERNS = [
  /Failed to reach OpenAI-compatible endpoint/i,
  /OpenAI-compatible endpoint .* timed out/i,
  /fetch failed/i,
  /status 500/i,
  /status 502/i,
  /status 503/i,
  /status 504/i,
];

function shouldForceRestartProxy(
  env: RuntimeEnvironment,
  error: unknown,
): boolean {
  if (env.openAiAuthMode !== "oauth_proxy") {
    return false;
  }

  const message = error instanceof Error ? error.message : String(error);
  return FORCE_PROXY_RESTART_PATTERNS.some((pattern) => pattern.test(message));
}

function resolveRetryDelayMs(attempt: number): number {
  return Math.min(250 * (attempt + 1), 1_000);
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}
