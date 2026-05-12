import {
  COMPILE_FAILURE_CLASSES,
  type CompileFailureClass,
  type ExperimentRecord,
} from "../contracts/types.js";

const TITLE_TOO_LONG_PATTERNS = [
  /title.*too long/i,
  /script title.*too long/i,
];

type CompileFailureClassifier = {
  failureClass: CompileFailureClass;
  matches: (error: string) => boolean;
};

const COMPILE_FAILURE_CLASSIFIERS: readonly CompileFailureClassifier[] = [
  {
    failureClass: "input_time_requires_const_defval",
    matches: (error) =>
      /Cannot call ["']?input\.time["']?/i.test(error) &&
      /const int/i.test(error) &&
      /simple int/i.test(error),
  },
  {
    failureClass: "undeclared_identifier",
    matches: (error) => /Undeclared identifier/i.test(error),
  },
  {
    failureClass: "qty_percent_argument",
    matches: (error) => /qty_percent/i.test(error),
  },
  {
    failureClass: "unsupported_ta_sum",
    matches: (error) =>
      /Could not find function or function reference 'ta\.sum'/i.test(error),
  },
  {
    failureClass: "function_mutates_global",
    matches: (error) => /Cannot modify global variable/i.test(error),
  },
  {
    failureClass: "title_too_long",
    matches: (error) =>
      TITLE_TOO_LONG_PATTERNS.some((pattern) => pattern.test(error)),
  },
  {
    failureClass: "na_type_assignment",
    matches: (error) => /NA type cannot be assigned/i.test(error),
  },
  {
    failureClass: "missing_local_code_block",
    matches: (error) => /structure is missing a local code block/i.test(error),
  },
  {
    failureClass: "missing_pine_side_effect",
    matches: (error) =>
      /strategy must contain at least one/i.test(error) &&
      /plot\*\(\)|strategy\.\*\(\)|barcolor|bgcolor|hline|drawing/i.test(error),
  },
  {
    failureClass: "ta_sma_scope_consistency",
    matches: (error) =>
      /ta\.sma/i.test(error) &&
      /called on each calculation/i.test(error) &&
      /ternary operator|scope/i.test(error),
  },
  {
    failureClass: "leading_indented_statement",
    matches: (error) =>
      /You should not start a new statement with an indent/i.test(error),
  },
];

export function classifyCompileFailure(
  error: string,
): CompileFailureClass | null {
  return (
    COMPILE_FAILURE_CLASSIFIERS.find((classifier) =>
      classifier.matches(error),
    )?.failureClass ?? null
  );
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
  const counts = Object.fromEntries(
    COMPILE_FAILURE_CLASSES.map((failureClass) => [failureClass, 0]),
  ) as Record<CompileFailureClass, number>;

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
