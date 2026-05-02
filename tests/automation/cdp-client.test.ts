import { afterEach, describe, expect, test, vi } from "vitest";

import {
  buildTradingViewExecutableCandidates,
  TradingViewDesktopCdpClient,
} from "../../src/automation/tradingview/cdp-client.js";

const originalFetch = globalThis.fetch;
const originalWebSocket = globalThis.WebSocket;

afterEach(() => {
  globalThis.fetch = originalFetch;
  globalThis.WebSocket = originalWebSocket;
  vi.restoreAllMocks();
});

describe("buildTradingViewExecutableCandidates", () => {
  test("prioritizes configured and appx paths before common Windows defaults", () => {
    expect(
      buildTradingViewExecutableCandidates({
        configuredPath: "C:\\custom\\TradingView.exe",
        appxInstallLocation:
          "C:\\Program Files\\WindowsApps\\TradingView.Desktop_3.1.0.7818_x64__n534cwy3pjxzj",
        localAppData: "C:\\Users\\hanji\\AppData\\Local",
        programFiles: "C:\\Program Files",
        programFilesX86: "C:\\Program Files (x86)",
      }),
    ).toEqual([
      "C:\\custom\\TradingView.exe",
      "C:\\Program Files\\WindowsApps\\TradingView.Desktop_3.1.0.7818_x64__n534cwy3pjxzj\\TradingView.exe",
      "C:\\Users\\hanji\\AppData\\Local\\Programs\\TradingView\\TradingView.exe",
      "C:\\Program Files\\TradingView\\TradingView.exe",
      "C:\\Program Files (x86)\\TradingView\\TradingView.exe",
    ]);
  });

  test("drops empty values and de-duplicates repeated paths", () => {
    expect(
      buildTradingViewExecutableCandidates({
        configuredPath: "C:\\same\\TradingView.exe",
        appxInstallLocation: "C:\\same",
        localAppData: "",
        programFiles: undefined,
        programFilesX86: undefined,
      }),
    ).toEqual(["C:\\same\\TradingView.exe"]);
  });

  test("times out an unresponsive Runtime.evaluate command", async () => {
    globalThis.fetch = vi.fn(async (url: string | URL | Request) => {
      const value = String(url);
      if (value.endsWith("/json/version")) {
        return { ok: true } as Response;
      }
      if (value.endsWith("/json/list")) {
        return {
          ok: true,
          async json() {
            return [
              {
                title: "TradingView chart",
                url: "https://www.tradingview.com/chart/test",
                webSocketDebuggerUrl: "ws://127.0.0.1/devtools/page/1",
              },
            ];
          },
        } as Response;
      }
      return { ok: false } as Response;
    }) as typeof fetch;

    class FakeWebSocket {
      private listeners = new Map<string, Array<(event: { data: string }) => void>>();

      public constructor() {
        setTimeout(() => this.emit("open", { data: "" }), 0);
      }

      public send(data: string): void {
        const payload = JSON.parse(data) as { id: number; method: string };
        if (payload.method === "Runtime.enable" || payload.method === "Page.enable") {
          setTimeout(
            () =>
              this.emit("message", {
                data: JSON.stringify({ id: payload.id, result: {} }),
              }),
            0,
          );
        }
      }

      public close(): void {
        this.emit("close", { data: "" });
      }

      public addEventListener(
        type: string,
        listener: (event: { data: string }) => void,
      ): void {
        const existing = this.listeners.get(type) ?? [];
        existing.push(listener);
        this.listeners.set(type, existing);
      }

      private emit(type: string, event: { data: string }): void {
        for (const listener of this.listeners.get(type) ?? []) {
          listener(event);
        }
      }
    }

    globalThis.WebSocket =
      FakeWebSocket as unknown as typeof globalThis.WebSocket;

    const client = new TradingViewDesktopCdpClient({
      cdpUrl: "http://127.0.0.1:9222",
      commandTimeoutMs: 10,
    });

    await expect(
      client.evaluate("1", {
        label: "Pine editor open command",
      }),
    ).rejects.toThrow(
      "TradingView CDP command Pine editor open command timed out after 10ms.",
    );
  });
});
