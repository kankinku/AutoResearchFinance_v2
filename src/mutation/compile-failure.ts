import {
  type CompileFailureClass,
  type ExperimentRecord,
} from "../contracts/types.js";

const TITLE_TOO_LONG_PATTERNS = [
  /title.*too long/i,
  /script title.*too long/i,
];

export function classifyCompileFailure(
  error: string,
): CompileFailureClass | null {
  if (
    /Cannot call ["']?input\.time["']?/i.test(error) &&
    /const int/i.test(error) &&
    /simple int/i.test(error)
  ) {
    return "input_time_requires_const_defval";
  }

  if (/Undeclared identifier/i.test(error)) {
    return "undeclared_identifier";
  }

  if (/qty_percent/i.test(error)) {
    return "qty_percent_argument";
  }

  if (/Could not find function or function reference 'ta\.sum'/i.test(error)) {
    return "unsupported_ta_sum";
  }

  if (/Cannot modify global variable/i.test(error)) {
    return "function_mutates_global";
  }

  if (TITLE_TOO_LONG_PATTERNS.some((pattern) => pattern.test(error))) {
    return "title_too_long";
  }

  if (/NA type cannot be assigned/i.test(error)) {
    return "na_type_assignment";
  }

  if (/structure is missing a local code block/i.test(error)) {
    return "missing_local_code_block";
  }

  return null;
}

export function normalizeCompileFailureClasses(
  errors: string[],
): CompileFailureClass[] {
  const unique: CompileFailureClass[] = [];
  for (const error of errors) {
    const normalized = classifyCompileFailure(error);
    if (!normalized || unique.includes(normalized)) {
      continue;
    }
    unique.push(normalized);
  }
  return unique;
}

export function buildCompileFailureClassCounts(
  records: ExperimentRecord[],
): Record<CompileFailureClass, number> {
  const counts: Record<CompileFailureClass, number> = {
    undeclared_identifier: 0,
    qty_percent_argument: 0,
    unsupported_ta_sum: 0,
    function_mutates_global: 0,
    title_too_long: 0,
    na_type_assignment: 0,
    input_time_requires_const_defval: 0,
    missing_local_code_block: 0,
  };

  for (const record of records) {
    if (record.decision !== "compile_fail") {
      continue;
    }

    for (const failureClass of normalizeCompileFailureClasses(
      record.compile?.errors ?? [],
    )) {
      counts[failureClass] += 1;
    }
  }

  return counts;
}
