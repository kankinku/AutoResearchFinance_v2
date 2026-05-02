import { type MutationBrief } from "../../contracts/types.js";
import { type ProblemEventRecord } from "../../contracts/autonomous.js";

export function buildSchemaRegenerateBrief(
  brief: MutationBrief,
  diagnosis: string,
): MutationBrief {
  const schemaHardeningSummary = [
    brief.schemaHardeningSummary,
    `Latest schema failure: ${diagnosis}`,
    "The next response must be strict JSON only with complete required fields.",
  ]
    .filter((value): value is string => typeof value === "string" && value.length > 0)
    .join(" ");

  return {
    ...brief,
    schemaHardeningSummary,
    nextMutationDirection: [
      "Schema regenerate mode is active.",
      "Emit a simpler, structurally complete mutation payload before pursuing additional optimization.",
      brief.nextMutationDirection,
    ].join(" "),
    forbiddenPatterns: Array.from(
      new Set([
        ...brief.forbiddenPatterns,
        "Do not omit any required JSON key.",
        "Do not return loose narrative text outside strict JSON.",
      ]),
    ),
  };
}

export function buildSchemaHardeningSummary(
  problemEvents: ProblemEventRecord[],
): string | undefined {
  const recentSchemaProblems = problemEvents
    .filter(
      (event) =>
        event.problemKind === "llm_schema_fail" ||
        event.problemKind === "mutation_generation_fail",
    )
    .slice(-3);
  if (recentSchemaProblems.length === 0) {
    return undefined;
  }

  return recentSchemaProblems
    .map((event) =>
      `${event.problemKind}${event.failureSignatureHash ? `:${event.failureSignatureHash}` : ""}`,
    )
    .join(" | ");
}
