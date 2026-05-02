import { type ConditionInventoryItem, type MutationBrief } from "../contracts/types.js";

export interface MutationLlmClient {
  generateMutation(input: {
    brief: MutationBrief;
    baselinePine: string;
    signal?: AbortSignal;
  }): Promise<string>;
  generateConditionAblation(input: {
    brief: MutationBrief;
    candidatePine: string;
    condition: ConditionInventoryItem;
    candidateSummary?: string;
    inventory?: ConditionInventoryItem[];
    signal?: AbortSignal;
  }): Promise<string>;
  repairMutation(input: {
    brief: MutationBrief;
    candidatePine: string;
    compileErrors: string[];
    candidateSummary?: string;
    inventory?: ConditionInventoryItem[];
    rawFailedResponse?: string;
    signal?: AbortSignal;
  }): Promise<string>;
}

export function createStaticLlmClient(
  response: string,
  repairResponse?: string,
  ablationResponses?: Record<string, string>,
): MutationLlmClient {
  return {
    async generateMutation() {
      return response;
    },
    async generateConditionAblation(input) {
      return ablationResponses?.[input.condition.conditionId] ?? repairResponse ?? response;
    },
    async repairMutation() {
      return repairResponse ?? response;
    },
  };
}

export function createOpenAiCompatibleLlmClient(config: {
  baseUrl: string;
  model: string;
  apiKey?: string;
  requestTimeoutMs?: number;
  fetchImpl?: typeof fetch;
}): MutationLlmClient {
  const requestTimeoutMs = config.requestTimeoutMs ?? 60_000;
  const fetchImpl = config.fetchImpl ?? fetch;

  async function completeJson(
    messages: Array<{ role: "system" | "user"; content: string }>,
    externalSignal?: AbortSignal,
  ) {
    const endpoint = `${config.baseUrl.replace(/\/$/, "")}/chat/completions`;
    let response: Response;
    const controller = new AbortController();
    let timedOut = false;
    if (externalSignal?.aborted) {
      throw new Error("LLM request was aborted before it was sent.");
    }
    const onExternalAbort = () => {
      controller.abort(externalSignal?.reason ?? new Error("LLM request was aborted."));
    };
    externalSignal?.addEventListener("abort", onExternalAbort, { once: true });
    const timeout = setTimeout(() => {
      timedOut = true;
      controller.abort(
        new Error(
          `OpenAI-compatible endpoint ${endpoint} timed out after ${requestTimeoutMs}ms.`,
        ),
      );
    }, requestTimeoutMs);
    try {
      response = await fetchImpl(endpoint, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          ...(config.apiKey ? { authorization: `Bearer ${config.apiKey}` } : {}),
        },
        signal: controller.signal,
        body: JSON.stringify({
          model: config.model,
          response_format: { type: "json_object" },
          messages,
        }),
      });
    } catch (error) {
      clearTimeout(timeout);
      externalSignal?.removeEventListener("abort", onExternalAbort);
      if (timedOut) {
        throw new Error(
          `OpenAI-compatible endpoint ${endpoint} timed out after ${requestTimeoutMs}ms.`,
        );
      }
      if (externalSignal?.aborted || isAbortError(error)) {
        throw new Error(`OpenAI-compatible endpoint ${endpoint} request was aborted.`);
      }
      const detail = error instanceof Error ? error.message : String(error);
      throw new Error(`Failed to reach OpenAI-compatible endpoint ${endpoint}: ${detail}`);
    }
    clearTimeout(timeout);
    externalSignal?.removeEventListener("abort", onExternalAbort);

    if (!response.ok) {
      throw new Error(`LLM request failed with status ${response.status} at ${endpoint}.`);
    }

    const payload = (await response.json()) as {
      choices?: Array<{ message?: { content?: string | null } }>;
    };
    const content = payload.choices?.[0]?.message?.content;
    if (!content) {
      throw new Error("LLM response did not include content.");
    }
    return content;
  }

  return {
    async generateMutation(input) {
      return await completeJson([
        {
          role: "system",
          content:
            [
              "You are generating TradingView Pine Script strategy mutations.",
              "Return compile-ready Pine Script v5 only.",
              "Preserve the AF seed strategy core architecture when the brief includes seed preservation constraints.",
              "Treat brief.forbiddenPatterns as hard constraints.",
              "Do not replace the strategy with a generic EMA crossover or generic trend-following template unless the brief explicitly permits it.",
              "If brief.acceptedHead.metrics and brief.acceptedHead.tradeRetentionTarget are present, preserve the accepted head's tradability and avoid low-trade or zero-trade mutations.",
              "Treat brief.repairMode as a hard constraint.",
              "If brief.repairMode is entry_recovery, recover tradability by loosening or removing existing entry gates and do not add new filters, new regime gates, or new subsystems.",
              "If brief.repairMode is exit_profit_repair, keep changes inside exit, risk, loser-management, replacement, or slot-management blocks and do not use broad entry expansion as the main change.",
              "If brief.repairMode is exploration_breakout, do not repair the current family by loosening it. Generate a materially different AF-compatible structure from brief.explorationDirective, allow coordinated entry/exit/risk changes, and keep only local compatibility plus trade-count guardrails as hard preservation targets.",
              "If brief.repairMode is balanced, keep changes localized and avoid multi-block rewrites.",
              "If brief.recentCompileFailureClasses is non-empty, prioritize avoiding those normalized compile-failure classes before considering raw compiler strings.",
              "If brief.recentCompileErrors is non-empty, treat those exact compiler messages as anti-patterns that must not reappear in the new candidate.",
              "When brief.recentLossAnalysis.status is available and brief.repairPriorities is non-empty, prioritize those targeted repair priorities before broad entry-loosening changes.",
              "If brief.repairPriorities includes stabilize_trade_retention_cluster, aggressive_trade_recovery, or lift_oos_trade_floor, simplify the strategy materially: use one primary entry trigger, at most one lightweight regime filter, remove cooldown-heavy logic and stacked confirmations, and recover both full-sample and OOS trade counts before optimizing anything else.",
              "If brief.lossHotZones or brief.repairPriorities point to weak_exit, range_squeeze, or trend_down loss clusters, prefer localized exit or risk fixes over broad entry expansion unless tradability would otherwise collapse.",
              "If brief.stagnationSignals is non-empty, treat them as anti-repetition constraints and change the specific mutated rule, threshold, or regime scope instead of repeating the same diagnosis.",
              "If brief.stagnationSignals includes repeated_trade_retention_cluster, treat the recent sparse trade profile as forbidden and produce a materially simpler, trade-retentive candidate instead of a near-variant.",
              "If brief.breakoutOutcomeMemory is present, never choose routes listed in suppressedRoutes, prefer routes listed in preferredRoutes, and treat dominantSparsePatterns such as 31/7, 7/1, or 3/1 as forbidden local backtest profiles.",
              "If brief.breakoutOutcomeMemory.bestBreakoutRoute is time_boxed_event_rotation, preserve broad post-event participation, zero or low cooldown, and simple time exits while changing details enough to avoid duplicates.",
              "If brief.breakoutVariantDirective is present, it overrides generic route wording: implement every forcedRules item literally, avoid every forbiddenPatterns item, and do not emit another 31/7-style near-variant.",
              "For time_boxed_event_rotation, emit explicit route variables named eventFloorBars, eventWindowBars, maxHoldBars, bullContinueWindow, and bearReboundWindow; define bullEventFloor/bearEventFloor before earlyBullEvent/earlyBearEvent; make primaryEntryTrigger the canonical entry source and entryPass primaryEntryTrigger plus at most not riskOff.",
              "Do not make entrySignal, rotationWindowEnd, windowBars, holdBars1..4, or rank-specific aliases the only route surface; if you use aliases, also expose the canonical route variables and entryPass path so local scoring can identify the route.",
              "If brief.repairMode is not exploration_breakout and brief.recentCalibrationSummary, brief.highDivergenceFamilies, brief.lowDivergenceFamilies, or brief.calibrationAwareInstruction are present, treat them as calibration-aware mutation constraints. Prefer low-divergence families and avoid repeating high-divergence families without a material structural change.",
              "When brief.acceptedHead.metrics indicate a strong profitable accepted head, treat it as a control and keep mutations narrowly scoped to one localized behavior block unless the brief explicitly asks for a coordinated pair of changes or brief.repairMode is exploration_breakout.",
              "If a recent compile error mentions an undeclared identifier, ensure every referenced variable is declared before use and initialized with a Pine v5-safe type when na is involved.",
              "Do not use unsupported strategy.entry arguments such as qty_percent.",
              "Do not use ta.sum(); replace it with a Pine v5-safe alternative supported by the current executor.",
              "Do not mutate global variables inside Pine functions; return values and assign them at the call site instead.",
              "Do not emit placeholder text, TODO markers, or markdown fences inside pineScript.",
              "Do not use ta.adx(); if ADX is needed, use Pine v5-safe manual DMI/ADX logic.",
              "Return JSON only.",
              "Required top-level keys:",
              "candidateSummary: string",
              "nextMutationHints: string[]",
              "pineScript: full Pine script string",
              "inventory: array of { conditionId, role, summary, pineLineHints }",
              "Do not use alternative keys like pine, code, or source.",
            ].join(" "),
        },
        {
          role: "user",
          content: JSON.stringify(input, null, 2),
        },
      ], input.signal);
    },
    async generateConditionAblation(input) {
      return await completeJson([
        {
          role: "system",
          content:
            [
              "You are generating a TradingView Pine Script ablation variant for explainability.",
              "Disable exactly one target condition while preserving the overall strategy logic and keeping Pine v5 compile-ready.",
              "Preserve the AF seed strategy core architecture when the brief includes seed preservation constraints.",
              "Treat brief.forbiddenPatterns as hard constraints.",
              "Respect brief.repairMode when choosing what to ablate; keep the ablation local to the requested condition.",
              "Keep the exact same strategy() title unless it is missing.",
              "Do not emit markdown fences, TODO text, or placeholders inside pineScript.",
              "Do not use qty_percent, ta.sum(), or global-variable mutation inside functions.",
              "Do not use ta.adx(); use Pine v5-safe manual DMI/ADX logic when needed.",
              "Return JSON only.",
              "Required top-level keys:",
              "candidateSummary: string",
              "nextMutationHints: string[]",
              "pineScript: full Pine script string",
              "inventory: array of { conditionId, role, summary, pineLineHints }",
            ].join(" "),
        },
        {
          role: "user",
          content: JSON.stringify(input, null, 2),
        },
      ], input.signal);
    },
    async repairMutation(input) {
      return await completeJson([
        {
          role: "system",
          content:
            [
              "You are repairing a TradingView Pine Script strategy after a failed autonomous evaluation step.",
              "Return JSON only.",
              "Keep the strategy intent intact while fixing the specific failure described in compileErrors.",
              "If rawFailedResponse is present, repair that malformed response into the required strict JSON shape instead of falling back to baseline source.",
              "Preserve the AF seed strategy core architecture when the brief includes seed preservation constraints.",
              "Treat brief.forbiddenPatterns as hard constraints.",
              "Treat compileErrors as the authoritative repair instructions even when they describe local compatibility, trade-count, OOS, or robustness failures rather than compiler errors.",
              "Target Pine version 5 compatibility.",
              "If brief.repairMode is entry_recovery, recover tradability by loosening or removing existing entry gates and do not add new filters, new regime gates, or new subsystems.",
              "If brief.repairMode is exit_profit_repair, keep changes inside exit, risk, loser-management, replacement, or slot-management blocks and do not use broad entry expansion as the main change.",
              "If brief.repairMode is exploration_breakout, do not repair the current family by loosening it. Regenerate into a materially different AF-compatible structure from brief.explorationDirective, and preserve only local compatibility plus trade-count guardrails.",
              "If brief.repairMode is balanced, keep changes localized and avoid multi-block rewrites.",
              "Respect brief.recentCompileFailureClasses as normalized compiler anti-patterns that must be removed.",
              "If compileErrors mention minimum trade counts or out-of-sample trade deficits, increase trade opportunity density and preserve positive post-fee profitability.",
              "If brief.repairPriorities includes stabilize_trade_retention_cluster, aggressive_trade_recovery, or lift_oos_trade_floor, aggressively simplify entry logic: use one primary entry trigger, at most one lightweight regime filter, remove cooldown-heavy logic, and do not preserve stacked confirmations or sparse gating.",
              "If brief.repairMode is not exploration_breakout and brief.recentCalibrationSummary, brief.highDivergenceFamilies, brief.lowDivergenceFamilies, or brief.calibrationAwareInstruction are present, use them as calibration-aware repair constraints. Do not re-emit a high-divergence family without a material structural correction.",
              "If brief.stagnationSignals includes repeated_trade_retention_cluster, treat the recent sparse trade profile as forbidden and materially widen trade opportunity density before any other optimization.",
              "If brief.breakoutOutcomeMemory is present, do not repair into any suppressedRoutes and do not repeat dominantSparsePatterns such as 31/7, 7/1, or 3/1; when preferredRoutes contains time_boxed_event_rotation, keep broad post-event windows, zero or low cooldown, and simple time exits.",
              "If brief.breakoutVariantDirective is present during repair, keep the same route only as the named variant: implement forcedRules literally, remove forbiddenPatterns, and materially change the failed sparse implementation before optimizing score.",
              "For time_boxed_event_rotation repairs, emit explicit route variables named eventFloorBars, eventWindowBars, maxHoldBars, bullContinueWindow, and bearReboundWindow; define bullEventFloor/bearEventFloor before earlyBullEvent/earlyBearEvent; make primaryEntryTrigger the canonical entry source and entryPass primaryEntryTrigger plus at most not riskOff.",
              "Do not repair by hiding the route behind entrySignal, rotationWindowEnd, windowBars, holdBars1..4, or rank-specific aliases unless the canonical route variables and entryPass path are also present.",
              "If compileErrors mention local compatibility, emit every required AF input and helper exactly and keep the script compatible with the local-first executor.",
              "Do not use qty_percent, ta.sum(), or global-variable mutation inside functions.",
              "Do not emit placeholder text, TODO markers, or markdown fences inside pineScript.",
              "Do not use ta.adx(); replace it with Pine v5-safe manual DMI/ADX logic when needed.",
              "Required top-level keys:",
              "candidateSummary: string",
              "nextMutationHints: string[]",
              "pineScript: full Pine script string",
              "inventory: array of { conditionId, role, summary, pineLineHints }",
              "Do not omit any required key.",
            ].join(" "),
        },
        {
          role: "user",
          content: JSON.stringify(input, null, 2),
        },
      ], input.signal);
    },
  };
}

function isAbortError(error: unknown): boolean {
  return (
    error instanceof Error &&
    (error.name === "AbortError" || /aborted|abort/i.test(error.message))
  );
}
