import path from "node:path";

import { z } from "zod";

import { ensureOpenAiAuthReady } from "../cli/openai-oauth.js";
import { loadAlphaXivAccessToken, loadAlphaXivSessionCookieHeader } from "../cli/alphaxiv-auth.js";
import { type RuntimeEnvironment } from "../cli/runtime-config.js";
import { type TaskRecord } from "../contracts/types.js";
import { appendIncidentRecord, readResearchKnowledgeRecords } from "../state/jsonl-store.js";
import { resolveKnowledgePaths } from "../state/knowledge-paths.js";
import { createCandidateId, writeJson } from "../utils/fs.js";
import { type CliMonitor } from "../cli/monitor.js";
import { ingestResearchKnowledge } from "./research-knowledge.js";
import { type AlphaXivMcpClient } from "./alphaxiv-mcp-client.js";

const researchRefreshPlanSchema = z.object({
  shouldRefresh: z.boolean(),
  statusSummary: z.string().min(1),
  knowledgeGaps: z.array(z.string()).default([]),
  searchQueries: z.array(z.string()).default([]),
  paperQuestion: z.string().default(""),
  ingestionTitle: z.string().default(""),
});

type ResearchRefreshPlan = z.infer<typeof researchRefreshPlanSchema>;

export interface BatchResearchRefreshResult {
  status: "ingested" | "skipped" | "failed";
  reason: string;
  artifactPath: string | null;
  knowledgeIds: string[];
  searchQueries: string[];
}

interface RunBatchResearchRefreshInput {
  workspaceRoot: string;
  stateRoot: string;
  env?: RuntimeEnvironment;
  batchId: string;
  tasks: TaskRecord[];
  refreshEveryTasks: number;
  monitor?: CliMonitor;
  createClient?: (input: {
    endpoint: string;
    bearerToken?: string;
    authFilePath?: string;
    sessionFilePath?: string;
  }) => Promise<AlphaXivMcpClient>;
}

async function createDefaultAlphaXivMcpClient(input: {
  endpoint: string;
  bearerToken?: string;
  authFilePath?: string;
  sessionFilePath?: string;
}): Promise<AlphaXivMcpClient> {
  const module = await import("./alphaxiv-mcp-client.js");
  const bearerToken =
    input.bearerToken ?? (await loadAlphaXivAccessToken(input.authFilePath).catch(() => null));
  return module.createAlphaXivMcpClient({
    endpoint: input.endpoint,
    bearerToken: bearerToken ?? undefined,
    sessionCookieHeader:
      (await loadAlphaXivSessionCookieHeader(input.sessionFilePath)) ?? undefined,
  });
}

export async function runBatchResearchRefresh(
  input: RunBatchResearchRefreshInput,
): Promise<BatchResearchRefreshResult> {
  if (!input.env) {
    return {
      status: "skipped",
      reason: "runtime_environment_unavailable",
      artifactPath: null,
      knowledgeIds: [],
      searchQueries: [],
    };
  }

  if (input.tasks.length < input.refreshEveryTasks) {
    return {
      status: "skipped",
      reason: "insufficient_tasks_for_refresh",
      artifactPath: null,
      knowledgeIds: [],
      searchQueries: [],
    };
  }

  const createClient = input.createClient ?? createDefaultAlphaXivMcpClient;
  const refreshId = createCandidateId("rrf");
  const artifactPath = path.join(
    resolveKnowledgePaths(input.stateRoot).researchDir,
    `research-refresh-${input.batchId}-${refreshId}.json`,
  );

  let mcpClient: AlphaXivMcpClient | null = null;
  let searchQueries: string[] = [];
  try {
    const plan = finalizeResearchRefreshPlan(
      await generateResearchRefreshPlan(input.env, input.workspaceRoot, input.tasks),
      input.batchId,
    );
    searchQueries = plan.searchQueries;
    await input.monitor?.log("research.refresh.plan", "Research refresh plan prepared", {
      shouldRefresh: plan.shouldRefresh,
      knowledgeGapCount: plan.knowledgeGaps.length,
      searchQueries: plan.searchQueries,
      paperQuestion: plan.paperQuestion,
      ingestionTitle: plan.ingestionTitle,
    });

    if (!plan.shouldRefresh || plan.searchQueries.length === 0) {
      return {
        status: "skipped",
        reason: "llm_decided_no_refresh_needed",
        artifactPath: null,
        knowledgeIds: [],
        searchQueries: plan.searchQueries,
      };
    }

    mcpClient = await createClient({
      endpoint: input.env.alphaXivMcpUrl,
      bearerToken: input.env.alphaXivMcpBearerToken,
      authFilePath: input.env.alphaXivAuthFilePath,
      sessionFilePath: input.env.alphaXivSessionFilePath,
    });

    const availableTools = await mcpClient.listToolNames();
    const retrievalTool = availableTools.includes("agentic_paper_retrieval")
      ? "agentic_paper_retrieval"
      : availableTools.includes("embedding_similarity_search")
      ? "embedding_similarity_search"
      : null;
    if (!retrievalTool) {
      throw new Error("alphaXiv MCP did not expose a supported retrieval tool.");
    }

    const retrievals: Array<{
      query: string;
      retrievalText: string;
      paperUrls: string[];
      answers: Array<{ url: string; answer: string }>;
    }> = [];

    for (const query of plan.searchQueries.slice(0, 2)) {
      await input.monitor?.log("research.refresh.query", "Running research query", {
        query,
      });

      const retrievalText = await mcpClient.callTool(retrievalTool, { query });
      const paperUrls = extractArxivUrls(retrievalText).slice(0, 2);
      const answers: Array<{ url: string; answer: string }> = [];

      for (const url of paperUrls) {
        try {
          const answer = await mcpClient.callTool("answer_pdf_queries", {
            url,
            query: plan.paperQuestion,
          });
          answers.push({ url, answer });
        } catch {
          // Keep retrieval-only evidence when targeted paper Q&A fails.
        }
      }

      retrievals.push({
        query,
        retrievalText,
        paperUrls,
        answers,
      });
    }

    const knowledgeRecords = await ingestResearchKnowledge({
      workspaceRoot: input.workspaceRoot,
      env: input.env,
      title: plan.ingestionTitle,
      sourceType: "alphaxiv_mcp",
      rawText: JSON.stringify(
        {
          batchId: input.batchId,
          statusSummary: plan.statusSummary,
          knowledgeGaps: plan.knowledgeGaps,
          searchQueries: plan.searchQueries,
          paperQuestion: plan.paperQuestion,
          retrievals,
        },
        null,
        2,
      ),
      problemTags: plan.knowledgeGaps,
    });

    await writeJson(artifactPath, {
      generatedAt: new Date().toISOString(),
      batchId: input.batchId,
      plan,
      retrievals,
      knowledgeIds: knowledgeRecords.map((record) => record.knowledgeId),
    });

    await input.monitor?.log("research.refresh.done", "Research refresh completed", {
      knowledgeIds: knowledgeRecords.map((record) => record.knowledgeId),
      searchQueries: plan.searchQueries,
    });

    return {
      status: "ingested",
      reason: "alphaxiv_research_ingested",
      artifactPath,
      knowledgeIds: knowledgeRecords.map((record) => record.knowledgeId),
      searchQueries: plan.searchQueries,
    };
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    const normalizedReason = normalizeResearchRefreshFailure(detail);
    await appendIncidentRecord(input.stateRoot, {
      runId: input.batchId,
      iteration: input.tasks.at(-1)?.iteration ?? input.tasks.length,
      candidateId: input.batchId,
      incidentType: "research_refresh_failed",
      detail,
    });

    await input.monitor?.log("research.refresh.failed", "Research refresh failed", {
      error: normalizedReason,
      detail,
    });

    return {
      status: "failed",
      reason: normalizedReason,
      artifactPath: null,
      knowledgeIds: [],
      searchQueries,
    };
  } finally {
    await mcpClient?.close();
  }
}

function normalizeResearchRefreshFailure(detail: string): string {
  if (/401|unauthorized|auth/i.test(detail)) {
    return "alphaxiv_oauth_required";
  }

  return detail;
}

async function generateResearchRefreshPlan(
  env: RuntimeEnvironment,
  workspaceRoot: string,
  tasks: TaskRecord[],
): Promise<ResearchRefreshPlan> {
  const existingKnowledge = await readResearchKnowledgeRecords(
    path.join(workspaceRoot, "state", "pi-autoresearch"),
  );

  const payload = {
    tasks: tasks.map((task) => ({
      taskNumber: task.taskNumber,
      status: task.status,
      objective: task.hypothesis.objective,
      nextMutationDirection: task.hypothesis.nextMutationDirection,
      recentFailures: task.hypothesis.recentFailures,
      decision: task.analysis.decision,
      score: task.analysis.score,
      hardGatesPassed: task.analysis.hardGatesPassed,
      softGuardrailBreached: task.analysis.softGuardrailBreached,
      nextMutationHints: task.analysis.nextMutationHints,
    })),
    existingKnowledge: existingKnowledge.slice(-10).map((record) => ({
      title: record.title,
      problemTags: record.problemTags,
      strategyTags: record.strategyTags,
    })),
  };

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
              "You are the AF research refresh planner.",
              "After every three tasks, inspect batch outcomes and decide whether AF needs more external knowledge.",
              "Return JSON only with keys:",
              "shouldRefresh: boolean,",
              "statusSummary: string,",
              "knowledgeGaps: string[],",
              "searchQueries: string[] (1-2 natural language queries for alphaXiv agentic_paper_retrieval),",
              "paperQuestion: string,",
              "ingestionTitle: string.",
              "Focus on actionable strategy logic, regime filters, entry timing, exit behavior, drawdown control, and low trade count recovery.",
              "Avoid duplicate search directions already covered by existingKnowledge unless the batch clearly regressed there again.",
            ].join(" "),
          },
          {
            role: "user",
            content: JSON.stringify(payload, null, 2),
          },
        ],
      }),
    });

    if (!result.ok) {
      throw new Error(
        `Research refresh planning failed with status ${result.status} at ${endpoint}.`,
      );
    }

    const body = (await result.json()) as {
      choices?: Array<{ message?: { content?: string | null } }>;
    };
    const content = body.choices?.[0]?.message?.content;
    if (!content) {
      throw new Error("Research refresh planning did not return content.");
    }
    return content;
  });

  return researchRefreshPlanSchema.parse(JSON.parse(response));
}

function finalizeResearchRefreshPlan(
  plan: ResearchRefreshPlan,
  batchId: string,
): ResearchRefreshPlan {
  const normalizedStatusSummary = plan.statusSummary.trim();
  const normalizedKnowledgeGaps = plan.knowledgeGaps
    .map((gap) => gap.trim())
    .filter(Boolean);
  const normalizedSearchQueries = plan.searchQueries
    .map((query) => query.trim())
    .filter(Boolean)
    .slice(0, 2);
  const fallbackGap = normalizedKnowledgeGaps[0] ?? "strategy improvement";
  const paperQuestion =
    plan.paperQuestion.trim() ||
    `What actionable strategy change addresses ${fallbackGap} for the current AF batch?`;
  const ingestionTitle =
    plan.ingestionTitle.trim() ||
    `Batch ${batchId} research refresh: ${normalizedStatusSummary}`;

  return {
    shouldRefresh: plan.shouldRefresh,
    statusSummary: normalizedStatusSummary,
    knowledgeGaps: normalizedKnowledgeGaps,
    searchQueries: normalizedSearchQueries,
    paperQuestion,
    ingestionTitle,
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
  return [
    /Failed to reach OpenAI-compatible endpoint/i,
    /fetch failed/i,
    /status 429/i,
    /status 502/i,
    /status 503/i,
    /status 504/i,
  ].some((pattern) => pattern.test(message));
}

function extractArxivUrls(text: string): string[] {
  const ids: string[] = text.match(/\b\d{4}\.\d{4,5}(?:v\d+)?\b/g) ?? [];
  return ids
    .filter((id, index) => ids.indexOf(id) === index)
    .map((id) => `https://arxiv.org/abs/${id}`);
}
