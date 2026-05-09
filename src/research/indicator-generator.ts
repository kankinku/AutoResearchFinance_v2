import { writeFile } from "node:fs/promises";
import path from "node:path";

import { z } from "zod";

import { ensureCandidateStudyTitle, extractStudyTitle } from "../strategy-source/pine-study.js";
import { type IndicatorArtifactRecord } from "../contracts/types.js";
import { type MutationLlmClient } from "../mutation/llm-client.js";
import { assertEditableResearchPath } from "../policy/autoresearch-contract.js";
import { appendIndicatorArtifactRecord } from "../state/jsonl-store.js";
import { createCandidateId, ensureDir, sha256 } from "../utils/fs.js";

const indicatorResponseSchema = z.object({
  indicatorSummary: z.string().min(1).optional(),
  pineScript: z.string().min(1),
  nextSteps: z.array(z.string()).default([]),
});

export interface IndicatorGenerationResult {
  record: IndicatorArtifactRecord;
  indicatorSummary: string | null;
  nextSteps: string[];
}

export async function generateIndicatorArtifact(input: {
  workspaceRoot: string;
  stateRoot: string;
  llmClient: MutationLlmClient;
  goal: string;
  outputPath?: string | null;
  sourceContext?: Record<string, unknown>;
  signal?: AbortSignal;
}): Promise<IndicatorGenerationResult> {
  const goal = input.goal.trim();
  if (!goal) {
    throw new Error("indicator goal is required.");
  }
  const sourceContext = input.sourceContext ?? {};
  const sourceContextHash = sha256(JSON.stringify({ goal, sourceContext }));
  if (!input.llmClient.generateIndicator) {
    throw new Error("Configured LLM client does not support indicator generation.");
  }
  const raw = await input.llmClient.generateIndicator({
    goal,
    context: sourceContext,
    signal: input.signal,
  });
  const parsed = parseIndicatorResponse(raw);
  const indicatorId = createCandidateId("ind");
  const normalized = ensureCandidateStudyTitle(parsed.pineScript, indicatorId);
  const validationIssues = validateIndicatorPine(normalized.source);
  if (validationIssues.length > 0) {
    throw new Error(
      `Indicator preflight failed: ${validationIssues.join("; ")}`,
    );
  }

  const pinePath = resolveIndicatorPath({
    workspaceRoot: input.workspaceRoot,
    outputPath: input.outputPath,
    indicatorId,
  });
  assertEditableResearchPath({
    workspaceRoot: input.workspaceRoot,
    targetPath: pinePath,
  });
  await ensureDir(path.dirname(pinePath));
  await writeFile(pinePath, normalized.source, "utf8");
  const record = await appendIndicatorArtifactRecord(input.stateRoot, {
    indicatorId,
    goal,
    pinePath,
    pineHash: sha256(normalized.source),
    studyTitle: normalized.studyTitle ?? extractStudyTitle(normalized.source),
    sourceContextHash,
    validationStatus: "valid",
    validationIssues: [],
  });
  return {
    record,
    indicatorSummary: parsed.indicatorSummary ?? null,
    nextSteps: parsed.nextSteps,
  };
}

export function parseIndicatorResponse(content: string): z.infer<typeof indicatorResponseSchema> {
  const payload = JSON.parse(extractJsonPayload(content));
  return indicatorResponseSchema.parse(payload);
}

export function validateIndicatorPine(source: string): string[] {
  const issues: string[] = [];
  if (!/^\s*\/\/@version=5/m.test(source)) {
    issues.push("Pine source must declare //@version=5.");
  }
  if (!/\bindicator\s*\(/i.test(source)) {
    issues.push("Pine source must declare indicator(...).");
  }
  if (/\bstrategy\s*\(/i.test(source)) {
    issues.push("Indicator source must not declare strategy(...).");
  }
  if (/\bstrategy\./i.test(source)) {
    issues.push("Indicator source must not use strategy namespace calls.");
  }
  if (/\bstrategy\.(entry|exit|order|close|close_all|cancel)\s*\(/i.test(source)) {
    issues.push("Indicator source must not use strategy order functions.");
  }
  if (!/\b(?:plot|plotshape|alertcondition)\s*\(/i.test(source)) {
    issues.push("Indicator source must include plot(), plotshape(), or alertcondition().");
  }
  if (/```|TODO|PLACEHOLDER/i.test(source)) {
    issues.push("Indicator source must not contain markdown fences or placeholder text.");
  }
  return issues;
}

function resolveIndicatorPath(input: {
  workspaceRoot: string;
  outputPath?: string | null;
  indicatorId: string;
}): string {
  if (input.outputPath) {
    return path.isAbsolute(input.outputPath)
      ? path.resolve(input.outputPath)
      : path.resolve(input.workspaceRoot, input.outputPath);
  }
  return path.join(
    input.workspaceRoot,
    "strategies",
    "indicators",
    `${input.indicatorId}.pine`,
  );
}

function extractJsonPayload(content: string): string {
  const trimmed = content.trim();
  if (trimmed.startsWith("{")) {
    return trimmed;
  }
  const codeBlockMatch = trimmed.match(/```json\s*([\s\S]*?)```/i);
  if (codeBlockMatch?.[1]) {
    return codeBlockMatch[1].trim();
  }
  const startIndex = trimmed.indexOf("{");
  const endIndex = trimmed.lastIndexOf("}");
  if (startIndex === -1 || endIndex <= startIndex) {
    throw new Error("Indicator response must contain a JSON payload.");
  }
  return trimmed.slice(startIndex, endIndex + 1);
}
