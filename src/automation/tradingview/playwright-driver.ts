import {
  applyResultSchema,
  artifactBundleSchema,
  compileResultSchema,
  syncArtifactSchema,
  type ArtifactBundle,
  type AttachDiagnostics,
  type BacktestMetrics,
  type ChartTarget,
  type CompileResult,
  type ConditionInventoryItem,
  type ExecutorCapability,
  type SurfaceRecoveryAction,
  type SyncArtifact,
  type VerificationRuntimeFailureKind,
} from "../../contracts/types.js";
import { extractStudyTitle } from "./pine-study.js";
import {
  extractBacktestMetricsFromReportData,
  extractEquitySummaryFromReportData,
  extractTraceEventsFromReportData,
  extractTradeRecordsFromReportData,
  inspectReportData,
  normalizeAttachedStudyTitle,
  type RawStrategyReportData,
} from "./report-data.js";
import { buildTvTraceArtifact } from "./trace-artifact.js";
import { type PineEvaluationExecutor } from "./types.js";
import { type ExecutorHealth } from "../common/executor.js";
import { TradingViewDesktopCdpClient } from "./cdp-client.js";
import { sha256 } from "../../utils/fs.js";

interface TradingViewDesktopExecutorConfig {
  executablePath?: string;
  cdpUrl?: string;
  pineEditorTimeoutMs?: number;
  cdpCommandTimeoutMs?: number;
}

interface AttachedStudySnapshot {
  title: string | null;
  normalizedTitle: string | null;
  metaDescription: string | null;
  hasStrategyData: boolean;
}

interface ChartStateSnapshot {
  symbol: string | null;
  timeframe: string | null;
  pineEditorOpen: boolean;
  attachedStudies: AttachedStudySnapshot[];
}

interface StrategySnapshot {
  attachedStudies: AttachedStudySnapshot[];
  expectedStudy: {
    title: string | null;
    normalizedTitle: string | null;
    metaDescription: string | null;
    reportData: RawStrategyReportData | null;
  } | null;
}

interface StudyRemovalResult {
  removedCount: number;
  dismissedIndicatorLimitDialog: boolean;
}

const MONACO_MODULE_ID = 24292;
const DEFAULT_PINE_EDITOR_WAIT_TIMEOUT_MS = 15_000;
const PINE_EDITOR_HARD_RELOAD_WAIT_MS = 12_000;

export class TradingViewDesktopExecutor implements PineEvaluationExecutor {
  public readonly role = "external_calibration";
  public readonly evidenceAuthority = "external_tv";
  public readonly supportedStrategyFamilies = ["Pine"];
  public readonly supportedSymbols: string[] = [];
  public readonly supportedTimeframes: string[] = [];
  private readonly client: TradingViewDesktopCdpClient;
  private readonly pineEditorTimeoutMs: number;
  private lastCompile: CompileResult | null = null;
  private lastAttachDiagnostics: AttachDiagnostics | null = null;
  private pendingStudyTitle: string | null = null;
  private pendingAttachRecoveryActions: string[] = [];

  public constructor(config: TradingViewDesktopExecutorConfig) {
    this.client = new TradingViewDesktopCdpClient({
      executablePath: config.executablePath,
      cdpUrl: config.cdpUrl,
      commandTimeoutMs: config.cdpCommandTimeoutMs,
    });
    this.pineEditorTimeoutMs =
      config.pineEditorTimeoutMs ?? DEFAULT_PINE_EDITOR_WAIT_TIMEOUT_MS;
  }

  public getCapability(): ExecutorCapability {
    return {
      kind: "tradingview-live",
      authoritative: true,
      supportedSymbols: this.supportedSymbols,
      supportedTimeframes: this.supportedTimeframes,
      supportedStrategyFamilies: this.supportedStrategyFamilies,
      confidenceLevel: "verification",
      role: this.role,
      evidenceAuthority: this.evidenceAuthority,
    };
  }

  public async healthCheck(): Promise<ExecutorHealth> {
    try {
      await this.client.connect();
      return {
        healthy: true,
        status: "ready",
        detail: "TradingView Desktop CDP surface is reachable.",
      };
    } catch (error) {
      return {
        healthy: false,
        status: "unavailable",
        detail: error instanceof Error ? error.message : String(error),
      };
    }
  }

  public async recoverSurface(input: {
    action: SurfaceRecoveryAction;
    chartTarget: ChartTarget;
    failureKind: VerificationRuntimeFailureKind;
  }): Promise<void> {
    switch (input.action) {
      case "soft_reload_chart":
        await this.prepareChart(input.chartTarget);
        return;
      case "reopen_pine_editor":
        await this.client.close();
        await this.prepareChart(input.chartTarget);
        await this.ensurePineEditorReady("Pine editor reopen");
        return;
      case "reattach_monaco":
        await this.ensurePineEditorReady("Monaco editor ready");
        await this.client.evaluate<number>(monacoEditorCountExpression());
        await this.client.evaluate<boolean>(focusMonacoEditorExpression());
        return;
      case "reopen_strategy_tester":
        await this.prepareChart(input.chartTarget);
        await this.readStrategySnapshot(null);
        return;
      case "restart_tradingview_page":
      default:
        await this.client.close();
        await this.prepareChart(input.chartTarget);
        return;
    }
  }

  public async prepareChart(input: ChartTarget): Promise<void> {
    await this.ensurePineEditorReady("Pine editor open");

    await this.client.evaluate<boolean>(setChartTargetExpression(input));
    await this.client.waitFor(
      () => this.readChartState(),
      (state) =>
        normalizeSymbol(state.symbol) === normalizeSymbol(input.symbol) &&
        normalizeResolution(state.timeframe) === normalizeResolution(input.timeframe),
      {
        label: "Chart target",
      },
    );
    await this.removeAttachedStrategyStudies(null);
  }

  public async updateStrategySource(source: string): Promise<void> {
    await this.ensurePineEditorReady("Monaco editor ready");
    this.pendingStudyTitle = extractStudyTitle(source);
    this.pendingAttachRecoveryActions = [];
    await this.client.evaluate<boolean>(setMonacoSourceExpression(source));
  }

  public async compileStrategy(): Promise<CompileResult> {
    if (this.pendingStudyTitle != null) {
      const removal = await this.removeAttachedStrategyStudies(this.pendingStudyTitle);
      if (removal.removedCount > 0) {
        this.pendingAttachRecoveryActions.push(
          "pre_removed_existing_strategy_studies",
        );
      }
      if (removal.dismissedIndicatorLimitDialog) {
        this.pendingAttachRecoveryActions.push(
          "dismissed_indicator_limit_dialog",
        );
      }
    }

    await this.client.evaluate<boolean>(focusMonacoEditorExpression());
    await this.client.dispatchCtrlEnter();
    await this.client.delay(4_000);

    const markers = await this.client.evaluate<
      Array<{ message: string; severity: number }>
    >(readMonacoMarkersExpression());
    const errors = deduplicateErrors(
      markers
        .filter((marker) => marker.severity >= 8)
        .map((marker) => marker.message.trim())
        .filter(Boolean),
    );

    const compile = compileResultSchema.parse({
      ok: errors.length === 0,
      errors,
    });
    this.lastCompile = compile;
    return compile;
  }

  public async applyStrategy(input?: {
    expectedStudyTitle?: string | null;
  }) {
    const expectedStudyTitle = input?.expectedStudyTitle ?? null;
    let strategySnapshot = await this.client.waitFor(
      () => this.readStrategySnapshot(expectedStudyTitle),
      (snapshot) => snapshot.expectedStudy !== null || snapshot.attachedStudies.length > 0,
      {
        timeoutMs: 10_000,
        intervalMs: 500,
        label: "Study attachment",
      },
    );

    const recoveryActions = [...this.pendingAttachRecoveryActions];
    let attachDiagnostics = buildAttachDiagnostics(
      expectedStudyTitle,
      strategySnapshot.attachedStudies,
      strategySnapshot.expectedStudy,
      recoveryActions,
    );
    if (expectedStudyTitle != null && !attachDiagnostics.exactTitleMatched) {
      const removal = await this.removeAttachedStrategyStudies(expectedStudyTitle);
      if (removal.removedCount > 0) {
        recoveryActions.push("removed_conflicting_strategy_studies");
      }
      if (removal.dismissedIndicatorLimitDialog) {
        recoveryActions.push("dismissed_indicator_limit_dialog");
      }
      await this.client.evaluate<boolean>(focusMonacoEditorExpression());
      await this.client.dispatchCtrlEnter();
      recoveryActions.push("retried_study_attachment");
      await this.client.delay(4_000);
      strategySnapshot = await this.client.waitFor(
        () => this.readStrategySnapshot(expectedStudyTitle),
        (snapshot) => snapshot.expectedStudy !== null,
        {
          timeoutMs: 10_000,
          intervalMs: 500,
          label: "Recovered study attachment",
        },
      );
      attachDiagnostics = buildAttachDiagnostics(
        expectedStudyTitle,
        strategySnapshot.attachedStudies,
        strategySnapshot.expectedStudy,
        recoveryActions,
      );
    }
    if (
      expectedStudyTitle != null &&
      attachDiagnostics.exactTitleMatched &&
      countMatchingStrategyStudies(strategySnapshot.attachedStudies, expectedStudyTitle) > 1
    ) {
      const removal = await this.removeAttachedStrategyStudies(expectedStudyTitle);
      if (removal.removedCount > 0) {
        recoveryActions.push("removed_duplicate_strategy_studies");
      }
      if (removal.dismissedIndicatorLimitDialog) {
        recoveryActions.push("dismissed_indicator_limit_dialog");
      }
      await this.client.evaluate<boolean>(focusMonacoEditorExpression());
      await this.client.dispatchCtrlEnter();
      recoveryActions.push("reattached_single_strategy_study");
      await this.client.delay(4_000);
      strategySnapshot = await this.client.waitFor(
        () => this.readStrategySnapshot(expectedStudyTitle),
        (snapshot) =>
          snapshot.expectedStudy !== null &&
          countMatchingStrategyStudies(snapshot.attachedStudies, expectedStudyTitle) === 1,
        {
          timeoutMs: 10_000,
          intervalMs: 500,
          label: "Deduplicated study attachment",
        },
      );
      attachDiagnostics = buildAttachDiagnostics(
        expectedStudyTitle,
        strategySnapshot.attachedStudies,
        strategySnapshot.expectedStudy,
        recoveryActions,
      );
    }

    this.lastAttachDiagnostics = attachDiagnostics;
    return applyResultSchema.parse({
      ok: attachDiagnostics.exactTitleMatched,
      message: attachDiagnostics.exactTitleMatched
        ? "Pine strategy attached to chart."
        : "Expected study title was not attached to the chart.",
      attachDiagnostics,
      fallbackActions: [],
    });
  }

  public async readArtifactBundle(input?: {
    expectedStudyTitle?: string | null;
    maxTrades?: number;
  }): Promise<ArtifactBundle> {
    const expectedStudyTitle = input?.expectedStudyTitle ?? null;
    let strategySnapshot: StrategySnapshot;
    try {
      strategySnapshot = await this.client.waitFor(
        () => this.readStrategySnapshot(expectedStudyTitle),
        (snapshot) =>
          snapshot.expectedStudy !== null &&
          snapshot.expectedStudy.reportData?.performance?.all != null,
        {
          timeoutMs: 10_000,
          intervalMs: 500,
          label: "Strategy tester report",
        },
      );
    } catch {
      strategySnapshot = await this.readStrategySnapshot(expectedStudyTitle);
    }
    const attachDiagnostics = buildAttachDiagnostics(
      expectedStudyTitle,
      strategySnapshot.attachedStudies,
      strategySnapshot.expectedStudy,
    );
    const reportData = strategySnapshot.expectedStudy?.reportData ?? null;
    const reportDiagnostics = inspectReportData(reportData);
    const strategy = extractBacktestMetricsFromReportData(reportData);
    const rawReportHash = reportData ? sha256(JSON.stringify(reportData)) : null;
    const eventTrace = extractTraceEventsFromReportData(reportData);
    const tvTraceArtifact = buildTvTraceArtifact(eventTrace);

    return artifactBundleSchema.parse({
      strategy,
      trades: extractTradeRecordsFromReportData(reportData, input?.maxTrades ?? 50),
      equity: extractEquitySummaryFromReportData(reportData),
      attachDiagnostics,
      rawReportHash,
      state: {
        ...(await this.readChartState()),
        reportDiagnostics,
        rawReportSnapshot: reportData,
        eventTrace,
        tvTraceArtifact,
      },
    });
  }

  public async buildSyncArtifact(input: {
    chartTarget: ChartTarget;
    compile: CompileResult;
    apply?: {
      attachDiagnostics?: AttachDiagnostics;
    };
  }): Promise<SyncArtifact> {
    return syncArtifactSchema.parse({
      chartTarget: input.chartTarget,
      compile: input.compile,
      apply: input.apply,
      attachDiagnostics: input.apply?.attachDiagnostics ?? this.lastAttachDiagnostics ?? undefined,
      stateAfter: await this.readChartState(),
    });
  }

  public async evaluateAblation(input: {
    condition: ConditionInventoryItem;
    source: string;
  }): Promise<BacktestMetrics | null> {
    const lineNumbers = [...input.condition.pineLineHints].sort((left, right) => right - left);
    if (lineNumbers.length === 0) {
      return null;
    }

    const lines = input.source.split(/\r?\n/);
    for (const lineNumber of lineNumbers) {
      const index = lineNumber - 1;
      if (index >= 0 && index < lines.length) {
        lines[index] = `// ablated:${input.condition.conditionId} ${lines[index]}`;
      }
    }

    const ablatedSource = lines.join("\n");
    const expectedStudyTitle = extractStudyTitle(input.source);
    try {
      await this.updateStrategySource(ablatedSource);
      const compile = await this.compileStrategy();
      if (!compile.ok) {
        return null;
      }

      const apply = await this.applyStrategy({
        expectedStudyTitle,
      });
      if (!apply.ok) {
        return null;
      }

      const artifactBundle = await this.readArtifactBundle({
        expectedStudyTitle,
      });
      return artifactBundle.strategy;
    } finally {
      await this.updateStrategySource(input.source);
      const restoreCompile = await this.compileStrategy();
      if (restoreCompile.ok) {
        await this.applyStrategy({
          expectedStudyTitle,
        });
      }
    }
  }

  public async close(): Promise<void> {
    await this.client.close();
  }

  private async readChartState(): Promise<ChartStateSnapshot> {
    return await this.client.evaluate<ChartStateSnapshot>(readChartStateExpression());
  }

  private async readStrategySnapshot(
    expectedStudyTitle: string | null,
  ): Promise<StrategySnapshot> {
    return await this.client.evaluate<StrategySnapshot>(
      readStrategySnapshotExpression(expectedStudyTitle),
    );
  }

  private async removeAttachedStrategyStudies(
    expectedStudyTitle: string | null,
  ): Promise<StudyRemovalResult> {
    const removal = await this.client.evaluate<StudyRemovalResult>(
      removeAttachedStrategyStudiesExpression(expectedStudyTitle),
    );
    await this.client.waitFor(
      () => this.readChartState(),
      (state) =>
        !state.attachedStudies.some(
          (study) =>
            isAutomationAttachedStudy(study) ||
            isSameStudyFamily(expectedStudyTitle, study.metaDescription) ||
            isSameStudyFamily(expectedStudyTitle, study.normalizedTitle) ||
            isSameStudyFamily(expectedStudyTitle, study.title),
        ),
      {
        timeoutMs: 5_000,
        intervalMs: 250,
        label: "Remove stale strategy studies",
      },
    );
    return removal;
  }

  private async ensurePineEditorReady(label: string): Promise<void> {
    const waitForEditor = async (attemptLabel: string) => {
      await this.client.waitFor(
        async () => {
          await this.client.evaluate<boolean>(openPineEditorExpression(), {
            label: "Pine editor open command",
          });
          return await this.client.evaluate<number>(monacoEditorCountExpression(), {
            label: "Monaco editor attach command",
          });
        },
        (editorCount) => editorCount > 0,
        {
          timeoutMs: this.pineEditorTimeoutMs,
          label: attemptLabel,
        },
      );
    };

    try {
      await waitForEditor(label);
      return;
    } catch (error) {
      const timeoutKind = /monaco/i.test(label)
        ? "Monaco editor attach timeout"
        : "Pine editor open timeout";
      const detail = error instanceof Error ? error.message : String(error);
      try {
        await this.client.reloadPage({
          ignoreCache: true,
          waitMs: PINE_EDITOR_HARD_RELOAD_WAIT_MS,
        });
        await waitForEditor(`${label} after hard reload`);
        return;
      } catch (retryError) {
        const retryDetail =
          retryError instanceof Error ? retryError.message : String(retryError);
        throw new Error(
          `${timeoutKind}: ${label} timed out after ${this.pineEditorTimeoutMs}ms while loading TradingView Pine editor. ${detail} Hard reload recovery failed. ${retryDetail}`,
        );
      }
    }
  }
}

export { TradingViewDesktopExecutor as TradingViewPlaywrightExecutor };

function openPineEditorExpression(): string {
  return `(() => {
    const openSelector = '.pine-dialog, .monaco-editor, [data-name="pine-dialog"], [data-name="pine-editor"]';
    const buttonSelectors = [
      '[data-name="pine-dialog-button"]',
      '[data-name="script-editor"]',
      '[data-name="script-editor-button"]',
      '[aria-label*="pine" i]',
      '[title*="pine" i]',
      '[data-tooltip*="pine" i]',
      '[aria-label*="editor" i]',
      '[title*="editor" i]',
    ];

    const isEditorOpen = () => document.querySelectorAll(openSelector).length > 0;
    if (isEditorOpen()) {
      return true;
    }

    window.TVD?.setFocusPineEditor?.();
    if (isEditorOpen()) {
      return true;
    }

    let button = null;
    for (const selector of buttonSelectors) {
      button = document.querySelector(selector);
      if (button) {
        break;
      }
    }

    if (!button) {
      const clickableCandidates = Array.from(
        document.querySelectorAll('button, [role="button"], [data-name], [aria-label], [title]'),
      );
      button =
        clickableCandidates.find((element) => {
          const text = [
            element.getAttribute?.('aria-label') ?? '',
            element.getAttribute?.('title') ?? '',
            element.getAttribute?.('data-name') ?? '',
            element.getAttribute?.('data-tooltip') ?? '',
            element.textContent ?? '',
          ]
            .join(' ')
            .toLowerCase();
          return text.includes('pine') || text.includes('editor');
        }) ?? null;
    }

    if (!button) {
      return false;
    }

    button.click();
    if (typeof MouseEvent === 'function') {
      button.dispatchEvent?.(
        new MouseEvent('click', {
          bubbles: true,
          cancelable: true,
        }),
      );
    }
    return true;
  })()`;
}

function monacoEditorCountExpression(): string {
  return buildMonacoBridgeExpression(
    "return monaco?.editor?.getEditors?.().length ?? 0;",
  );
}

function setMonacoSourceExpression(source: string): string {
  return buildMonacoBridgeExpression(`
    if (!editor) {
      throw new Error("Monaco editor is not available.");
    }

    editor.focus();
    editor.getModel().setValue(${JSON.stringify(source)});
    return true;
  `);
}

function focusMonacoEditorExpression(): string {
  return buildMonacoBridgeExpression(`
    if (!editor) {
      throw new Error("Monaco editor is not available.");
    }

    editor.focus();
    window.TVD?.setFocusPineEditor?.();
    return true;
  `);
}

function readMonacoMarkersExpression(): string {
  return buildMonacoBridgeExpression(`
    if (!editor || !monaco) {
      throw new Error("Monaco editor is not available.");
    }

    const model = editor.getModel();
    return monaco.editor
      .getModelMarkers({ resource: model.uri })
      .map((marker) => ({
        message: marker.message,
        severity: marker.severity,
      }));
  `);
}

function buildMonacoBridgeExpression(body: string): string {
  return `(() => {
    const resolveMonaco = () => {
      const directCandidates = [
        window.monaco,
        window.tvMonaco,
        window.__MONACO__,
        window.TradingViewMonaco,
      ];
      for (const candidate of directCandidates) {
        if (candidate?.editor?.getEditors) {
          return candidate;
        }
      }

      const chunk = window.webpackChunktradingview;
      if (Array.isArray(chunk)) {
        try {
          chunk.push([[Symbol("af-monaco-bridge")], {}, (req) => {
            window.__afCdpReq = req;
          }]);
        } catch {}
      }

      const req = window.__afCdpReq;
      if (typeof req === 'function') {
        const candidates = [];
        const pushCandidate = (candidate) => {
          if (candidate && !candidates.includes(candidate)) {
            candidates.push(candidate);
          }
        };

        try {
          pushCandidate(req(${MONACO_MODULE_ID}));
        } catch {}

        for (const moduleRecord of Object.values(req.c ?? {})) {
          pushCandidate(moduleRecord?.exports);
          pushCandidate(moduleRecord?.exports?.default);
        }

        for (const candidate of candidates) {
          if (candidate?.editor?.getEditors) {
            return candidate;
          }
        }
      }

      return null;
    };

    const monaco = resolveMonaco();
    const editor = monaco?.editor?.getEditors?.()?.[0] ?? null;
    ${body}
  })()`;
}

function setChartTargetExpression(input: ChartTarget): string {
  return `(() => {
    const collection = studyMarket?._chartWidgetCollection;
    const active = collection?.activeChartWidget?.value?.() ?? collection?.activeChartWidget ?? null;
    if (!active) {
      throw new Error("TradingView active chart widget is not available.");
    }

    const operations = [];
    if (typeof active.setSymbol === "function" && active.getSymbol?.() !== ${JSON.stringify(input.symbol)}) {
      operations.push(Promise.resolve(active.setSymbol(${JSON.stringify(input.symbol)})));
    }
    if (typeof active.setResolution === "function" && active.getResolution?.() !== ${JSON.stringify(input.timeframe)}) {
      operations.push(Promise.resolve(active.setResolution(${JSON.stringify(input.timeframe)})));
    }

    return Promise.all(operations).then(() => true);
  })()`;
}

function readChartStateExpression(): string {
  return `(() => {
    const collection = studyMarket?._chartWidgetCollection;
    const active = collection?.activeChartWidget?.value?.() ?? collection?.activeChartWidget ?? null;
    const model = active?.model?.();
    const attachedStudies = Array.from(model?.dataSources?.() ?? [])
      .map((source) => {
        const metaDescription = source?.metaInfo?.()?.description ?? null;
        const title = source?.title?.()?.toString?.() ?? null;
        return {
          title,
          normalizedTitle: title ? title.replace(/\\s+\\([^)]*\\)$/, "").trim() : null,
          metaDescription,
          hasStrategyData:
            Boolean(source?.reportData?.()?.performance) ||
            typeof source?.ordersData === "function",
        };
      })
      .filter((source) => source.metaDescription || source.hasStrategyData);

    return {
      symbol: active?.getSymbol?.() ?? null,
      timeframe: active?.getResolution?.() ?? null,
      pineEditorOpen: document.querySelectorAll('.pine-dialog').length > 0,
      attachedStudies,
    };
  })()`;
}

function readStrategySnapshotExpression(expectedStudyTitle: string | null): string {
  return `(() => {
    const normalizeTitle = (title) =>
      title ? title.replace(/\\s+\\([^)]*\\)$/, "").trim() : null;
    const collection = studyMarket?._chartWidgetCollection;
    const active = collection?.activeChartWidget?.value?.() ?? collection?.activeChartWidget ?? null;
    const model = active?.model?.();
    const studies = Array.from(model?.dataSources?.() ?? [])
      .map((source) => {
        const title = source?.title?.()?.toString?.() ?? null;
        const metaDescription = source?.metaInfo?.()?.description ?? null;
        const reportData = source?.reportData?.() ?? null;
        const hasStrategyData =
          Boolean(reportData?.performance) || typeof source?.ordersData === "function";
        return {
          title,
          normalizedTitle: normalizeTitle(title),
          metaDescription,
          reportData: hasStrategyData
            ? {
                performance: reportData?.performance ?? null,
                trades: reportData?.trades ?? [],
                currency: reportData?.currency ?? null,
                buyHold: reportData?.buyHold ?? [],
                buyHoldPercent: reportData?.buyHoldPercent ?? [],
              }
            : null,
          hasStrategyData,
        };
      })
      .filter((study) => study.metaDescription || study.hasStrategyData);

    const expectedStudy = studies.find((study) => {
      if (!study.hasStrategyData) {
        return false;
      }

      return (
        study.metaDescription === ${JSON.stringify(expectedStudyTitle)} ||
        study.normalizedTitle === ${JSON.stringify(expectedStudyTitle)} ||
        ${JSON.stringify(expectedStudyTitle)} === null
      );
    }) ?? null;

    return {
      attachedStudies: studies.map((study) => ({
        title: study.title,
        normalizedTitle: study.normalizedTitle,
        metaDescription: study.metaDescription,
        hasStrategyData: study.hasStrategyData,
      })),
      expectedStudy,
    };
  })()`;
}

function removeAttachedStrategyStudiesExpression(expectedStudyTitle: string | null): string {
  return `(() => {
    const expectedStudyTitle = ${JSON.stringify(expectedStudyTitle)};
    const normalizeTitle = (title) =>
      title ? title.replace(/\\s+\\([^)]*\\)$/, "").replace(/\\s*\\[cand-[^\\]]+\\]$/, "").trim() : null;
    const studyFamily = (title) => {
      const normalized = normalizeTitle(title);
      if (!normalized) {
        return null;
      }
      return normalized.split(" - ")[0]?.trim() ?? normalized;
    };
    const isAutomationStudyTitle = (title) => {
      const normalized = normalizeTitle(title);
      if (!normalized) {
        return false;
      }
      return /^(AF Spec v1|AF Seed|Exhaustion Signal|AF Mock Candidate|AF Exploration)/i.test(normalized) ||
        /\\[cand-[^\\]]+\\]/i.test(normalized);
    };
    const dismissIndicatorLimitDialog = () => {
      const dialogCandidates = Array.from(
        document.querySelectorAll('[role="dialog"], [data-dialog-name], div'),
      )
        .filter((element) => {
          const text = (element.textContent ?? '').replace(/\\s+/g, ' ');
          return /\\uB354 \\uB9CE\\uC740 \\uC778\\uB514\\uCF00\\uC774\\uD130|\\uCD5C\\uB300\\uCE58\\uC778\\s*2\\uAC1C\\uC758 \\uC9C0\\uD45C|maximum.*indicators|too many indicators|indicator limit/i.test(text);
        })
        .map((element) => ({
          element,
          rect: element.getBoundingClientRect?.() ?? {
            top: 0,
            right: 0,
            width: Number.MAX_SAFE_INTEGER,
            height: Number.MAX_SAFE_INTEGER,
          },
        }))
        .sort(
          (left, right) =>
            left.rect.width * left.rect.height - right.rect.width * right.rect.height,
        );
      const dialog = dialogCandidates[0]?.element ?? null;
      if (!dialog) {
        return false;
      }
      const dialogRect = dialog.getBoundingClientRect?.() ?? null;

      const closeButtons = Array.from(
        dialog.querySelectorAll('button, [role="button"], [aria-label], [title]'),
      )
        .map((element) => {
          const rect = element.getBoundingClientRect?.() ?? null;
          const text = [
            element.getAttribute?.('aria-label') ?? '',
            element.getAttribute?.('title') ?? '',
            element.textContent ?? '',
          ].join(' ').trim();
          const closeLabelMatch = /close|dismiss|\\uB2EB\\uAE30|\\u00d7|x/i.test(text);
          const topRightDistance =
            dialogRect && rect
              ? Math.abs(rect.top - dialogRect.top) + Math.abs(rect.right - dialogRect.right)
              : Number.MAX_SAFE_INTEGER;
          return {
            element,
            rect,
            closeLabelMatch,
            topRightDistance,
          };
        })
        .filter((entry) => {
          if (!entry.rect) {
            return entry.closeLabelMatch;
          }
          return entry.rect.width > 0 && entry.rect.height > 0;
        })
        .sort((left, right) => {
          if (left.closeLabelMatch !== right.closeLabelMatch) {
            return left.closeLabelMatch ? -1 : 1;
          }
          return left.topRightDistance - right.topRightDistance;
        });
      const closeButton = closeButtons[0]?.element ?? null;
      if (!closeButton) {
        document.dispatchEvent?.(
          new KeyboardEvent('keydown', {
            key: 'Escape',
            code: 'Escape',
            keyCode: 27,
            bubbles: true,
            cancelable: true,
          }),
        );
        return false;
      }
      const rect = closeButton.getBoundingClientRect?.() ?? null;
      const eventOptions = rect
        ? {
            bubbles: true,
            cancelable: true,
            clientX: rect.left + rect.width / 2,
            clientY: rect.top + rect.height / 2,
          }
        : {
            bubbles: true,
            cancelable: true,
          };
      closeButton.dispatchEvent?.(new PointerEvent('pointerdown', eventOptions));
      closeButton.dispatchEvent?.(new MouseEvent('mousedown', eventOptions));
      closeButton.dispatchEvent?.(new PointerEvent('pointerup', eventOptions));
      closeButton.dispatchEvent?.(new MouseEvent('mouseup', eventOptions));
      closeButton.dispatchEvent?.(new MouseEvent('click', eventOptions));
      closeButton.click?.();
      return true;
    };
    const expectedFamily = studyFamily(expectedStudyTitle);
    const collection = studyMarket?._chartWidgetCollection;
    const active = collection?.activeChartWidget?.value?.() ?? collection?.activeChartWidget ?? null;
    const model = active?.model?.();
    if (!model || typeof model.dataSources !== "function") {
      throw new Error("TradingView chart model is not available.");
    }

    const removable = Array.from(model.dataSources())
      .filter((source) => {
        const title = source?.title?.()?.toString?.() ?? null;
        const metaDescription = source?.metaInfo?.()?.description ?? null;
        const reportData = source?.reportData?.() ?? null;
        const hasStrategyData =
          Boolean(reportData?.performance) || typeof source?.ordersData === "function";
        const sourceFamily = studyFamily(metaDescription) ?? studyFamily(title);
        return (
          hasStrategyData ||
          isAutomationStudyTitle(metaDescription) ||
          isAutomationStudyTitle(title) ||
          (expectedFamily !== null && sourceFamily === expectedFamily)
        );
      });

    removable.forEach((source) => {
      model.removeSource?.(source, false);
    });
    return {
      removedCount: removable.length,
      dismissedIndicatorLimitDialog: dismissIndicatorLimitDialog(),
    };
  })()`;
}

function buildAttachDiagnostics(
  expectedStudyTitle: string | null,
  attachedStudies: AttachedStudySnapshot[],
  expectedStudy:
    | {
        title: string | null;
        normalizedTitle: string | null;
        metaDescription: string | null;
      }
    | null,
  recoveryActions: string[] = [],
): AttachDiagnostics {
  const conflictingAttachedStudy = attachedStudies.find(
    (study) =>
      isSameStudyFamily(expectedStudyTitle, study.metaDescription) ||
      isSameStudyFamily(expectedStudyTitle, study.normalizedTitle) ||
      isSameStudyFamily(expectedStudyTitle, study.title),
  );
  const detectedStudyTitle =
    expectedStudy?.metaDescription ??
    expectedStudy?.normalizedTitle ??
    expectedStudy?.title ??
    attachedStudies.find((study) => study.hasStrategyData)?.metaDescription ??
    attachedStudies.find((study) => study.hasStrategyData)?.normalizedTitle ??
    conflictingAttachedStudy?.metaDescription ??
    conflictingAttachedStudy?.normalizedTitle ??
    conflictingAttachedStudy?.title ??
    null;
  const exactTitleMatched =
    expectedStudyTitle == null
      ? expectedStudy !== null
      : detectedStudyTitle === expectedStudyTitle ||
        normalizeAttachedStudyTitle(expectedStudy?.title) === expectedStudyTitle;

  return {
    expectedStudyTitle,
    detectedStudyTitle,
    exactTitleMatched,
    staleStudySuspected:
      expectedStudyTitle != null &&
      !exactTitleMatched &&
      attachedStudies.some(
        (study) =>
          study.hasStrategyData ||
          isSameStudyFamily(expectedStudyTitle, study.metaDescription) ||
          isSameStudyFamily(expectedStudyTitle, study.normalizedTitle) ||
          isSameStudyFamily(expectedStudyTitle, study.title),
      ),
    recoveryActions,
  };
}

function isSameStudyFamily(
  expectedStudyTitle: string | null,
  actualStudyTitle: string | null,
): boolean {
  const expectedFamily = studyFamilyName(expectedStudyTitle);
  const actualFamily = studyFamilyName(actualStudyTitle);
  return expectedFamily !== null && actualFamily !== null && expectedFamily === actualFamily;
}

function isAutomationAttachedStudy(study: AttachedStudySnapshot): boolean {
  return (
    study.hasStrategyData ||
    isAutomationStudyTitle(study.metaDescription) ||
    isAutomationStudyTitle(study.normalizedTitle) ||
    isAutomationStudyTitle(study.title)
  );
}

function isAutomationStudyTitle(title: string | null): boolean {
  const normalized = normalizeAttachedStudyTitle(title);
  if (!normalized) {
    return false;
  }

  return (
    /^(AF Spec v1|AF Seed|Exhaustion Signal|AF Mock Candidate|AF Exploration)/i.test(
      normalized,
    ) || /\[cand-[^\]]+\]/i.test(normalized)
  );
}

function studyFamilyName(title: string | null): string | null {
  const normalized = normalizeAttachedStudyTitle(title)?.replace(
    /\s*\[cand-[^\]]+\]$/,
    "",
  );
  if (!normalized) {
    return null;
  }
  return normalized.split(" - ")[0]?.trim() ?? normalized;
}

function countMatchingStrategyStudies(
  attachedStudies: AttachedStudySnapshot[],
  expectedStudyTitle: string,
): number {
  return attachedStudies.filter(
    (study) =>
      study.hasStrategyData &&
      (study.metaDescription === expectedStudyTitle ||
        study.normalizedTitle === expectedStudyTitle ||
        study.title === expectedStudyTitle ||
        normalizeAttachedStudyTitle(study.title) === expectedStudyTitle),
  ).length;
}

function normalizeResolution(value: string | null): string | null {
  if (!value) {
    return null;
  }

  if (value === "2H") {
    return "120";
  }

  return value;
}

function normalizeSymbol(value: string | null): string | null {
  if (!value) {
    return null;
  }

  return value.split(":").at(-1) ?? value;
}

function deduplicateErrors(errors: string[]): string[] {
  return [...new Set(errors)];
}

export const __test__ = {
  openPineEditorExpression,
  monacoEditorCountExpression,
  setMonacoSourceExpression,
  focusMonacoEditorExpression,
  readMonacoMarkersExpression,
  removeAttachedStrategyStudiesExpression,
};
