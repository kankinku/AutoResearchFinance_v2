import {
  finalAnalysisSummarySchema,
  pineAnalysisSummarySchema,
  type ConditionContribution,
  type ConditionInventoryItem,
  type ConditionRole,
  type DecisionCode,
  type FinalAnalysisSummary,
  type LossAnalysisSummary,
  type MutationBrief,
  type PineAnalysisSummary,
} from "../contracts/types.js";
import { type PineGenerationIssue } from "../mutation/preflight.js";

const STUDY_DECLARATION_TITLE_PATTERN =
  /\b(strategy|indicator|study)\s*\(\s*(['"`])([^'"`]+)\2/;

export function analyzePineMutation(input: {
  baselineSource: string;
  candidateSource: string;
  candidateSummary: string;
  inventory: ConditionInventoryItem[];
  brief: MutationBrief;
  issues?: PineGenerationIssue[];
}): PineAnalysisSummary {
  const changedRoles = [...new Set(input.inventory.map((item) => item.role))];
  const changedLineCount = countChangedLines(input.baselineSource, input.candidateSource);
  const materialChangeDetected =
    normalizeSource(input.baselineSource) !== normalizeSource(input.candidateSource);
  const blockingIssueCodes = (input.issues ?? [])
    .filter((issue) => issue.severity === "blocking")
    .map((issue) => issue.code);
  const warningIssueCodes = (input.issues ?? [])
    .filter((issue) => issue.severity === "warning")
    .map((issue) => issue.code);
  const changeScope = classifyChangeScope({
    materialChangeDetected,
    changedRoles,
    conditionCount: input.inventory.length,
    changedLineCount,
  });
  const noOpRisk = classifyNoOpRisk({
    materialChangeDetected,
    changeScope,
    conditionCount: input.inventory.length,
    changedLineCount,
  });
  const hypothesisAlignment = classifyHypothesisAlignment(changedRoles, input.brief);
  const roleSummary = changedRoles.length > 0 ? changedRoles.join(", ") : "none";

  return pineAnalysisSummarySchema.parse({
    status: "available",
    summary: `Pine mutation touched ${roleSummary} logic across ${input.inventory.length} conditions with ${changeScope} scope. No-op risk is ${noOpRisk}.`,
    changeScope,
    noOpRisk,
    hypothesisAlignment,
    materialChangeDetected,
    conditionCount: input.inventory.length,
    changedLineCount,
    changedRoles,
    blockingIssueCodes,
    warningIssueCodes,
  });
}

export function synthesizeFinalAnalysis(input: {
  decision: DecisionCode;
  pineAnalysis: PineAnalysisSummary;
  lossAnalysis?: LossAnalysisSummary;
  conditionContributions?: ConditionContribution[];
}): FinalAnalysisSummary {
  const signals = [
    `Roles touched: ${input.pineAnalysis.changedRoles.join(", ") || "none"}`,
    `Scope: ${input.pineAnalysis.changeScope}`,
    `No-op risk: ${input.pineAnalysis.noOpRisk}`,
    `Hypothesis alignment: ${input.pineAnalysis.hypothesisAlignment}`,
    `Objective decision: ${input.decision}`,
  ];
  if (input.pineAnalysis.blockingIssueCodes.length > 0) {
    signals.push(
      `Preflight blockers: ${input.pineAnalysis.blockingIssueCodes.join(", ")}`,
    );
  }
  if (input.pineAnalysis.warningIssueCodes.length > 0) {
    signals.push(
      `Preflight warnings: ${input.pineAnalysis.warningIssueCodes.join(", ")}`,
    );
  }

  const contributionsFlat =
    (input.conditionContributions?.length ?? 0) > 0 &&
    input.conditionContributions!.every(
      (contribution) => Math.abs(contribution.scoreDelta) < 1e-9,
    );
  if (contributionsFlat) {
    signals.push("Condition contributions were flat across evaluated ablations.");
  }
  if (input.lossAnalysis?.repairPriorities[0]) {
    signals.push(`Loss priority: ${input.lossAnalysis.repairPriorities[0]}`);
  }

  if (
    input.decision === "accepted_improvement" ||
    input.decision === "verified_improvement" ||
    input.decision === "screening_improvement"
  ) {
    return finalAnalysisSummarySchema.parse({
      status: "available",
      verdict: "promising",
      summary:
        "The Pine mutation produced a structurally actionable change and improved the objective frontier.",
      signals,
      recommendedAction:
        "Keep this candidate in the frontier and bias the next mutation toward the strongest contributing conditions.",
    });
  }

  if (
    input.decision === "accepted_no_improvement" ||
    input.decision === "valid_no_promotion"
  ) {
    if (input.pineAnalysis.noOpRisk === "high" || contributionsFlat) {
      return finalAnalysisSummarySchema.parse({
        status: "available",
        verdict: "no_op_suspected",
        summary:
          "The Pine mutation evaluated cleanly but its measured leverage appears too small to move the frontier.",
        signals,
        recommendedAction:
          "Increase mutation magnitude or target a different role instead of iterating on the same low-leverage change.",
      });
    }

    return finalAnalysisSummarySchema.parse({
      status: "available",
      verdict: "neutral",
      summary:
        "The Pine mutation was structurally valid, but it did not outperform the accepted head on the current objective.",
      signals,
      recommendedAction:
        "Retarget the next mutation toward a higher-leverage role or loss zone before spending more ablation budget here.",
    });
  }

  if (input.decision === "backtest_empty") {
    return finalAnalysisSummarySchema.parse({
      status: "available",
      verdict: "insufficient",
      summary:
        "The Pine mutation compiled and applied, but the backtest did not produce enough tradable evidence for a reliable judgment.",
      signals,
      recommendedAction:
        input.lossAnalysis?.repairPriorities[0] ??
        "Restore tradable entries before drawing conclusions from this code path.",
    });
  }

  return finalAnalysisSummarySchema.parse({
    status: "available",
    verdict: "risky",
    summary:
      "The Pine mutation introduced execution or objective risk before it could become a reliable frontier candidate.",
    signals,
    recommendedAction:
      "Resolve the blocking execution or guardrail issue before spending more mutations on this branch.",
  });
}

function classifyChangeScope(input: {
  materialChangeDetected: boolean;
  changedRoles: ConditionRole[];
  conditionCount: number;
  changedLineCount: number;
}): PineAnalysisSummary["changeScope"] {
  if (!input.materialChangeDetected) {
    return "none";
  }

  if (
    input.changedRoles.length <= 1 &&
    input.conditionCount <= 2 &&
    input.changedLineCount <= 6
  ) {
    return "targeted";
  }

  if (
    input.changedRoles.length <= 2 &&
    input.conditionCount <= 4 &&
    input.changedLineCount <= 20
  ) {
    return "balanced";
  }

  return "broad";
}

function classifyNoOpRisk(input: {
  materialChangeDetected: boolean;
  changeScope: PineAnalysisSummary["changeScope"];
  conditionCount: number;
  changedLineCount: number;
}): PineAnalysisSummary["noOpRisk"] {
  if (!input.materialChangeDetected || input.conditionCount === 0) {
    return "high";
  }

  if (input.changeScope === "targeted" && input.conditionCount <= 1) {
    return "high";
  }

  if (input.changeScope === "targeted" || input.changedLineCount <= 6) {
    return "medium";
  }

  return "low";
}

function classifyHypothesisAlignment(
  changedRoles: ConditionRole[],
  brief: MutationBrief,
): PineAnalysisSummary["hypothesisAlignment"] {
  if (changedRoles.length === 0) {
    return "unclear";
  }

  const targetText = [
    brief.objective,
    brief.nextMutationDirection,
    ...brief.repairPriorities,
    ...brief.lossHotZones,
  ]
    .join(" ")
    .toLowerCase();

  const matchedRoles = changedRoles.filter((role) =>
    keywordsForRole(role).some((keyword) => targetText.includes(keyword)),
  );

  if (matchedRoles.length === 0) {
    return "unclear";
  }

  if (matchedRoles.length === changedRoles.length) {
    return "aligned";
  }

  return "partial";
}

function keywordsForRole(role: ConditionRole): string[] {
  switch (role) {
    case "entry":
      return ["entry", "trade frequency", "tradable", "late entry"];
    case "exit":
      return ["exit", "drawdown", "profit", "weak exit", "loser"];
    case "filter":
      return ["filter", "avoid", "reduce", "counter-trend", "overextended"];
    case "risk":
      return ["risk", "stop", "drawdown", "sizing", "guardrail"];
  }
}

function countChangedLines(left: string, right: string): number {
  const leftLines = normalizeSource(left).split("\n");
  const rightLines = normalizeSource(right).split("\n");
  const maxLength = Math.max(leftLines.length, rightLines.length);
  let changed = 0;
  for (let index = 0; index < maxLength; index += 1) {
    if ((leftLines[index] ?? "") !== (rightLines[index] ?? "")) {
      changed += 1;
    }
  }
  return changed;
}

function normalizeSource(source: string): string {
  const withoutTitleNoise = source.replace(
    STUDY_DECLARATION_TITLE_PATTERN,
    (_match, kind: string, quote: string) => `${kind}(${quote}TITLE${quote}`,
  );
  return withoutTitleNoise
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0 && !line.startsWith("//"))
    .join("\n");
}
