import { parseAfStrategyConfig } from "../automation/local-backtest/af-config.js";
import { renderAfStrategySpecToPine } from "./codegen-pine.js";
import { afStrategySpecSchema, type AfStrategySpec } from "./schema.js";
import { afStrategySpecToConfig } from "./to-af-config.js";

export interface AfStrategySpecValidationResult {
  ok: boolean;
  spec: AfStrategySpec | null;
  issues: string[];
}

export function validateAfStrategySpec(input: unknown): AfStrategySpecValidationResult {
  const parsed = afStrategySpecSchema.safeParse(input);
  if (!parsed.success) {
    return {
      ok: false,
      spec: null,
      issues: parsed.error.issues.map((issue) => issue.message),
    };
  }

  const pine = renderAfStrategySpecToPine(parsed.data);
  const compatibility = parseAfStrategyConfig(pine);
  const generatedConfig = afStrategySpecToConfig(parsed.data);
  const semanticIssues = [
    generatedConfig.L1 >= generatedConfig.L2 ? "event_levels_not_ordered" : null,
    generatedConfig.L2 >= generatedConfig.L3 ? "event_levels_not_ordered" : null,
  ].filter((issue): issue is string => issue != null);
  const issues = [...compatibility.issues, ...semanticIssues];

  return {
    ok: issues.length === 0,
    spec: parsed.data,
    issues,
  };
}
