import vm from "node:vm";

import { describe, expect, test, vi } from "vitest";

import { TradingViewDesktopCdpClient } from "../../src/automation/tradingview/cdp-client.js";
import {
  TradingViewDesktopExecutor,
  __test__,
} from "../../src/automation/tradingview/playwright-driver.js";

function runExpression<T>(expression: string, context: Record<string, unknown>): T {
  return vm.runInNewContext(expression, context) as T;
}

describe("TradingView playwright driver expressions", () => {
  test("closes the underlying CDP client through the executor contract", async () => {
    const closeSpy = vi
      .spyOn(TradingViewDesktopCdpClient.prototype, "close")
      .mockResolvedValue();
    const executor = new TradingViewDesktopExecutor({
      cdpUrl: "http://127.0.0.1:65535",
    });

    await executor.close();

    expect(closeSpy).toHaveBeenCalledTimes(1);
    closeSpy.mockRestore();
  });

  test("hard reloads the chart when Pine editor attachment stalls", async () => {
    let waitCalls = 0;
    const evaluateSpy = vi
      .spyOn(TradingViewDesktopCdpClient.prototype, "evaluate")
      .mockImplementation(async <T>() => true as T);
    const reloadSpy = vi
      .spyOn(TradingViewDesktopCdpClient.prototype, "reloadPage")
      .mockResolvedValue();
    const waitSpy = vi
      .spyOn(TradingViewDesktopCdpClient.prototype, "waitFor")
      .mockImplementation(async <T>() => {
        waitCalls += 1;
        if (waitCalls === 1) {
          throw new Error("Pine editor open timed out after 15000ms.");
        }
        if (waitCalls === 3) {
          return {
            symbol: "QQQ",
            timeframe: "120",
            pineEditorOpen: true,
            attachedStudies: [],
          } as T;
        }
        return 1 as T;
      });
    const executor = new TradingViewDesktopExecutor({
      cdpUrl: "http://127.0.0.1:65535",
    });

    await executor.prepareChart({
      symbol: "QQQ",
      timeframe: "120",
      chartType: "candles",
    });

    expect(reloadSpy).toHaveBeenCalledWith({
      ignoreCache: true,
      waitMs: 12_000,
    });
    expect(waitCalls).toBe(4);
    evaluateSpy.mockRestore();
    reloadSpy.mockRestore();
    waitSpy.mockRestore();
  });

  test("opens the Pine editor through fallback clickable-element discovery", () => {
    let clicked = 0;
    const button = {
      textContent: "Open Pine Editor",
      getAttribute(name: string) {
        if (name === "aria-label") {
          return "Open Pine Editor";
        }
        return null;
      },
      click() {
        clicked += 1;
      },
      dispatchEvent() {
        clicked += 1;
        return true;
      },
    };

    const context = {
      window: {
        TVD: {},
      },
      document: {
        querySelector() {
          return null;
        },
        querySelectorAll(selector: string) {
          if (
            selector ===
            ".pine-dialog, .monaco-editor, [data-name=\"pine-dialog\"], [data-name=\"pine-editor\"]"
          ) {
            return [];
          }
          if (
            selector ===
            "button, [role=\"button\"], [data-name], [aria-label], [title]"
          ) {
            return [button];
          }
          return [];
        },
      },
      MouseEvent: function MouseEvent() {
        return {};
      },
      Symbol,
      Array,
      Object,
      JSON,
    };

    const result = runExpression<boolean>(__test__.openPineEditorExpression(), context);

    expect(result).toBe(true);
    expect(clicked).toBeGreaterThan(0);
  });

  test("opens the web Pine editor through the bottom script editor widget", async () => {
    const calls: string[] = [];
    const pineEditor = {
      open: vi.fn(async () => {
        calls.push("open-pine-editor");
      }),
    };
    const bar = {
      waitForWidgetsInitialized: vi.fn(async () => {
        calls.push("wait");
      }),
      setWidgetAvailability: vi.fn(() => {
        calls.push("available");
      }),
      _isHidden: {
        setValue: vi.fn(() => {
          calls.push("visible-container");
        }),
      },
      _isVisible: {
        setValue: vi.fn(),
      },
      _isBridgeVisible: {
        setValue: vi.fn(),
      },
      show: vi.fn(),
      setNormalHeight: vi.fn(),
      setMode: vi.fn(),
      open: vi.fn(),
      _activeWidget: {
        setValue(value: string) {
          calls.push(`active:${value}`);
        },
      },
      _createWidgetBarAPI: vi.fn(() => ({ widgetBarApi: true })),
      _updateActiveWidget: vi.fn(async () => {
        calls.push("update-active-widget");
      }),
      getWidgetByName: vi.fn((name: string) =>
        name === "scripteditor" ? pineEditor : null,
      ),
      _config: {
        scripteditor: {
          ctor: {
            hasInstance: vi.fn(() => false),
          },
        },
      },
    };

    const context = {
      window: {
        TradingView: {
          bottomWidgetBar: bar,
        },
      },
      document: {
        querySelector(selector: string) {
          if (selector === "[data-name=\"pine-dialog\"]") {
            return null;
          }
          return null;
        },
        querySelectorAll(selector: string) {
          if (selector === ".monaco-editor") {
            return [];
          }
          return [];
        },
      },
      Array,
      Date,
      Object,
      Promise,
    };

    const result = await runExpression<Promise<boolean>>(
      __test__.openWebPineEditorExpression(),
      context,
    );

    expect(result).toBe(true);
    expect(calls).toContain("active:scripteditor");
    expect(calls).toContain("update-active-widget");
    expect(pineEditor.open).toHaveBeenCalledWith(null, {
      source: "af_web_calibration",
    });
  });

  test("resolves Monaco from webpack cache instead of relying on a single module id", () => {
    const monaco = {
      editor: {
        getEditors() {
          return [{ id: "editor-1" }];
        },
      },
    };
    const req = Object.assign(
      () => {
        throw new Error("module not found");
      },
      {
        c: {
          12345: {
            exports: monaco,
          },
        },
      },
    );
    const chunk: unknown[] = [];
    chunk.push = ((payload: unknown[]) => {
      const callback = payload[2] as (requireFn: typeof req) => void;
      callback(req);
      return 1;
    }) as typeof chunk.push;

    const context = {
      window: {
        webpackChunktradingview: chunk,
      },
      Symbol,
      Array,
      Object,
      JSON,
    };

    const editorCount = runExpression<number>(
      __test__.monacoEditorCountExpression(),
      context,
    );

    expect(editorCount).toBe(1);
  });

  test("sets Monaco source through a direct global Monaco reference", () => {
    let currentValue = "";
    let focused = 0;
    const model = {
      setValue(value: string) {
        currentValue = value;
      },
    };
    const editor = {
      focus() {
        focused += 1;
      },
      getModel() {
        return model;
      },
    };

    const context = {
      window: {
        monaco: {
          editor: {
            getEditors() {
              return [editor];
            },
          },
        },
      },
      Symbol,
      Array,
      Object,
      JSON,
    };

    const result = runExpression<boolean>(
      __test__.setMonacoSourceExpression("//@version=5\nstrategy(\"X\")"),
      context,
    );

    expect(result).toBe(true);
    expect(focused).toBe(1);
    expect(currentValue).toContain("strategy(\"X\")");
  });

  test("removes stale strategy studies and dismisses indicator-limit dialogs", () => {
    const removed: unknown[] = [];
    let closeClicked = false;
    const staleStrategy = {
      title() {
        return "AF Spec v1 [cand-old]";
      },
      metaInfo() {
        return { description: "AF Spec v1 [cand-old]" };
      },
      reportData() {
        return { performance: { all: {} } };
      },
      ordersData() {
        return [];
      },
    };
    const unrelatedStudy = {
      title() {
        return "Volume";
      },
      metaInfo() {
        return { description: "Volume" };
      },
      reportData() {
        return null;
      },
    };
    const closeButton = {
      textContent: "×",
      getAttribute() {
        return null;
      },
      getBoundingClientRect() {
        return {
          top: 338,
          right: 866,
          left: 838,
          width: 28,
          height: 28,
        };
      },
      dispatchEvent() {
        return true;
      },
      click() {
        closeClicked = true;
      },
    };
    const dialog = {
      textContent:
        "더 많은 인디케이터, 더 많은 트레이딩 기회 현재 플랜에서 사용할 수 있는 최대치인 2개의 지표를 적용했습니다.",
      querySelectorAll() {
        return [closeButton];
      },
      getBoundingClientRect() {
        return {
          top: 330,
          right: 874,
          left: 266,
          width: 608,
          height: 700,
        };
      },
    };
    const context = {
      studyMarket: {
        _chartWidgetCollection: {
          activeChartWidget: {
            model() {
              return {
                dataSources() {
                  return [staleStrategy, unrelatedStudy];
                },
                removeSource(source: unknown) {
                  removed.push(source);
                },
              };
            },
          },
        },
      },
      document: {
        querySelectorAll(selector: string) {
          if (selector === "[role=\"dialog\"], [data-dialog-name], div") {
            return [dialog];
          }
          return [];
        },
      },
      Array,
      JSON,
      RegExp,
      KeyboardEvent: function KeyboardEvent() {
        return {};
      },
      MouseEvent: function MouseEvent() {
        return {};
      },
      PointerEvent: function PointerEvent() {
        return {};
      },
    };

    const result = runExpression<{ removedCount: number; dismissedIndicatorLimitDialog: boolean }>(
      __test__.removeAttachedStrategyStudiesExpression("AF Spec v1 [cand-new]"),
      context,
    );

    expect(result.removedCount).toBe(1);
    expect(result.dismissedIndicatorLimitDialog).toBe(true);
    expect(removed).toEqual([staleStrategy]);
    expect(closeClicked).toBe(true);
  });

  test("removes AF automation studies even when TradingView has no strategy report", () => {
    const removed: unknown[] = [];
    const staleAutomationStudy = {
      title() {
        return "AF Spec v1 [cand-185ff5a5]";
      },
      metaInfo() {
        return { description: "AF Spec v1 [cand-185ff5a5]" };
      },
      reportData() {
        return null;
      },
    };
    const unrelatedStudy = {
      title() {
        return "Volume";
      },
      metaInfo() {
        return { description: "Volume" };
      },
      reportData() {
        return null;
      },
    };
    const context = {
      studyMarket: {
        _chartWidgetCollection: {
          activeChartWidget: {
            model() {
              return {
                dataSources() {
                  return [staleAutomationStudy, unrelatedStudy];
                },
                removeSource(source: unknown) {
                  removed.push(source);
                },
              };
            },
          },
        },
      },
      document: {
        querySelectorAll() {
          return [];
        },
      },
      Array,
      JSON,
      RegExp,
      KeyboardEvent: function KeyboardEvent() {
        return {};
      },
      MouseEvent: function MouseEvent() {
        return {};
      },
      PointerEvent: function PointerEvent() {
        return {};
      },
    };

    const result = runExpression<{ removedCount: number; dismissedIndicatorLimitDialog: boolean }>(
      __test__.removeAttachedStrategyStudiesExpression(null),
      context,
    );

    expect(result.removedCount).toBe(1);
    expect(result.dismissedIndicatorLimitDialog).toBe(false);
    expect(removed).toEqual([staleAutomationStudy]);
  });

  test("pre-cleans TradingView studies before Ctrl+Enter can hit the indicator limit", async () => {
    const events: string[] = [];
    const evaluateSpy = vi
      .spyOn(TradingViewDesktopCdpClient.prototype, "evaluate")
      .mockImplementation(async <T>(expression: string) => {
        if (expression.includes("removeSource")) {
          events.push("remove-studies");
          return {
            removedCount: 2,
            dismissedIndicatorLimitDialog: true,
          } as T;
        }
        if (expression.includes("getModelMarkers")) {
          events.push("read-markers");
          return [] as T;
        }
        events.push("evaluate");
        return true as T;
      });
    const waitSpy = vi
      .spyOn(TradingViewDesktopCdpClient.prototype, "waitFor")
      .mockImplementation(async <T>() => {
        events.push("wait-clean");
        return {
          symbol: "QQQ",
          timeframe: "120",
          pineEditorOpen: true,
          attachedStudies: [],
        } as T;
      });
    const dispatchSpy = vi
      .spyOn(TradingViewDesktopCdpClient.prototype, "dispatchCtrlEnter")
      .mockImplementation(async () => {
        events.push("ctrl-enter");
      });
    const delaySpy = vi
      .spyOn(TradingViewDesktopCdpClient.prototype, "delay")
      .mockResolvedValue();
    const executor = new TradingViewDesktopExecutor({
      cdpUrl: "http://127.0.0.1:65535",
    });
    (
      executor as unknown as {
        pendingStudyTitle: string | null;
        pendingAttachRecoveryActions: string[];
      }
    ).pendingStudyTitle = "AF Spec v1 [cand-new]";

    const result = await executor.compileStrategy();

    expect(result.ok).toBe(true);
    expect(events.indexOf("remove-studies")).toBeGreaterThanOrEqual(0);
    expect(events.indexOf("ctrl-enter")).toBeGreaterThan(
      events.indexOf("remove-studies"),
    );
    expect(
      (
        executor as unknown as {
          pendingAttachRecoveryActions: string[];
        }
      ).pendingAttachRecoveryActions,
    ).toEqual([
      "pre_removed_existing_strategy_studies",
      "dismissed_indicator_limit_dialog",
    ]);
    evaluateSpy.mockRestore();
    waitSpy.mockRestore();
    dispatchSpy.mockRestore();
    delaySpy.mockRestore();
  });
});
