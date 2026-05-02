import { researchInsightSchema } from "../contracts/types.js";
import { ensureOpenAiAuthReady } from "../cli/openai-oauth.js";
import { type RuntimeEnvironment } from "../cli/runtime-config.js";

export interface ResearchKnowledgeSynthesis {
  summary: string;
  problemTags: string[];
  strategyTags: string[];
  insights: Array<{
    insightId: string;
    summary: string;
    rationale: string;
    suggestedMutation: string;
    relatedFailurePatterns: string[];
    keywords: string[];
    confidence: number;
  }>;
}

const RETRYABLE_OPENAI_PATTERNS = [
  /Failed to reach OpenAI-compatible endpoint/i,
  /fetch failed/i,
  /status 429/i,
  /status 502/i,
  /status 503/i,
  /status 504/i,
];

export async function synthesizeResearchKnowledge(
  env: RuntimeEnvironment,
  input: {
    title: string;
    sourceType: string;
    rawText: string;
    sourcePath?: string | null;
    sourceUrl?: string | null;
    problemTags: string[];
    strategyTags: string[];
  },
): Promise<ResearchKnowledgeSynthesis> {
  const response = await withOpenAiAuthRetry(env, async () => {
    await ensureOpenAiAuthReady(env);
    const endpoint = `${env.openAiBaseUrl.replace(/\/$/, "")}/chat/completions`;
    const result = await fetch(endpoint, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        ...(env.openAiApiKey ? { authorization: `Bearer ${env.openAiApiKey}` } : {}),
      },
      body: JSON.stringify({
        model: env.openAiModel,
        response_format: { type: "json_object" },
        messages: [
          {
            role: "system",
            content: [
              "You are extracting research knowledge for AF, an automated Pine strategy improvement system.",
              "Focus only on strategy logic, regime filters, entry timing, exit logic, risk controls, and failure modes relevant to QQQ 120m-style trading strategy research.",
              "Return JSON only with keys:",
              "summary: concise synthesis string,",
              "problemTags: string[],",
              "strategyTags: string[],",
              "insights: array of { insightId, summary, rationale, suggestedMutation, relatedFailurePatterns, keywords, confidence }.",
              "Keep problemTags and relatedFailurePatterns short and machine-usable, such as range_squeeze, weak_exit, late_entry, counter_trend_entry, overextended_entry, low_trade_count, drawdown_control.",
              "Keep suggestedMutation concrete and implementable in Pine.",
              "Return at most 5 insights.",
            ].join(" "),
          },
          {
            role: "user",
            content: JSON.stringify(
              {
                title: input.title,
                sourceType: input.sourceType,
                sourcePath: input.sourcePath ?? null,
                sourceUrl: input.sourceUrl ?? null,
                problemTags: input.problemTags,
                strategyTags: input.strategyTags,
                rawText: input.rawText.slice(0, 24000),
              },
              null,
              2,
            ),
          },
        ],
      }),
    });

    if (!result.ok) {
      throw new Error(
        `LLM request failed with status ${result.status} at ${endpoint}.`,
      );
    }

    const payload = (await result.json()) as {
      choices?: Array<{ message?: { content?: string | null } }>;
    };
    const content = payload.choices?.[0]?.message?.content;
    if (!content) {
      throw new Error("Research knowledge synthesis did not return content.");
    }
    return content;
  });

  const parsed = JSON.parse(response) as Partial<ResearchKnowledgeSynthesis>;
  return {
    summary:
      typeof parsed.summary === "string" && parsed.summary.trim().length > 0
        ? parsed.summary.trim()
        : `Research knowledge extracted from ${input.title}.`,
    problemTags: normalizeStringList(parsed.problemTags).concat(input.problemTags).filter(uniqueOnly),
    strategyTags: normalizeStringList(parsed.strategyTags).concat(input.strategyTags).filter(uniqueOnly),
    insights: Array.isArray(parsed.insights)
      ? parsed.insights
          .map((insight, index) =>
            researchInsightSchema.parse({
              insightId:
                typeof insight?.insightId === "string" && insight.insightId.trim().length > 0
                  ? insight.insightId
                  : `insight-${index + 1}`,
              summary: insight?.summary,
              rationale: insight?.rationale,
              suggestedMutation: insight?.suggestedMutation,
              relatedFailurePatterns: normalizeStringList(
                (insight as { relatedFailurePatterns?: unknown })?.relatedFailurePatterns,
              ),
              keywords: normalizeStringList((insight as { keywords?: unknown })?.keywords),
              confidence:
                typeof (insight as { confidence?: unknown })?.confidence === "number"
                  ? (insight as { confidence: number }).confidence
                  : 0.5,
            }),
          )
          .slice(0, 5)
      : [],
  };
}

async function withOpenAiAuthRetry<T>(
  env: RuntimeEnvironment,
  operation: () => Promise<T>,
): Promise<T> {
  let lastError: unknown;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      return await operation();
    } catch (error) {
      lastError = error;
      if (attempt > 0 || !isRetryableOpenAiError(error)) {
        throw error;
      }
      await ensureOpenAiAuthReady(env);
    }
  }
  throw lastError;
}

function isRetryableOpenAiError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error);
  return RETRYABLE_OPENAI_PATTERNS.some((pattern) => pattern.test(message));
}

function normalizeStringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((entry) => (typeof entry === "string" ? entry.trim() : ""))
    .filter(Boolean);
}

function uniqueOnly(value: string, index: number, items: string[]): boolean {
  return items.indexOf(value) === index;
}
