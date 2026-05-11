import {
  type CompileFailureClass,
  type MutationBrief,
  type ParsedMutationResponse,
} from "../contracts/types.js";

export interface PineGenerationIssue {
  code: string;
  ruleId: string;
  category: "syntax" | "compatibility" | "risk" | "placeholder" | "contract";
  severity: "blocking" | "warning";
  message: string;
  recommendation: string;
  lineHints: number[];
}

export interface PineGenerationInspection {
  issues: PineGenerationIssue[];
  blockingIssues: PineGenerationIssue[];
  warningIssues: PineGenerationIssue[];
}

interface PreflightRule {
  id: string;
  code: string;
  category: PineGenerationIssue["category"];
  severity: PineGenerationIssue["severity"];
  check(source: string): PineGenerationIssue[];
}

const PREVIEW_RULES: PreflightRule[] = [
  {
    id: "pine.require_version_pragma",
    code: "missing_version_pragma",
    category: "contract",
    severity: "blocking",
    check(source) {
      if (/^\s*\/\/\s*@version\s*=\s*5\b/m.test(source)) {
        return [];
      }
      return [
        createIssue({
          ruleId: "pine.require_version_pragma",
          code: "missing_version_pragma",
          category: "contract",
          severity: "blocking",
          message: "Pine source is missing //@version=5.",
          recommendation: "Add //@version=5 at the top of the script.",
          lineHints: [1],
        }),
      ];
    },
  },
  {
    id: "pine.require_strategy_declaration",
    code: "missing_strategy_declaration",
    category: "contract",
    severity: "blocking",
    check(source) {
      if (/\bstrategy\s*\(/i.test(source)) {
        return [];
      }
      return [
        createIssue({
          ruleId: "pine.require_strategy_declaration",
          code: "missing_strategy_declaration",
          category: "contract",
          severity: "blocking",
          message: "Generated Pine source does not declare strategy().",
          recommendation:
            "Emit a Pine strategy() declaration instead of indicator() or study().",
          lineHints: [1],
        }),
      ];
    },
  },
  createPatternRule({
    id: "pine.block_ta_adx",
    code: "unsupported_ta_adx",
    category: "compatibility",
    severity: "blocking",
    pattern: /\bta\.adx\s*\(/i,
    message:
      "Generated Pine source uses ta.adx(), which is blocked in the current Pine execution environment.",
    recommendation:
      "Replace ta.adx() with a Pine v5-safe manual DMI/ADX calculation or equivalent logic.",
  }),
  createPatternRule({
    id: "pine.block_qty_percent",
    code: "unsupported_strategy_entry_qty_percent",
    category: "compatibility",
    severity: "blocking",
    pattern: /\bstrategy\.(entry|order)\s*\([\s\S]*?\bqty_percent\s*=/i,
    message:
      "Generated Pine source uses qty_percent with strategy.entry/order(), which is unsupported in the current Pine execution environment.",
    recommendation:
      "Use strategy.percent_of_equity in strategy() defaults or compute qty explicitly and pass qty= instead of qty_percent=.",
  }),
  createPatternRule({
    id: "pine.block_ta_sum",
    code: "unsupported_ta_sum",
    category: "compatibility",
    severity: "blocking",
    pattern: /\bta\.sum\s*\(/i,
    message:
      "Generated Pine source uses ta.sum(), which has repeatedly failed in the current Pine execution environment.",
    recommendation:
      "Replace ta.sum() with a Pine v5-safe rolling accumulation alternative that compiles in the current executor.",
  }),
  createPatternRule({
    id: "pine.block_input_time_timestamp_defval",
    code: "input_time_timestamp_defval",
    category: "compatibility",
    severity: "blocking",
    pattern: /\binput\.time\s*\(\s*timestamp\s*\(/i,
    message:
      "Generated Pine source uses timestamp() as input.time() defval, but Pine requires a const int default.",
    recommendation:
      "Use a Unix millisecond integer literal for input.time(), for example input.time(1685539800000, \"backtestStartTime\"), instead of input.time(timestamp(...), ...).",
  }),
  createPatternRule({
    id: "pine.no_placeholder_logic",
    code: "placeholder_logic",
    category: "placeholder",
    severity: "blocking",
    pattern: /\b(todo|placeholder|your logic here|fill in|implement me)\b/i,
    message: "Generated Pine source still contains placeholder text.",
    recommendation: "Return compile-ready Pine logic without TODO or placeholder text.",
  }),
  createPatternRule({
    id: "pine.no_markdown_fence",
    code: "markdown_fence_leak",
    category: "contract",
    severity: "blocking",
    pattern: /```/,
    message: "Generated Pine source still contains markdown fences.",
    recommendation: "Return raw Pine code only inside pineScript, without markdown fences.",
  }),
  createPatternRule({
    id: "pine.warn_legacy_study",
    code: "legacy_study_declaration",
    category: "compatibility",
    severity: "warning",
    pattern: /\bstudy\s*\(/i,
    message: "Generated Pine source still uses legacy study().",
    recommendation:
      "Use strategy() for research candidates so the backtest surface stays consistent.",
  }),
  {
    id: "pine.warn_missing_trade_entry",
    code: "missing_trade_entry",
    category: "risk",
    severity: "warning",
    check(source) {
      if (/\bstrategy\.(entry|order)\s*\(/i.test(source)) {
        return [];
      }
      return [
        createIssue({
          ruleId: "pine.warn_missing_trade_entry",
          code: "missing_trade_entry",
          category: "risk",
          severity: "warning",
          message:
            "Generated Pine source does not appear to place any entries.",
          recommendation:
            "Ensure the script emits strategy.entry() or strategy.order() calls.",
          lineHints: [],
        }),
      ];
    },
  },
];

export function inspectGeneratedMutation(
  parsedMutation: ParsedMutationResponse,
  options?: {
    breakoutVariantDirective?: MutationBrief["breakoutVariantDirective"];
    recentCompileErrors?: string[];
    recentCompileFailureClasses?: CompileFailureClass[];
  },
): PineGenerationInspection {
  const source = parsedMutation.pineScript;
  const issues: PineGenerationIssue[] = [];
  const recentCompileFailureClasses = new Set(
    options?.recentCompileFailureClasses ?? [],
  );

  for (const rule of PREVIEW_RULES) {
    issues.push(...rule.check(source));
  }

  pushRecentUndeclaredIdentifierIssues(
    issues,
    source,
    options?.recentCompileErrors ?? [],
  );
  pushFunctionGlobalMutationIssues(issues, source);
  pushLongTitleIssues(issues, source, recentCompileFailureClasses);
  pushNaTypeAssignmentIssues(issues, source, recentCompileFailureClasses);
  pushMissingLocalCodeBlockIssues(issues, source);
  pushBreakoutVariantDirectiveIssues(
    issues,
    source,
    options?.breakoutVariantDirective,
  );

  return {
    issues,
    blockingIssues: issues.filter((issue) => issue.severity === "blocking"),
    warningIssues: issues.filter((issue) => issue.severity === "warning"),
  };
}

export function formatPreflightIssuesForRepair(
  issues: PineGenerationIssue[],
): string[] {
  return issues.map(
    (issue) =>
      `${issue.code}: ${issue.message} Recommended fix: ${issue.recommendation}`,
  );
}

export function repairTimeBoxedVariantPreflightIssues(
  parsedMutation: ParsedMutationResponse,
  issues: PineGenerationIssue[],
  directive: MutationBrief["breakoutVariantDirective"] | undefined,
): ParsedMutationResponse | null {
  if (!directive || directive.routeId !== "time_boxed_event_rotation") {
    return null;
  }
  const issueCodes = new Set(issues.map((issue) => issue.code));
  if (
    !issueCodes.has("time_boxed_sparse_event_source") &&
    !issueCodes.has("time_boxed_entry_overfiltered")
  ) {
    return null;
  }

  let source = parsedMutation.pineScript;
  let changed = false;
  if (issueCodes.has("time_boxed_sparse_event_source")) {
    const withFloorInput = ensureEventFloorInput(source);
    changed ||= withFloorInput !== source;
    source = withFloorInput;

    const withEarlyEvents = ensureEarlyEventBooleans(source);
    changed ||= withEarlyEvents !== source;
    source = withEarlyEvents;

    const withDenseWindowAliases = preferEarlyEventsInWindowAliases(source);
    changed ||= withDenseWindowAliases !== source;
    source = withDenseWindowAliases;

    const withDenseRawEvents = preferEarlyEventsInRawSources(source);
    changed ||= withDenseRawEvents !== source;
    source = withDenseRawEvents;

    const withOpenAgeWindows = removeTimeBoxedAgeLowerBounds(source);
    changed ||= withOpenAgeWindows !== source;
    source = withOpenAgeWindows;

    const withCanonicalEntryPath = forceCanonicalTimeBoxedEntryPath(source);
    changed ||= withCanonicalEntryPath !== source;
    source = withCanonicalEntryPath;
  }

  if (issueCodes.has("time_boxed_entry_overfiltered")) {
    const withSimplifiedEntryPass = simplifyTimeBoxedEntryPass(source);
    changed ||= withSimplifiedEntryPass !== source;
    source = withSimplifiedEntryPass;
  }

  if (!changed || source === parsedMutation.pineScript) {
    return null;
  }

  return {
    ...parsedMutation,
    candidateSummary: [
      parsedMutation.candidateSummary,
      "Deterministic preflight normalization injected dense early event-floor sources and simplified the time-boxed entry gate before local evaluation.",
    ].join(" "),
    nextMutationHints: [
      ...parsedMutation.nextMutationHints,
      "Keep eventFloorBars-driven earlyBullEvent/earlyBearEvent sources and avoid restoring sparse L1/L2/L3-only time-boxed gates.",
    ],
    pineScript: source,
  };
}

function ensureEventFloorInput(source: string): string {
  if (/\b(?:int\s+)?eventFloorBars\s*=\s*input\.int\s*\(/i.test(source)) {
    return source;
  }

  const hasGroupRot = /\bgroupRot\s*=/.test(source);
  const inputLine = hasGroupRot
    ? 'eventFloorBars = input.int(4, "Event Floor Bars", minval=2, maxval=5, group=groupRot)'
    : 'eventFloorBars = input.int(4, "Event Floor Bars", minval=2, maxval=5)';
  if (hasGroupRot) {
    return source.replace(
      /^(\s*groupRot\s*=\s*["'][^"']+["']\s*)$/m,
      `$1\n${inputLine}`,
    );
  }

  if (/^\s*newBullL1\s*=.*$/m.test(source)) {
    return source.replace(
      /^(\s*newBullL1\s*=.*)$/m,
      `${inputLine}\n$1`,
    );
  }
  if (/^\s*(?:int\s+)?bullEventRaw\s*=/m.test(source)) {
    return source.replace(/^(\s*(?:int\s+)?bullEventRaw\s*=.*)$/m, `${inputLine}\n$1`);
  }

  return source.replace(/^(\s*strategy\s*\(.*)$/m, `$1\n${inputLine}`);
}

function ensureEarlyEventBooleans(source: string): string {
  let next = source;
  next = upsertEventSourceAssignment(
    next,
    "bullEventFloor",
    "bullEventFloor = bull >= eventFloorBars",
  );
  next = upsertEventSourceAssignment(
    next,
    "bearEventFloor",
    "bearEventFloor = bear >= eventFloorBars",
  );
  next = upsertEventSourceAssignment(
    next,
    "earlyBullEvent",
    "earlyBullEvent = bullEventFloor and not nz(bullEventFloor[1], false)",
  );
  next = upsertEventSourceAssignment(
    next,
    "earlyBearEvent",
    "earlyBearEvent = bearEventFloor and not nz(bearEventFloor[1], false)",
  );
  return next;
}

function upsertEventSourceAssignment(
  source: string,
  identifier: string,
  line: string,
): string {
  const assignmentPattern = new RegExp(
    String.raw`^(\s*)(?:var\s+)?(?:bool\s+|int\s+|float\s+)?${escapeForRegex(identifier)}\s*=.*$`,
    "m",
  );
  if (assignmentPattern.test(source)) {
    return source.replace(assignmentPattern, `$1${line}`);
  }

  return insertBeforeEventRaw(source, line);
}

function insertBeforeEventRaw(source: string, line: string): string {
  if (/^\s*(?:bool\s+)?(?:earlyBullEvent|earlyBearEvent)\s*=/m.test(source)) {
    return source.replace(
      /^(\s*(?:bool\s+)?(?:earlyBullEvent|earlyBearEvent)\s*=.*)$/m,
      `${line}\n$1`,
    );
  }

  if (/^\s*(?:int\s+)?bullEventRaw\s*=/m.test(source)) {
    return source.replace(/^(\s*(?:int\s+)?bullEventRaw\s*=.*)$/m, `${line}\n$1`);
  }

  return insertBeforePrimaryEntryTrigger(source, line);
}

function preferEarlyEventsInRawSources(source: string): string {
  let next = source;
  next = next.replace(
    /^(\s*)(?:int\s+)?bullEventRaw\s*=.*$/m,
    "$1bullEventRaw = earlyBullEvent ? 1 : newBullConfirmed ? 4 : newBullStrong ? 3 : newBullCandidate ? 2 : newBullL1 ? 1 : 0",
  );
  next = next.replace(
    /^(\s*)(?:int\s+)?bearEventRaw\s*=.*$/m,
    "$1bearEventRaw = earlyBearEvent ? 1 : newBearConfirmed ? 4 : newBearStrong ? 3 : newBearCandidate ? 2 : newBearL1 ? 1 : 0",
  );
  return next;
}

function preferEarlyEventsInWindowAliases(source: string): string {
  let next = source;
  next = next.replace(
    /^(\s*)(?:bool\s+)?bullEarlyEvent\s*=.*$/m,
    "$1bullEarlyEvent = earlyBullEvent",
  );
  next = next.replace(
    /^(\s*)(?:bool\s+)?bearEarlyEvent\s*=.*$/m,
    "$1bearEarlyEvent = earlyBearEvent",
  );
  next = next.replace(
    /^(\s*)(?:bool\s+)?bullEventSource\s*=.*$/m,
    "$1bullEventSource = earlyBullEvent",
  );
  next = next.replace(
    /^(\s*)(?:bool\s+)?bearEventSource\s*=.*$/m,
    "$1bearEventSource = earlyBearEvent",
  );
  return next;
}

function removeTimeBoxedAgeLowerBounds(source: string): string {
  let next = source;
  next = next.replace(
    /^(\s*)(?:bool\s+)?bullAgeActive\s*=\s*not\s+na\(bullEventAge\)\s+and\s+bullEventAge\s*>=\s*(?:eventFloorBars|earlyEventFloorBars|[2-9]\d*)\s+and\s+bullEventAge\s*<=\s*([A-Za-z_]\w*)\s*$/m,
    "$1bullAgeActive = not na(bullEventAge) and bullEventAge <= $2",
  );
  next = next.replace(
    /^(\s*)(?:bool\s+)?bearAgeActive\s*=\s*not\s+na\(bearEventAge\)\s+and\s+bearEventAge\s*>=\s*(?:eventFloorBars|earlyEventFloorBars|[2-9]\d*)\s+and\s+bearEventAge\s*<=\s*([A-Za-z_]\w*)\s*$/m,
    "$1bearAgeActive = not na(bearEventAge) and bearEventAge <= $2",
  );
  next = next.replace(
    /^(\s*)(?:bool\s+)?postBullEventWindow\s*=\s*not\s+na\(([^)]+)\)\s+and\s+(\w+)\s*>=\s*(?:eventFloorBars|earlyEventFloorBars|[2-9]\d*)\s+and\s+\3\s*<=\s*([A-Za-z_]\w*)\s*$/m,
    "$1postBullEventWindow = not na($2) and $3 >= 0 and $3 <= $4",
  );
  next = next.replace(
    /^(\s*)(?:bool\s+)?postBearReboundWindow\s*=\s*not\s+na\(([^)]+)\)\s+and\s+(\w+)\s*>=\s*(?:eventFloorBars|earlyEventFloorBars|[2-9]\d*)\s+and\s+\3\s*<=\s*([A-Za-z_]\w*)\s*$/m,
    "$1postBearReboundWindow = not na($2) and $3 >= 0 and $3 <= $4",
  );
  return next;
}

function forceCanonicalTimeBoxedEntryPath(source: string): string {
  let next = ensureTimeBoxedWindowInputs(source);
  next = upsertAssignment(
    next,
    "bullEventAge",
    "bullEventAge = ta.barssince(earlyBullEvent)",
  );
  next = upsertAssignment(
    next,
    "bearEventAge",
    "bearEventAge = ta.barssince(earlyBearEvent)",
  );
  next = upsertAssignment(
    next,
    "bullAgeActive",
    "bullAgeActive = not na(bullEventAge) and bullEventAge <= bullContinueWindow",
  );
  next = upsertAssignment(
    next,
    "bearAgeActive",
    "bearAgeActive = not na(bearEventAge) and bearEventAge <= bearReboundWindow",
  );
  next = upsertAssignment(
    next,
    "postBullEventWindow",
    "postBullEventWindow = bullAgeActive",
  );
  next = upsertAssignment(
    next,
    "postBearReboundWindow",
    "postBearReboundWindow = bearAgeActive",
  );
  next = upsertAssignment(
    next,
    "primaryEntryTrigger",
    "primaryEntryTrigger = postBullEventWindow or postBearReboundWindow",
  );
  return ensureCanonicalTimeBoxedEntryGate(next);
}

function ensureTimeBoxedWindowInputs(source: string): string {
  let next = source;
  const hasGroupRot = /\bgroupRot\s*=/.test(next);
  if (!/\b(?:int\s+)?bullContinueWindow\s*=/.test(next)) {
    next = insertBeforeTimeBoxedWindowUsage(
      next,
      hasGroupRot
        ? 'bullContinueWindow = input.int(14, "Bull Continue Window", minval=1, maxval=30, group=groupRot)'
        : 'bullContinueWindow = input.int(14, "Bull Continue Window", minval=1, maxval=30)',
    );
  }
  if (!/\b(?:int\s+)?bearReboundWindow\s*=/.test(next)) {
    next = insertBeforeTimeBoxedWindowUsage(
      next,
      hasGroupRot
        ? 'bearReboundWindow = input.int(14, "Bear Rebound Window", minval=1, maxval=30, group=groupRot)'
        : 'bearReboundWindow = input.int(14, "Bear Rebound Window", minval=1, maxval=30)',
    );
  }
  return next;
}

function upsertAssignment(source: string, identifier: string, line: string): string {
  const assignmentPattern = new RegExp(
    String.raw`^(\s*)(?:var\s+)?(?:bool\s+|int\s+|float\s+)?${escapeForRegex(identifier)}\s*=.*$`,
    "m",
  );
  if (assignmentPattern.test(source)) {
    return source.replace(assignmentPattern, `$1${line}`);
  }

  return insertBeforePrimaryEntryTrigger(source, line);
}

function insertBeforeTimeBoxedWindowUsage(source: string, line: string): string {
  const firstUsagePattern =
    /^(\s*(?:var\s+)?(?:int\s+|bool\s+)?(?:bullEventAge|bearEventAge|bullAgeActive|bearAgeActive|postBullEventWindow|postBearReboundWindow)\b.*)$/m;
  if (firstUsagePattern.test(source)) {
    return source.replace(firstUsagePattern, `${line}\n$1`);
  }

  return insertBeforePrimaryEntryTrigger(source, line);
}

function insertBeforePrimaryEntryTrigger(source: string, line: string): string {
  if (/^\s*(?:bool\s+)?primaryEntryTrigger\s*=/m.test(source)) {
    return source.replace(
      /^(\s*(?:bool\s+)?primaryEntryTrigger\s*=.*)$/m,
      `${line}\n$1`,
    );
  }

  if (/^\s*(?:bool\s+)?entryPass\s*=/m.test(source)) {
    return source.replace(/^(\s*(?:bool\s+)?entryPass\s*=.*)$/m, `${line}\n$1`);
  }

  if (/^\s*if\s+entryPass\b/m.test(source)) {
    return source.replace(/^(\s*if\s+entryPass\b.*)$/m, `${line}\n$1`);
  }

  if (/^\s*(?:bool\s+)?entrySignal\s*=/m.test(source)) {
    return source.replace(
      /^(\s*(?:bool\s+)?entrySignal\s*=.*)$/m,
      `${line}\n$1`,
    );
  }

  if (/^\s*if\s+entrySignal\b/m.test(source)) {
    return source.replace(/^(\s*if\s+entrySignal\b.*)$/m, `${line}\n$1`);
  }

  return `${source}\n${line}\n`;
}

function simplifyTimeBoxedEntryPass(source: string): string {
  return ensureCanonicalTimeBoxedEntryGate(source);
}

function ensureCanonicalTimeBoxedEntryGate(source: string): string {
  const replacement = /\briskOff\b/.test(source)
    ? "entryPass = primaryEntryTrigger and not riskOff"
    : "entryPass = primaryEntryTrigger";
  let next = source;
  const entryPassPattern = /^(\s*)(?:bool\s+)?entryPass\s*=.*$/m;
  if (entryPassPattern.test(next)) {
    next = next.replace(entryPassPattern, `$1${replacement}`);
  } else if (/^\s*(?:bool\s+)?primaryEntryTrigger\s*=.*$/m.test(next)) {
    next = next.replace(
      /^(\s*(?:bool\s+)?primaryEntryTrigger\s*=.*)$/m,
      `$1\n${replacement}`,
    );
  } else {
    next = insertBeforePrimaryEntryTrigger(next, replacement);
  }

  return next.replace(/^(\s*)if\s+entrySignal\b/gm, "$1if entryPass");
}

function pushPatternIssue(input: {
  issues: PineGenerationIssue[];
  source: string;
  code: string;
  ruleId: string;
  category: PineGenerationIssue["category"];
  severity: "blocking" | "warning";
  pattern: RegExp;
  message: string;
  recommendation: string;
}): void {
  const lineHints = findMatchingLineHints(input.source, input.pattern);
  if (lineHints.length === 0) {
    return;
  }

  input.issues.push({
    code: input.code,
    ruleId: input.ruleId,
    category: input.category,
    severity: input.severity,
    message: input.message,
    recommendation: input.recommendation,
    lineHints,
  });
}

function findMatchingLineHints(source: string, pattern: RegExp): number[] {
  const lines = source.split(/\r?\n/);
  const matches: number[] = [];
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index] ?? "";
    pattern.lastIndex = 0;
    if (pattern.test(line)) {
      matches.push(index + 1);
    }
  }
  return matches.slice(0, 5);
}

function pushRecentUndeclaredIdentifierIssues(
  issues: PineGenerationIssue[],
  source: string,
  recentCompileErrors: string[],
): void {
  const identifiers = recentCompileErrors
    .map((error) => error.match(/Undeclared identifier '([^']+)'/i)?.[1]?.trim())
    .filter((identifier): identifier is string => Boolean(identifier));

  for (const identifier of identifiers) {
    const lineHints = findIdentifierUsageLineHints(source, identifier);
    if (lineHints.length === 0 || hasIdentifierAssignment(source, identifier)) {
      continue;
    }

    issues.push({
      code: "recent_undeclared_identifier_repeat",
      ruleId: "pine.recent_undeclared_identifier_repeat",
      category: "compatibility",
      severity: "blocking",
      message: `Generated Pine source reuses recently undeclared identifier '${identifier}' without any visible assignment.`,
      recommendation: `Declare and initialize '${identifier}' before use, or remove the reference entirely.`,
      lineHints,
    });
  }
}

function findIdentifierUsageLineHints(source: string, identifier: string): number[] {
  const escapedIdentifier = escapeForRegex(identifier);
  return findMatchingLineHints(source, new RegExp(`\\b${escapedIdentifier}\\b`));
}

function hasIdentifierAssignment(source: string, identifier: string): boolean {
  const escapedIdentifier = escapeForRegex(identifier);
  return new RegExp(
    String.raw`(^|\n)\s*(?:var\s+)?(?:[\w.<>\[\]]+\s+)?${escapedIdentifier}\s*[:=]?=`,
    "m",
  ).test(source);
}

function pushFunctionGlobalMutationIssues(
  issues: PineGenerationIssue[],
  source: string,
): void {
  const lines = source.split(/\r?\n/);
  const globalAssignments = new Set<string>();
  const topLevelAssignmentPattern =
    /^(?:var\s+)?(?:[\w.<>\[\]]+\s+)?([A-Za-z_]\w*)\s*[:=]?=/;

  for (const line of lines) {
    if (/^\s/.test(line)) {
      continue;
    }
    if (/^(if|else|for|while|switch)\b/.test(line.trim())) {
      continue;
    }
    const match = line.match(topLevelAssignmentPattern);
    if (match?.[1]) {
      globalAssignments.add(match[1]);
    }
  }

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index] ?? "";
    if (!/^[A-Za-z_]\w*\s*\([^)]*\)\s*=>\s*$/.test(line)) {
      continue;
    }

    for (let bodyIndex = index + 1; bodyIndex < lines.length; bodyIndex += 1) {
      const bodyLine = lines[bodyIndex] ?? "";
      if (!/^\s+/.test(bodyLine)) {
        break;
      }

      const mutationMatch = bodyLine.match(/^\s+([A-Za-z_]\w*)\s*:=/);
      if (!mutationMatch?.[1] || !globalAssignments.has(mutationMatch[1])) {
        continue;
      }

      issues.push({
        code: "function_mutates_global",
        ruleId: "pine.function_mutates_global",
        category: "compatibility",
        severity: "blocking",
        message: `Generated Pine source mutates global variable '${mutationMatch[1]}' inside a function body.`,
        recommendation:
          "Return values from the function and update global state at the call site instead of mutating globals inside the function.",
        lineHints: [bodyIndex + 1],
      });
    }
  }
}

function pushLongTitleIssues(
  issues: PineGenerationIssue[],
  source: string,
  recentCompileFailureClasses: ReadonlySet<CompileFailureClass>,
): void {
  if (!recentCompileFailureClasses.has("title_too_long")) {
    return;
  }

  const lines = source.split(/\r?\n/);
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index] ?? "";
    const titleMatch = line.match(/\b(?:strategy|indicator|study)\s*\(\s*["']([^"']+)["']/i);
    if (!titleMatch?.[1]) {
      continue;
    }

    if (titleMatch[1].length <= 60) {
      continue;
    }

    issues.push({
      code: "strategy_title_too_long",
      ruleId: "pine.strategy_title_too_long",
      category: "compatibility",
      severity: "blocking",
      message:
        "Generated Pine source uses a strategy title that is likely to exceed the current Pine executor title limit.",
      recommendation:
        "Shorten the strategy title or label and keep metadata in comments instead of the title string.",
      lineHints: [index + 1],
    });
    return;
  }
}

function pushNaTypeAssignmentIssues(
  issues: PineGenerationIssue[],
  source: string,
  recentCompileFailureClasses: ReadonlySet<CompileFailureClass>,
): void {
  if (!recentCompileFailureClasses.has("na_type_assignment")) {
    return;
  }

  const declaredIdentifiers = new Set<string>();
  const lines = source.split(/\r?\n/);

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index] ?? "";
    const declarationMatch = line.match(
      /^\s*(?:var\s+)?(?:bool|int|float|string|color|line|label|box|table|array<[^>]+>|matrix<[^>]+>)\s+([A-Za-z_]\w*)\s*(?:[:=]?=)?/i,
    );
    if (declarationMatch?.[1]) {
      declaredIdentifiers.add(declarationMatch[1]);
    }

    const riskyMatch = line.match(/^\s*([A-Za-z_]\w*)\s*=\s*na\b/);
    if (!riskyMatch?.[1] || declaredIdentifiers.has(riskyMatch[1])) {
      continue;
    }

    issues.push({
      code: "na_type_assignment",
      ruleId: "pine.na_type_assignment",
      category: "compatibility",
      severity: "blocking",
      message:
        `Generated Pine source assigns na to '${riskyMatch[1]}' without a visible typed declaration.`,
      recommendation:
        "Declare the variable with an explicit Pine type or use var/type initialization before assigning na.",
      lineHints: [index + 1],
    });
    return;
  }
}

function pushMissingLocalCodeBlockIssues(
  issues: PineGenerationIssue[],
  source: string,
): void {
  const lines = source.split(/\r?\n/);
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index] ?? "";
    const trimmed = stripLineComment(line).trim();
    if (!requiresLocalCodeBlock(trimmed)) {
      continue;
    }

    const currentIndent = indentationWidth(line);
    const nextCodeLine = findNextCodeLine(lines, index + 1);
    if (nextCodeLine && indentationWidth(nextCodeLine.line) > currentIndent) {
      continue;
    }

    issues.push({
      code: "missing_local_code_block",
      ruleId: "pine.missing_local_code_block",
      category: "syntax",
      severity: "blocking",
      message:
        "Generated Pine source has a function, conditional, or loop structure without an indented local code block.",
      recommendation:
        "Add at least one indented Pine expression inside the structure, or remove the empty structure entirely.",
      lineHints: [index + 1],
    });
  }
}

function requiresLocalCodeBlock(trimmedLine: string): boolean {
  if (!trimmedLine) {
    return false;
  }

  const functionMatch = trimmedLine.match(/^\w+\s*\([^)]*\)\s*=>\s*(.*)$/);
  if (functionMatch) {
    return (functionMatch[1] ?? "").trim().length === 0;
  }

  return /^(?:if|else\s+if|else|for|while|switch)\b/.test(trimmedLine);
}

function findNextCodeLine(
  lines: string[],
  startIndex: number,
): { line: string; index: number } | null {
  for (let index = startIndex; index < lines.length; index += 1) {
    const line = lines[index] ?? "";
    const trimmed = stripLineComment(line).trim();
    if (!trimmed) {
      continue;
    }
    return { line, index };
  }
  return null;
}

function stripLineComment(line: string): string {
  const commentIndex = line.indexOf("//");
  return commentIndex >= 0 ? line.slice(0, commentIndex) : line;
}

function indentationWidth(line: string): number {
  const indent = line.match(/^\s*/)?.[0] ?? "";
  let width = 0;
  for (const char of indent) {
    width += char === "\t" ? 4 : 1;
  }
  return width;
}

function pushBreakoutVariantDirectiveIssues(
  issues: PineGenerationIssue[],
  source: string,
  directive: MutationBrief["breakoutVariantDirective"] | undefined,
): void {
  if (!directive || directive.routeId !== "time_boxed_event_rotation") {
    return;
  }

  if (
    !usesDenseEarlyEventFloor(source) ||
    usesSparseTimeBoxedWindowAlias(source) ||
    usesDelayedTimeBoxedAgeWindow(source)
  ) {
    issues.push({
      code: "time_boxed_sparse_event_source",
      ruleId: "pine.time_boxed_sparse_event_source",
      category: "risk",
      severity: "blocking",
      message:
        "Time-boxed breakout variant still depends on sparse AF milestone events instead of a dense early event floor.",
      recommendation:
        "Add eventFloorBars with default 4 or 5, define earlyBullEvent and earlyBearEvent from bull/bear progress reaching that floor, and feed post-event windows from those dense early events rather than only L1/L2/L3, candidate, strong, or confirmed events.",
      lineHints: findMatchingLineHints(
        source,
        /\b(?:L1_in|bullEventRaw|bearEventRaw|postBullEventWindow|postBearReboundWindow|primaryEntryTrigger|rotationWindowEnd|rotationActive|windowBars|entrySignal)\b/i,
      ),
    });
  }

  const overfilteredEntryLineHints = findOverfilteredTimeBoxedEntryLineHints(
    source,
  );
  if (overfilteredEntryLineHints.length > 0) {
    issues.push({
      code: "time_boxed_entry_overfiltered",
      ruleId: "pine.time_boxed_entry_overfiltered",
      category: "risk",
      severity: "blocking",
      message:
        "Time-boxed breakout variant still gates primaryEntryTrigger behind multiple entry filters, which preserves the sparse 31/7 profile.",
      recommendation:
        "Make entryPass primaryEntryTrigger plus at most one lightweight risk-off exclusion. Remove trendPass, supertrendEntryPass, overextended, rank, and confirmation stacks from the primary entry path.",
      lineHints: overfilteredEntryLineHints,
    });
  }
}

function usesDelayedTimeBoxedAgeWindow(source: string): boolean {
  return /^\s*(?:bool\s+)?(?:bullAgeActive|bearAgeActive|postBullEventWindow|postBearReboundWindow)\s*=.*\b(?:bullEventAge|bearEventAge|bullAge|bearAge)\s*>=\s*(?:eventFloorBars|earlyEventFloorBars|[2-9]\d*)/im.test(
    source,
  );
}

function usesSparseTimeBoxedWindowAlias(source: string): boolean {
  if (!findSparseAliasLine(source, "bull") && !findSparseAliasLine(source, "bear")) {
    return false;
  }

  return /\b(?:bullEarlyEvent|bearEarlyEvent|bullEventSource|bearEventSource)\b[\s\S]*\bprimaryEntryTrigger\b/i.test(
    source,
  );
}

function findSparseAliasLine(source: string, side: "bull" | "bear"): boolean {
  const prefix = side === "bull" ? "Bull" : "Bear";
  const lowerPrefix = side === "bull" ? "bull" : "bear";
  const aliasPattern = new RegExp(
    String.raw`^\s*(?:bool\s+)?(?:${lowerPrefix}EarlyEvent|${lowerPrefix}EventSource)\s*=([^\n]+)$`,
    "im",
  );
  const expression = source.match(aliasPattern)?.[1] ?? "";
  if (!expression) {
    return false;
  }
  if (
    new RegExp(
      String.raw`\bearly${prefix}Event\b|\b${lowerPrefix}EventFloor\b`,
    ).test(expression)
  ) {
    return false;
  }
  return new RegExp(
    String.raw`\bnew${prefix}(?:L1|Candidate|Strong|Confirmed)\b|\b${lowerPrefix}(?:L1|Candidate|Strong|Confirmed)\b`,
  ).test(expression);
}

function usesDenseEarlyEventFloor(source: string): boolean {
  const hasDenseFloorInput =
    /\b(?:int\s+)?(?:eventFloorBars|earlyEventFloorBars)\s*=\s*input\.int\s*\(\s*[2-5]\b/i.test(
      source,
    );
  const bullUsesDenseFloorDirect =
    /\b(?:earlyBullEvent|bullEventSource|bullEventRaw)\b[^\n=]*=\s*[^\n]*(?:\bbull\s*>=\s*(?:eventFloorBars|earlyEventFloorBars|[2-5]\b)|\bbull\s*>\s*(?:eventFloorBars|earlyEventFloorBars|[1-4]\b))/i.test(
      source,
    );
  const bearUsesDenseFloorDirect =
    /\b(?:earlyBearEvent|bearEventSource|bearEventRaw)\b[^\n=]*=\s*[^\n]*(?:\bbear\s*>=\s*(?:eventFloorBars|earlyEventFloorBars|[2-5]\b)|\bbear\s*>\s*(?:eventFloorBars|earlyEventFloorBars|[1-4]\b))/i.test(
      source,
    );
  const bullUsesDenseFloorVariable =
    /\b(?:bool\s+)?bullEventFloor\s*=\s*\bbull\s*>=\s*(?:eventFloorBars|earlyEventFloorBars|[2-5]\b)/i.test(
      source,
    ) && /\b(?:bool\s+)?earlyBullEvent\s*=\s*[^\n]*\bbullEventFloor\b/i.test(source);
  const bearUsesDenseFloorVariable =
    /\b(?:bool\s+)?bearEventFloor\s*=\s*\bbear\s*>=\s*(?:eventFloorBars|earlyEventFloorBars|[2-5]\b)/i.test(
      source,
    ) && /\b(?:bool\s+)?earlyBearEvent\s*=\s*[^\n]*\bbearEventFloor\b/i.test(source);

  return (
    hasDenseFloorInput &&
    (bullUsesDenseFloorDirect || bullUsesDenseFloorVariable) &&
    (bearUsesDenseFloorDirect || bearUsesDenseFloorVariable)
  );
}

function findOverfilteredTimeBoxedEntryLineHints(source: string): number[] {
  const lines = source.split(/\r?\n/);
  const filterTokens = [
    "trendPass",
    "riskPass",
    "supertrendEntryPass",
    "overextended",
    "bullTrend",
    "bearTrend",
    "bullMomentum",
    "bearMomentum",
    "emaUp",
    "emaDown",
    "lastBullEventRank",
    "lastBearEventRank",
    "entryRank",
    "bullConfirmed",
    "bearConfirmed",
  ];

  const hints: number[] = [];
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index] ?? "";
    if (!/^\s*(?:bool\s+)?entryPass\s*=/.test(line)) {
      continue;
    }
    if (!/\bprimaryEntryTrigger\b/.test(line)) {
      continue;
    }

    const gateCount = filterTokens.reduce(
      (count, token) =>
        new RegExp(`\\b${escapeForRegex(token)}\\b`).test(line)
          ? count + 1
          : count,
      0,
    );
    if (gateCount > 1) {
      hints.push(index + 1);
    }
  }

  return hints;
}

function escapeForRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function createPatternRule(input: {
  id: string;
  code: string;
  category: PineGenerationIssue["category"];
  severity: PineGenerationIssue["severity"];
  pattern: RegExp;
  message: string;
  recommendation: string;
}): PreflightRule {
  return {
    id: input.id,
    code: input.code,
    category: input.category,
    severity: input.severity,
    check(source) {
      const issues: PineGenerationIssue[] = [];
      pushPatternIssue({
        issues,
        source,
        code: input.code,
        ruleId: input.id,
        category: input.category,
        severity: input.severity,
        pattern: input.pattern,
        message: input.message,
        recommendation: input.recommendation,
      });
      return issues;
    },
  };
}

function createIssue(input: PineGenerationIssue): PineGenerationIssue {
  return input;
}
