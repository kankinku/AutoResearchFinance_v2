import {
  parsedMutationResponseSchema,
  specPatchSchema,
  type ConditionInventoryItem,
  type ParsedMutationResponse,
  type SpecPatch,
} from "../contracts/types.js";
import { extractStudyTitle } from "../strategy-source/pine-study.js";
import { renderAfStrategySpecToPine } from "../strategy-spec/codegen-pine.js";
import { parseAfStrategySpec, type AfStrategySpec } from "../strategy-spec/schema.js";
import { afStrategySpecFromPine } from "../strategy-spec/to-af-config.js";
import { validateAfStrategySpec } from "../strategy-spec/validate.js";
import { assertNoFirewallPathReference } from "../policy/autoresearch-contract.js";

interface LooseConditionRecord {
  conditionId?: unknown;
  id?: unknown;
  role?: unknown;
  type?: unknown;
  summary?: unknown;
  description?: unknown;
  name?: unknown;
  pineLineHints?: unknown;
  lines?: unknown;
}

interface MutationParseOptions {
  strict: boolean;
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
  if (startIndex === -1 || endIndex === -1 || endIndex <= startIndex) {
    throw new Error("Mutation response must contain a JSON payload.");
  }

  return trimmed.slice(startIndex, endIndex + 1);
}

export function parseMutationResponse(content: string): ParsedMutationResponse {
  return parseMutationResponseWithRecovery(content);
}

export function parseMutationResponseStrict(
  content: string,
): ParsedMutationResponse {
  return parseMutationResponseInternal(content, {
    strict: true,
  });
}

export function parseMutationResponseWithRecovery(
  content: string,
): ParsedMutationResponse {
  return parseMutationResponseInternal(content, {
    strict: false,
  });
}

export function inferConditionInventoryFromPine(
  pineScript: string,
): ConditionInventoryItem[] {
  return inferInventoryFromPine(pineScript);
}

function parseMutationResponseInternal(
  content: string,
  options: MutationParseOptions,
): ParsedMutationResponse {
  const payload = JSON.parse(extractJsonPayload(content)) as Record<string, unknown>;
  const missingFields: string[] = [];
  const inferredFields: string[] = [];

  const strategySpec = resolveStrategySpec(payload, options, missingFields, inferredFields);
  const specPatch = resolveSpecPatch(payload, options, missingFields, inferredFields);
  let pineScript =
    strategySpec != null
      ? renderAfStrategySpecToPine(strategySpec)
      : options.strict
        ? pickString(payload, ["pineScript"])
        : pickString(payload, ["pineScript", "pine", "code", "source"]);
  if (!pineScript) {
    throw new Error(
      "Mutation response must include strategySpec; legacy Pine code is accepted only by recovery parsing.",
    );
  }
  if (options.strict && strategySpec == null) {
    throw new Error("Strict mutation response must include strategySpec.");
  }

  let candidateSummary = options.strict
    ? pickString(payload, ["candidateSummary"])
    : pickString(payload, ["candidateSummary", "summary", "candidate_summary"]);
  if (!candidateSummary) {
    missingFields.push("candidateSummary");
    if (options.strict) {
      throw new Error("Mutation response must include candidateSummary.");
    }
    candidateSummary = inferCandidateSummary(pineScript);
    inferredFields.push("candidateSummary");
  }

  let nextMutationHints = options.strict
    ? pickStringArray(payload, ["nextMutationHints"])
    : pickStringArray(payload, ["nextMutationHints", "next_hints", "hints"]);
  if (!Array.isArray(payload.nextMutationHints)) {
    missingFields.push("nextMutationHints");
    if (options.strict) {
      throw new Error("Mutation response must include nextMutationHints as an array.");
    }
    nextMutationHints = [];
    inferredFields.push("nextMutationHints");
  }

  const rawInventory = options.strict
    ? payload.inventory
    : payload.inventory ?? payload.conditions ?? payload.conditionInventory;
  if (!Array.isArray(rawInventory) || rawInventory.length === 0) {
    missingFields.push("inventory");
    if (options.strict) {
      throw new Error("Mutation response must include inventory with at least one condition.");
    }
  }

  const inventory = normalizeInventory(rawInventory, pineScript, options);
  if (inventory.length === 0 && options.strict) {
    throw new Error("Mutation response inventory must contain at least one valid condition.");
  }

  const inventorySource =
    !Array.isArray(rawInventory) || rawInventory.length === 0
      ? "inferred"
      : inferredFields.length > 0
        ? "mixed"
        : "llm";
  assertNoFirewallPathReference({
    candidateSummary,
    nextMutationHints,
    specPatch,
  });

  return parsedMutationResponseSchema.parse({
    candidateSummary,
    nextMutationHints,
    pineScript,
    strategySpec,
    specPatch,
    inventory,
    inventorySource,
    missingFields,
    inferredFields,
  });
}

function resolveSpecPatch(
  payload: Record<string, unknown>,
  options: MutationParseOptions,
  missingFields: string[],
  inferredFields: string[],
): SpecPatch | null {
  const rawPatch = payload.specPatch ?? payload.spec_patch;
  if (rawPatch == null) {
    missingFields.push("specPatch");
    if (options.strict) {
      throw new Error("Mutation response must include structured specPatch.");
    }
    inferredFields.push("specPatch");
    return buildRecoveredSpecPatch("legacy payload omitted specPatch");
  }

  const parsed = specPatchSchema.safeParse(rawPatch);
  if (parsed.success) {
    return parsed.data;
  }

  if (options.strict) {
    throw new Error(`specPatch failed validation: ${parsed.error.issues.map((issue) => issue.message).join(", ")}`);
  }

  inferredFields.push("specPatch");
  return buildRecoveredSpecPatch("legacy payload used non-structured specPatch");
}

function buildRecoveredSpecPatch(reason: string): SpecPatch {
  return {
    version: "af-spec-patch/v1",
    summary: "Recovered legacy mutation intent for test-only compatibility.",
    operations: [
      {
        path: "/entry",
        after: "legacy-recovered",
        reason,
      },
    ],
  };
}

function resolveStrategySpec(
  payload: Record<string, unknown>,
  options: MutationParseOptions,
  missingFields: string[],
  inferredFields: string[],
): AfStrategySpec | null {
  const rawSpec = payload.strategySpec ?? payload.strategy_spec ?? payload.spec;
  if (rawSpec != null) {
    const parsed = parseAfStrategySpec(rawSpec);
    const validation = validateAfStrategySpec(parsed);
    if (!validation.ok) {
      throw new Error(`strategySpec failed validation: ${validation.issues.join(", ")}`);
    }
    return parsed;
  }

  missingFields.push("strategySpec");
  if (options.strict) {
    return null;
  }

  const pineScript = pickString(payload, ["pineScript", "pine", "code", "source"]);
  if (!pineScript) {
    return null;
  }
  const recovered = afStrategySpecFromPine(pineScript);
  if (!recovered.spec) {
    return null;
  }
  inferredFields.push("strategySpec");
  return recovered.spec;
}

function normalizeInventory(
  rawInventory: unknown,
  pineScript: string,
  options: MutationParseOptions,
): ConditionInventoryItem[] {
  if (Array.isArray(rawInventory) && rawInventory.length > 0) {
    const normalized = rawInventory
      .map((entry, index) => normalizeInventoryEntry(entry, index, pineScript))
      .filter((entry): entry is ConditionInventoryItem => entry !== null);
    if (normalized.length > 0) {
      return normalized;
    }
  }

  if (options.strict) {
    return [];
  }

  return inferInventoryFromPine(pineScript);
}

function normalizeInventoryEntry(
  rawEntry: unknown,
  index: number,
  pineScript: string,
): ConditionInventoryItem | null {
  if (!isRecord(rawEntry)) {
    return null;
  }

  const entry = rawEntry as LooseConditionRecord;
  const role = normalizeRole(entry.role ?? entry.type);
  const summary =
    pickStringFromUnknown(entry.summary) ??
    pickStringFromUnknown(entry.description) ??
    pickStringFromUnknown(entry.name);
  if (!role || !summary) {
    return null;
  }

  const lineHints = normalizeLineHints(entry.pineLineHints ?? entry.lines);
  return {
    conditionId:
      pickStringFromUnknown(entry.conditionId) ??
      pickStringFromUnknown(entry.id) ??
      `${role}-${index + 1}`,
    role,
    summary,
    pineLineHints:
      lineHints.length > 0
        ? lineHints
        : inferLineHintsFromPine(summary, role, pineScript),
  };
}

function inferInventoryFromPine(pineScript: string): ConditionInventoryItem[] {
  const lines = pineScript.split(/\r?\n/);
  const candidates = lines
    .map((line, index) => {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("//")) {
        return null;
      }

      const role = inferRoleFromLine(trimmed);
      if (!role) {
        return null;
      }

      return {
        conditionId: `${role}-${slugify(trimmed.slice(0, 48)) || index + 1}`,
        role,
        summary: inferSummaryFromLine(trimmed),
        pineLineHints: [index + 1],
      } satisfies ConditionInventoryItem;
    })
    .filter((entry): entry is ConditionInventoryItem => entry !== null);

  if (candidates.length > 0) {
    return deduplicateInventory(candidates).slice(0, 5);
  }

  const studyTitle = extractStudyTitle(pineScript) ?? "generated strategy";
  return [
    {
      conditionId: "entry-generated",
      role: "entry",
      summary: `${studyTitle} generated entry logic`,
      pineLineHints: [1],
    },
  ];
}

function inferRoleFromLine(
  line: string,
): ConditionInventoryItem["role"] | null {
  const lower = line.toLowerCase();
  if (
    lower.includes("longentry") ||
    lower.includes("shortentry") ||
    lower.includes("entrysignal") ||
    lower.includes("strategy.entry")
  ) {
    return "entry";
  }

  if (
    lower.includes("longexit") ||
    lower.includes("shortexit") ||
    lower.includes("exitsignal") ||
    lower.includes("strategy.close")
  ) {
    return "exit";
  }

  if (
    lower.includes("strategy.exit") ||
    lower.includes("stopprice") ||
    lower.includes("trail") ||
    lower.includes("risk") ||
    lower.includes("limitprice")
  ) {
    return "risk";
  }

  if (
    lower.includes("filter") ||
    lower.includes("trend") ||
    lower.includes("momentum") ||
    lower.includes("pullback") ||
    lower.includes("rsi") ||
    lower.includes("adx")
  ) {
    return "filter";
  }

  return null;
}

function inferSummaryFromLine(line: string): string {
  const assignmentMatch = line.match(/^([a-zA-Z_][a-zA-Z0-9_]*)\s*=/);
  if (assignmentMatch?.[1]) {
    return `${assignmentMatch[1]} condition`;
  }

  return line.slice(0, 80);
}

function normalizeRole(value: unknown): ConditionInventoryItem["role"] | null {
  if (typeof value !== "string") {
    return null;
  }

  const lower = value.toLowerCase();
  if (lower === "entry" || lower === "exit" || lower === "filter" || lower === "risk") {
    return lower;
  }

  if (lower.includes("entry")) {
    return "entry";
  }

  if (lower.includes("exit")) {
    return "exit";
  }

  if (lower.includes("risk") || lower.includes("stop")) {
    return "risk";
  }

  if (lower.includes("filter")) {
    return "filter";
  }

  return null;
}

function normalizeLineHints(value: unknown): number[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .filter((entry): entry is number => typeof entry === "number" && Number.isInteger(entry))
    .filter((entry) => entry > 0);
}

function inferLineHintsFromPine(
  summary: string,
  role: ConditionInventoryItem["role"],
  pineScript: string,
): number[] {
  const lines = pineScript.split(/\r?\n/);
  const keywords = [
    ...summary
      .toLowerCase()
      .split(/[^a-z0-9]+/i)
      .filter((token) => token.length >= 3)
      .filter((token) => !COMMON_SUMMARY_TOKENS.has(token)),
    ...ROLE_KEYWORDS[role],
  ];

  const exactMatches = lines
    .map((line, index) => ({ line: line.toLowerCase(), lineNumber: index + 1 }))
    .filter(({ line }) => keywords.some((keyword) => line.includes(keyword)))
    .map(({ lineNumber }) => lineNumber);
  if (exactMatches.length > 0) {
    return [...new Set(exactMatches)].slice(0, 3);
  }

  const fallbackMatches = lines
    .map((line, index) => ({
      line: line.trim(),
      lineNumber: index + 1,
    }))
    .filter(({ line }) => inferRoleFromLine(line) === role)
    .map(({ lineNumber }) => lineNumber);

  return [...new Set(fallbackMatches)].slice(0, 3);
}

function pickString(
  payload: Record<string, unknown>,
  keys: string[],
): string | null {
  for (const key of keys) {
    const value = payload[key];
    if (typeof value === "string" && value.trim().length > 0) {
      return value;
    }
  }

  return null;
}

function pickStringArray(
  payload: Record<string, unknown>,
  keys: string[],
): string[] {
  for (const key of keys) {
    const value = payload[key];
    if (Array.isArray(value)) {
      return value
        .filter((entry): entry is string => typeof entry === "string")
        .map((entry) => entry.trim())
        .filter(Boolean);
    }
  }

  return [];
}

function pickStringFromUnknown(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value.trim() : null;
}

function inferCandidateSummary(pineScript: string): string {
  const studyTitle = extractStudyTitle(pineScript);
  return studyTitle ? `${studyTitle} mutation candidate` : "Generated Pine mutation candidate";
}

function deduplicateInventory(
  inventory: ConditionInventoryItem[],
): ConditionInventoryItem[] {
  const seen = new Set<string>();
  const deduplicated: ConditionInventoryItem[] = [];
  for (const item of inventory) {
    const key = `${item.role}:${item.summary}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    deduplicated.push(item);
  }
  return deduplicated;
}

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 32);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

const COMMON_SUMMARY_TOKENS = new Set([
  "and",
  "the",
  "with",
  "when",
  "that",
  "this",
  "above",
  "below",
  "long",
  "short",
  "entry",
  "exit",
  "risk",
  "filter",
  "condition",
  "based",
  "requires",
  "require",
]);

const ROLE_KEYWORDS: Record<ConditionInventoryItem["role"], string[]> = {
  entry: ["entry", "crossover", "crossunder", "signal"],
  exit: ["exit", "close", "crossunder", "crossover"],
  filter: ["filter", "trend", "momentum", "pullback", "rsi", "adx"],
  risk: ["strategy.exit", "stop", "trail", "limit", "risk", "atr"],
};
