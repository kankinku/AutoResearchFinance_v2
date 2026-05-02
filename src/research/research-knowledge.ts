import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";

import { PDFParse } from "pdf-parse";

import {
  mutationResearchContextSchema,
  researchKnowledgeRecordSchema,
  type MutationResearchContext,
  type ResearchInsight,
  type ResearchKnowledgeRecord,
  type ResearchKnowledgeSourceType,
} from "../contracts/types.js";
import { type RuntimeEnvironment } from "../cli/runtime-config.js";
import {
  appendResearchKnowledgeRecord,
  readResearchKnowledgeRecords,
} from "../state/jsonl-store.js";
import { resolveKnowledgePaths } from "../state/knowledge-paths.js";
import { createCandidateId, ensureDir, sha256 } from "../utils/fs.js";
import { synthesizeResearchKnowledge } from "./knowledge-synthesizer.js";

export async function ingestResearchKnowledge(input: {
  workspaceRoot: string;
  env: RuntimeEnvironment;
  filePath?: string;
  rawText?: string;
  title?: string;
  sourceType?: ResearchKnowledgeSourceType;
  sourceUrl?: string | null;
  problemTags?: string[];
  strategyTags?: string[];
}): Promise<ResearchKnowledgeRecord[]> {
  const stateRoot = input.env.stateRoot;
  const paths = resolveKnowledgePaths(stateRoot);
  await ensureDir(paths.researchDir);

  if (!input.filePath && !input.rawText) {
    throw new Error("Provide --file or --text to ingest research knowledge.");
  }

  if (input.filePath) {
    const absolutePath = path.resolve(input.filePath);
    const sourceType = input.sourceType ?? inferSourceTypeFromPath(absolutePath);
    const fileBuffer = await readFile(absolutePath);
    const rawText = await extractResearchText(fileBuffer, sourceType);
    return [
      await buildAndPersistKnowledgeRecord({
        workspaceRoot: input.workspaceRoot,
        env: input.env,
        title:
          input.title ??
          path.basename(absolutePath, path.extname(absolutePath)),
        sourceType,
        sourcePath: absolutePath,
        sourceUrl: input.sourceUrl ?? null,
        rawText,
        problemTags: input.problemTags ?? [],
        strategyTags: input.strategyTags ?? [],
      }),
    ];
  }

  return [
    await buildAndPersistKnowledgeRecord({
      workspaceRoot: input.workspaceRoot,
      env: input.env,
      title: input.title ?? "Manual Research Note",
      sourceType: input.sourceType ?? "manual_text",
      sourcePath: null,
      sourceUrl: input.sourceUrl ?? null,
      rawText: input.rawText ?? "",
      problemTags: input.problemTags ?? [],
      strategyTags: input.strategyTags ?? [],
    }),
  ];
}

export async function selectRelevantResearchContext(input: {
  workspaceRoot: string;
  stateRoot?: string;
  recentFailures: string[];
  lossHotZones: string[];
  repairPriorities: string[];
  objectiveLabel: string;
}): Promise<MutationResearchContext> {
  const stateRoot =
    input.stateRoot ?? path.join(input.workspaceRoot, "state", "pi-autoresearch");
  const records = await readResearchKnowledgeRecords(stateRoot);
  if (records.length === 0) {
    return mutationResearchContextSchema.parse({
      status: "none",
      summary: "No external research knowledge has been attached yet.",
      matchedProblemTags: [],
      relevantKnowledgeIds: [],
      insights: [],
    });
  }

  const targetTokens = buildTargetTokens(input);
  const scoredInsights = records
    .flatMap((record) =>
      record.insights.map((insight) => ({
        record,
        insight,
        score: scoreInsight(record, insight, targetTokens),
      })),
    )
    .filter((entry) => entry.score > 0)
    .sort((left, right) => right.score - left.score || right.insight.confidence - left.insight.confidence)
    .slice(0, 4);

  if (scoredInsights.length === 0) {
    return mutationResearchContextSchema.parse({
      status: "none",
      summary: "Research knowledge exists but none matched the current failure pattern strongly enough.",
      matchedProblemTags: [],
      relevantKnowledgeIds: [],
      insights: [],
    });
  }

  const matchedProblemTags = scoredInsights
    .flatMap(({ record, insight }) => [...record.problemTags, ...insight.relatedFailurePatterns])
    .map(normalizeToken)
    .filter(uniqueOnly)
    .slice(0, 8);

  return mutationResearchContextSchema.parse({
    status: "available",
    summary: `Attached ${scoredInsights.length} research insight(s) relevant to the current failure pattern in ${input.objectiveLabel}.`,
    matchedProblemTags,
    relevantKnowledgeIds: scoredInsights
      .map(({ record }) => record.knowledgeId)
      .filter(uniqueOnly),
    insights: scoredInsights.map(({ record, insight }) => ({
      knowledgeId: record.knowledgeId,
      title: record.title,
      sourceType: record.sourceType,
      summary: insight.summary,
      suggestedMutation: insight.suggestedMutation,
      confidence: insight.confidence,
    })),
  });
}

async function buildAndPersistKnowledgeRecord(input: {
  workspaceRoot: string;
  env: RuntimeEnvironment;
  title: string;
  sourceType: ResearchKnowledgeSourceType;
  sourcePath: string | null;
  sourceUrl: string | null;
  rawText: string;
  problemTags: string[];
  strategyTags: string[];
}): Promise<ResearchKnowledgeRecord> {
  const stateRoot = input.env.stateRoot;
  const paths = resolveKnowledgePaths(stateRoot);
  const contentHash = sha256(input.rawText);
  const importedStructured = tryParseStructuredKnowledge(input.rawText);
  const knowledgeId = createCandidateId("rsk");
  const rawTextPath = path.join(paths.researchDir, `${knowledgeId}.txt`);
  await writeFile(rawTextPath, input.rawText, "utf8");

  const synthesized =
    importedStructured ??
    (await synthesizeResearchKnowledge(input.env, {
      title: input.title,
      sourceType: input.sourceType,
      rawText: input.rawText,
      sourcePath: input.sourcePath,
      sourceUrl: input.sourceUrl,
      problemTags: input.problemTags,
      strategyTags: input.strategyTags,
    }));

  const record = researchKnowledgeRecordSchema.parse({
    knowledgeId,
    sourceType: input.sourceType,
    title: input.title,
    sourcePath: input.sourcePath,
    sourceUrl: input.sourceUrl,
    contentHash,
    rawTextPath,
    summary: synthesized.summary,
    problemTags: normalizeStringList(synthesized.problemTags).concat(input.problemTags).filter(uniqueOnly),
    strategyTags: normalizeStringList(synthesized.strategyTags).concat(input.strategyTags).filter(uniqueOnly),
    insights: synthesized.insights.slice(0, 5),
  });

  return await appendResearchKnowledgeRecord(stateRoot, record);
}

function tryParseStructuredKnowledge(rawText: string): {
  summary: string;
  problemTags: string[];
  strategyTags: string[];
  insights: ResearchInsight[];
} | null {
  try {
    const parsed = JSON.parse(rawText) as Record<string, unknown>;
    if (typeof parsed.summary !== "string" || !Array.isArray(parsed.insights)) {
      return null;
    }

    return {
      summary: parsed.summary,
      problemTags: normalizeStringList(parsed.problemTags),
      strategyTags: normalizeStringList(parsed.strategyTags),
      insights: parsed.insights
        .map((insight, index) => ({
          insightId:
            typeof (insight as { insightId?: unknown })?.insightId === "string"
              ? ((insight as { insightId: string }).insightId || `insight-${index + 1}`)
              : `insight-${index + 1}`,
          summary: String((insight as { summary?: unknown })?.summary ?? ""),
          rationale: String((insight as { rationale?: unknown })?.rationale ?? ""),
          suggestedMutation: String(
            (insight as { suggestedMutation?: unknown })?.suggestedMutation ?? "",
          ),
          relatedFailurePatterns: normalizeStringList(
            (insight as { relatedFailurePatterns?: unknown })?.relatedFailurePatterns,
          ),
          keywords: normalizeStringList((insight as { keywords?: unknown })?.keywords),
          confidence:
            typeof (insight as { confidence?: unknown })?.confidence === "number"
              ? (insight as { confidence: number }).confidence
              : 0.5,
        }))
        .filter(
          (insight) =>
            insight.summary.trim().length > 0 &&
            insight.rationale.trim().length > 0 &&
            insight.suggestedMutation.trim().length > 0,
        ),
    };
  } catch {
    return null;
  }
}

async function extractResearchText(
  fileBuffer: Buffer,
  sourceType: ResearchKnowledgeSourceType,
): Promise<string> {
  if (sourceType === "manual_pdf") {
    const parser = new PDFParse({ data: new Uint8Array(fileBuffer) });
    try {
      const parsed = await parser.getText();
      return parsed.text.trim();
    } finally {
      await parser.destroy();
    }
  }

  return fileBuffer.toString("utf8").trim();
}

function inferSourceTypeFromPath(filePath: string): ResearchKnowledgeSourceType {
  const ext = path.extname(filePath).toLowerCase();
  if (ext === ".pdf") {
    return "manual_pdf";
  }
  if (ext === ".md") {
    return "manual_markdown";
  }
  if (ext === ".json") {
    return "manual_json";
  }
  return "manual_text";
}

function buildTargetTokens(input: {
  recentFailures: string[];
  lossHotZones: string[];
  repairPriorities: string[];
  objectiveLabel: string;
}): string[] {
  return [
    ...input.recentFailures,
    ...input.lossHotZones,
    ...input.repairPriorities,
    input.objectiveLabel,
  ]
    .flatMap((entry) => tokenize(entry))
    .filter(uniqueOnly);
}

function scoreInsight(
  record: ResearchKnowledgeRecord,
  insight: ResearchInsight,
  targetTokens: string[],
): number {
  const recordTokens = [
    ...record.problemTags,
    ...record.strategyTags,
    ...insight.relatedFailurePatterns,
    ...insight.keywords,
    insight.summary,
    insight.suggestedMutation,
  ]
    .flatMap((entry) => tokenize(entry))
    .filter(uniqueOnly);

  const overlap = recordTokens.filter((token) => targetTokens.includes(token)).length;
  return overlap * 2 + insight.confidence;
}

function tokenize(value: string): string[] {
  return value
    .split(/[^a-zA-Z0-9_]+/)
    .map(normalizeToken)
    .filter(Boolean);
}

function normalizeToken(value: string): string {
  return value.trim().toLowerCase();
}

function normalizeStringList(values: unknown): string[] {
  if (!Array.isArray(values)) {
    return [];
  }

  return values
    .map((value) => (typeof value === "string" ? value.trim() : ""))
    .filter(Boolean);
}

function uniqueOnly(value: string, index: number, items: string[]): boolean {
  return items.indexOf(value) === index;
}
