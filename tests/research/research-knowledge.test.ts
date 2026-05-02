import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { describe, expect, test } from "vitest";

import {
  ingestResearchKnowledge,
  selectRelevantResearchContext,
} from "../../src/research/research-knowledge.js";
import { resolveKnowledgePaths } from "../../src/state/knowledge-paths.js";

const testEnv = {
  projectRoot: process.cwd(),
  workspaceRoot: "",
  stateRoot: "",
  researchTargetId: "qqq-120m-af",
  openAiAuthMode: "oauth_proxy" as const,
  openAiBaseUrl: "http://127.0.0.1:10531/v1",
  openAiModel: "gpt-5.4",
  openAiApiKey: undefined,
  openAiRequestTimeoutMs: 180_000,
  openAiMaxRetries: 3,
  openAiOauthProxyCommand: "npx openai-oauth",
  openAiOauthAuthFilePath: undefined,
  mutationStaticResponsePath: undefined,
  evaluationUseMock: false,
  evaluationExecutor: "tradingview-desktop-cdp" as const,
  promotionVerificationExecutor: "none" as const,
  tradingViewDesktopPath: undefined,
  tradingViewCdpUrl: undefined,
  pineEditorTimeoutMs: 15_000,
  tradingViewCdpCommandTimeoutMs: 8_000,
  chartSymbol: "QQQ",
  chartTimeframe: "120",
  chartType: "candles",
  maxTrades: 50,
  researchRefreshEveryTasks: 3,
  alphaXivMcpUrl: "https://api.alphaxiv.org/mcp/v1",
  alphaXivMcpBearerToken: undefined,
  alphaXivAuthFilePath: undefined,
  alphaXivSessionFilePath: undefined,
  tvCalibrationMode: "live" as const,
  autonomousBootstrapMode: "disabled" as const,
  autoProcessCalibration: false,
  calibrationBudget: 1,
  calibrationTimeoutMs: 30_000,
};

describe("research knowledge ingestion", () => {
  test("ingests structured JSON knowledge from a file and selects relevant research context", async () => {
    const workspaceRoot = await mkdtemp(path.join(tmpdir(), "af-research-knowledge-"));
    const knowledgeFilePath = path.join(workspaceRoot, "weak-exit-note.json");
    await writeFile(
      knowledgeFilePath,
      JSON.stringify(
        {
          summary: "Research note focused on weak exits during downtrends.",
          problemTags: ["weak_exit", "trend_down"],
          strategyTags: ["exit_tightening"],
          insights: [
            {
              insightId: "insight-1",
              summary: "Weak exits should trigger faster during downtrend continuation.",
              rationale: "Losses deepen when longs remain open despite regime confirmation.",
              suggestedMutation:
                "Tighten long exits when trend_down persists and momentum weakens after entry.",
              relatedFailurePatterns: ["weak_exit", "trend_down"],
              keywords: ["exit", "trend", "drawdown"],
              confidence: 0.88,
            },
          ],
        },
        null,
        2,
      ),
      "utf8",
    );

    const records = await ingestResearchKnowledge({
      workspaceRoot,
      env: {
        ...testEnv,
        workspaceRoot,
        stateRoot: path.join(workspaceRoot, "state", "pi-autoresearch"),
      },
      filePath: knowledgeFilePath,
      problemTags: ["drawdown_control"],
      strategyTags: ["regime_filter"],
    });

    expect(records).toHaveLength(1);
    expect(records[0]?.sourceType).toBe("manual_json");
    expect(records[0]?.problemTags).toContain("weak_exit");
    expect(records[0]?.strategyTags).toContain("regime_filter");

    const context = await selectRelevantResearchContext({
      workspaceRoot,
      recentFailures: ["hard_gate_fail"],
      lossHotZones: ["trend_down:weak_exit"],
      repairPriorities: ["Tighten exit behavior when losing trades continue into deeper drawdown."],
      objectiveLabel: "QQQ 120m",
    });

    expect(context.status).toBe("available");
    expect(context.relevantKnowledgeIds).toContain(records[0]?.knowledgeId);
    expect(context.insights[0]?.suggestedMutation).toContain("Tighten long exits");

    const knowledgePaths = resolveKnowledgePaths(path.join(workspaceRoot, "state", "pi-autoresearch"));
    expect(records[0]?.rawTextPath).toBeTruthy();
    const rawText = await readFile(records[0]!.rawTextPath!, "utf8");
    expect(rawText).toContain('"summary": "Research note focused on weak exits during downtrends."');
    expect(knowledgePaths.researchKnowledgePath).toContain("research-knowledge.jsonl");
  });

  test("ingests inline text content without requiring a file path", async () => {
    const workspaceRoot = await mkdtemp(path.join(tmpdir(), "af-research-inline-"));
    const records = await ingestResearchKnowledge({
      workspaceRoot,
      env: {
        ...testEnv,
        workspaceRoot,
        stateRoot: path.join(workspaceRoot, "state", "pi-autoresearch"),
      },
      title: "Inline structured note",
      sourceType: "manual_text",
      rawText: JSON.stringify({
        summary: "Inline note for late entries.",
        problemTags: ["late_entry"],
        strategyTags: ["entry_filter"],
        insights: [
          {
            insightId: "insight-1",
            summary: "Late entries should be avoided after short-term upside extension.",
            rationale: "Extended entries tend to mean-revert on QQQ 120m.",
            suggestedMutation: "Skip longs after short-window upside extension beyond EMA distance caps.",
            relatedFailurePatterns: ["late_entry", "overextended_entry"],
            keywords: ["extension", "ema", "entry"],
            confidence: 0.81,
          },
        ],
      }),
    });

    expect(records).toHaveLength(1);
    expect(records[0]?.title).toBe("Inline structured note");
    expect(records[0]?.insights[0]?.summary).toContain("Late entries");
  });
});
