import { sha256 } from "../utils/fs.js";
import { parseAfStrategySpec, type AfStrategySpec } from "./schema.js";

export function canonicalAfStrategySpecJson(input: unknown): string {
  const spec = parseAfStrategySpec(input);
  return `${JSON.stringify(spec, null, 2)}\n`;
}

export function hashAfStrategySpec(input: unknown): string {
  return sha256(canonicalAfStrategySpecJson(input));
}

export function normalizeAfStrategySpec(input: unknown): AfStrategySpec {
  return parseAfStrategySpec(input);
}
