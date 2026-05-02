import { type ConditionInventoryItem, type MutationBrief } from "../contracts/types.js";
import { afStrategySpecFromPine } from "../strategy-spec/to-af-config.js";
import { parseAfStrategySpec } from "../strategy-spec/schema.js";

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
      return normalizeStaticMutationResponse(response);
    },
    async generateConditionAblation(input) {
      return normalizeStaticMutationResponse(
        ablationResponses?.[input.condition.conditionId] ?? repairResponse ?? response,
      );
    },
    async repairMutation() {
      return normalizeStaticMutationResponse(repairResponse ?? response);
    },
  };
}

function normalizeStaticMutationResponse(response: string): string {
  try {
    const payload = JSON.parse(response) as Record<string, unknown>;
    if (payload.strategySpec != null || typeof payload.pineScript !== "string") {
      return response;
    }
    const recovered = afStrategySpecFromPine(payload.pineScript);
    const strategySpec = recovered.spec ?? buildDefaultStaticStrategySpec();
    return JSON.stringify({
      ...payload,
      strategySpec,
      specPatch: payload.specPatch ?? {
        version: "af-spec-patch/v1",
        summary: "Recovered legacy static fixture as a spec-authoritative mutation.",
        operations: [
          {
            path: "/entry",
            after: "legacy_static_fixture",
            reason: "Static test fixture omitted a structured specPatch.",
          },
        ],
      },
    });
  } catch {
    return response;
  }
}

function buildDefaultStaticStrategySpec() {
  return parseAfStrategySpec({
    version: "af-spec/v1",
    name: "Static Fixture AF Spec",
    event: {
      source: "af_exhaustion",
      L1: 9,
      L2: 12,
      L3: 14,
      confirmBars: 2,
      eventFloorBars: null,
      eventWindowBars: null,
    },
    regime: {
      trendMode: "Balanced",
      useSupertrendFilter: false,
      riskOffRsi: 45,
      maxExtPct: 6,
    },
    entry: {
      primaryTrigger: "bull_event",
      cooldownBars: 0,
      allowBearRebound: true,
      applyFilterToB1: false,
    },
    slot: {
      slotPct: 15,
      maxSlots: 18,
      useReplacement: true,
      replaceMinRank: 3,
      replaceIfPnlBelow: -5,
    },
    exit: {
      weakRangeExit: true,
      maxHoldBars: null,
      closeAllOnBearConfRiskOff: true,
      resetOnL3: false,
    },
  });
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
              "You are generating schema-first AF strategy mutations.",
              "Return an AF strategySpec object; do not return hand-written Pine as the authority.",
              "Pine Script will be generated deterministically by the research harness from strategySpec.",
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
              "For time_boxed_event_rotation, set strategySpec.event.eventFloorBars, strategySpec.event.eventWindowBars, and strategySpec.exit.maxHoldBars explicitly.",
              "If brief.repairMode is not exploration_breakout and brief.recentCalibrationSummary, brief.highDivergenceFamilies, brief.lowDivergenceFamilies, or brief.calibrationAwareInstruction are present, treat them as calibration-aware mutation constraints. Prefer low-divergence families and avoid repeating high-divergence families without a material structural change.",
              "When brief.acceptedHead.metrics indicate a strong profitable accepted head, treat it as a control and keep mutations narrowly scoped to one localized behavior block unless the brief explicitly asks for a coordinated pair of changes or brief.repairMode is exploration_breakout.",
              "If a recent compile error mentions an undeclared identifier, ensure every referenced variable is declared before use and initialized with a Pine v5-safe type when na is involved.",
              "Do not use unsupported strategy.entry arguments such as qty_percent.",
              "Do not use ta.sum(); replace it with a Pine v5-safe alternative supported by the current executor.",
              "Do not mutate global variables inside Pine functions; return values and assign them at the call site instead.",
              "Do not emit placeholder text, TODO markers, markdown fences, or a hand-written pineScript.",
              "Return JSON only.",
              "Required top-level keys:",
              "candidateSummary: string",
              "nextMutationHints: string[]",
              "strategySpec: object matching version af-spec/v1",
              "specPatch: { version: 'af-spec-patch/v1', summary: string, operations: [{ path, before?, after, reason }] } where path is under /event, /regime, /entry, /slot, or /exit",
              "inventory: array of { conditionId, role, summary, pineLineHints }",
              "Do not use alternative keys like pine, code, source, or pineScript.",
            ].join(" "),
        },
        {
          role: "user",
          content: JSON.stringify(withStrategySpecContext(input, "baselinePine"), null, 2),
        },
      ], input.signal);
    },
    async generateConditionAblation(input) {
      return await completeJson([
        {
          role: "system",
          content:
            [
              "You are generating a schema-first AF strategy ablation variant for explainability.",
              "Disable exactly one target condition in strategySpec while preserving the overall strategy intent.",
              "Pine Script will be generated deterministically by the research harness from strategySpec.",
              "Preserve the AF seed strategy core architecture when the brief includes seed preservation constraints.",
              "Treat brief.forbiddenPatterns as hard constraints.",
              "Respect brief.repairMode when choosing what to ablate; keep the ablation local to the requested condition.",
              "Keep the exact same strategy() title unless it is missing.",
              "Do not emit markdown fences, TODO text, placeholders, or hand-written pineScript.",
              "Return JSON only.",
              "Required top-level keys:",
              "candidateSummary: string",
              "nextMutationHints: string[]",
              "strategySpec: object matching version af-spec/v1",
              "specPatch: { version: 'af-spec-patch/v1', summary: string, operations: [{ path, before?, after, reason }] } where path is under /event, /regime, /entry, /slot, or /exit",
              "inventory: array of { conditionId, role, summary, pineLineHints }",
            ].join(" "),
        },
        {
          role: "user",
          content: JSON.stringify(withStrategySpecContext(input, "candidatePine"), null, 2),
        },
      ], input.signal);
    },
    async repairMutation(input) {
      return await completeJson([
        {
          role: "system",
          content:
            [
              "You are repairing a schema-first AF strategySpec after a failed autonomous evaluation step.",
              "Return JSON only.",
              "Keep the strategy intent intact while fixing the specific failure described in compileErrors.",
              "If rawFailedResponse is present, repair that malformed response into the required strict JSON shape instead of falling back to baseline source.",
              "Pine Script will be generated deterministically by the research harness from strategySpec; do not return hand-written pineScript.",
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
              "For time_boxed_event_rotation repairs, set strategySpec.event.eventFloorBars, strategySpec.event.eventWindowBars, and strategySpec.exit.maxHoldBars explicitly.",
              "If compileErrors mention local compatibility, emit every required AF input and helper exactly and keep the script compatible with the local-first executor.",
              "Do not emit placeholder text, TODO markers, markdown fences, or hand-written Pine.",
              "Required top-level keys:",
              "candidateSummary: string",
              "nextMutationHints: string[]",
              "strategySpec: object matching version af-spec/v1",
              "specPatch: { version: 'af-spec-patch/v1', summary: string, operations: [{ path, before?, after, reason }] } where path is under /event, /regime, /entry, /slot, or /exit",
              "inventory: array of { conditionId, role, summary, pineLineHints }",
              "Do not omit any required key.",
            ].join(" "),
        },
        {
          role: "user",
          content: JSON.stringify(withStrategySpecContext(input, "candidatePine"), null, 2),
        },
      ], input.signal);
    },
  };
}

function withStrategySpecContext<T extends Record<string, unknown>>(
  input: T,
  pineField: "baselinePine" | "candidatePine",
): T & { baselineStrategySpec?: unknown; candidateStrategySpec?: unknown } {
  const pineSource = typeof input[pineField] === "string" ? input[pineField] : null;
  const recovered = pineSource ? afStrategySpecFromPine(pineSource).spec : null;
  if (pineField === "baselinePine") {
    return {
      ...input,
      baselineStrategySpec: recovered,
    };
  }
  return {
    ...input,
    candidateStrategySpec: recovered,
  };
}

function isAbortError(error: unknown): boolean {
  return (
    error instanceof Error &&
    (error.name === "AbortError" || /aborted|abort/i.test(error.message))
  );
}
