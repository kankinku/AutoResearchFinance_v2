import vm from "node:vm";

import { describe, expect, test } from "vitest";

import { __test__ } from "../../src/automation/tradingview/playwright-driver.js";

function runExpression<T>(expression: string, context: Record<string, unknown>): T {
  return vm.runInNewContext(expression, context) as T;
}

describe("TradingView playwright driver expressions", () => {
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
});
