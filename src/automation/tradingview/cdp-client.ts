import path from "node:path";
import { access, mkdir } from "node:fs/promises";
import { execFile, spawn } from "node:child_process";

import { chromium } from "playwright";

interface CdpTargetInfo {
  title: string;
  url: string;
  webSocketDebuggerUrl: string;
}

interface PendingMessage {
  resolve: (value: unknown) => void;
  reject: (error: Error) => void;
}

interface CdpResponse {
  id?: number;
  result?: {
    result?: {
      value?: unknown;
      description?: string;
    };
    exceptionDetails?: {
      text?: string;
      exception?: {
        description?: string;
      };
    };
  };
  error?: {
    message?: string;
  };
}

interface TradingViewDesktopCdpClientConfig {
  surface?: "desktop" | "web";
  cdpUrl?: string;
  executablePath?: string;
  webProfileDir?: string;
  webChartUrl?: string;
  webHeadless?: boolean;
  connectTimeoutMs?: number;
  commandTimeoutMs?: number;
}

interface WebSocketMessageEventLike {
  data: unknown;
}

interface WebSocketLike {
  send(data: string): void;
  close(): void;
  addEventListener(
    type: string,
    listener: (event: WebSocketMessageEventLike) => void,
    options?: { once?: boolean },
  ): void;
}

const DEFAULT_CDP_URL = "http://127.0.0.1:9222";
const DEFAULT_WEB_CDP_URL = "http://127.0.0.1:9223";
const DEFAULT_TRADINGVIEW_WEB_CHART_URL = "https://www.tradingview.com/chart/";
const DEFAULT_CONNECT_TIMEOUT_MS = 20_000;
const DEFAULT_COMMAND_TIMEOUT_MS = 8_000;
const CHART_TARGET_PATTERN = /tradingview\.com\/chart\//i;
const TRADINGVIEW_EXECUTABLE_NAME = "TradingView.exe";
const TRADINGVIEW_PROCESS_IMAGE = "TradingView.exe";

export class TradingViewDesktopCdpClient {
  private readonly cdpBaseUrl: string;
  private readonly surface: "desktop" | "web";
  private readonly connectTimeoutMs: number;
  private readonly commandTimeoutMs: number;
  private socket: WebSocketLike | null = null;
  private messageId = 0;
  private readonly pending = new Map<number, PendingMessage>();

  public constructor(private readonly config: TradingViewDesktopCdpClientConfig) {
    this.surface = config.surface ?? "desktop";
    this.cdpBaseUrl = normalizeCdpBaseUrl(config.cdpUrl, this.surface);
    this.connectTimeoutMs = config.connectTimeoutMs ?? DEFAULT_CONNECT_TIMEOUT_MS;
    this.commandTimeoutMs = config.commandTimeoutMs ?? DEFAULT_COMMAND_TIMEOUT_MS;
  }

  public async connect(): Promise<void> {
    if (this.socket) {
      return;
    }

    if (this.surface === "web") {
      await ensureWebDebugEndpoint({
        cdpBaseUrl: this.cdpBaseUrl,
        executablePath: this.config.executablePath,
        profileDir: this.config.webProfileDir,
        chartUrl: this.config.webChartUrl,
        headless: this.config.webHeadless,
        connectTimeoutMs: this.connectTimeoutMs,
      });
      await ensureChartTargetOpen({
        cdpBaseUrl: this.cdpBaseUrl,
        chartUrl: this.config.webChartUrl,
        connectTimeoutMs: this.connectTimeoutMs,
      });
    } else {
      await ensureDesktopDebugEndpoint({
        cdpBaseUrl: this.cdpBaseUrl,
        executablePath: this.config.executablePath,
        connectTimeoutMs: this.connectTimeoutMs,
      });
    }

    const target = await waitForChartTarget(this.cdpBaseUrl, this.connectTimeoutMs);
    this.socket = await openSocket(target.webSocketDebuggerUrl, this.connectTimeoutMs);
    this.socket.addEventListener("message", (event) => {
      const response = JSON.parse(String(event.data)) as CdpResponse;
      if (response.id == null) {
        return;
      }

      const pending = this.pending.get(response.id);
      if (!pending) {
        return;
      }

      this.pending.delete(response.id);
      if (response.error?.message) {
        pending.reject(new Error(response.error.message));
        return;
      }

      pending.resolve(response);
    });
    this.socket.addEventListener("close", () => {
      for (const pending of this.pending.values()) {
        pending.reject(new Error("TradingView CDP connection closed."));
      }
      this.pending.clear();
      this.socket = null;
    });

    await this.send("Runtime.enable");
    await this.send("Page.enable");
  }

  public async evaluate<T>(
    expression: string,
    input?: {
      timeoutMs?: number;
      label?: string;
    },
  ): Promise<T> {
    await this.connect();
    const response = (await this.send("Runtime.evaluate", {
      expression,
      awaitPromise: true,
      returnByValue: true,
    }, {
      label: input?.label ?? "Runtime.evaluate",
      timeoutMs: input?.timeoutMs,
    })) as CdpResponse;

    const runtimeError =
      response.result?.exceptionDetails?.exception?.description ??
      response.result?.exceptionDetails?.text;
    if (runtimeError) {
      throw new Error(runtimeError);
    }

    return (response.result?.result?.value as T | undefined) as T;
  }

  public async dispatchCtrlEnter(): Promise<void> {
    await this.connect();
    await this.send("Input.dispatchKeyEvent", {
      type: "rawKeyDown",
      windowsVirtualKeyCode: 17,
      code: "ControlLeft",
      key: "Control",
      modifiers: 2,
    });
    await this.send("Input.dispatchKeyEvent", {
      type: "rawKeyDown",
      windowsVirtualKeyCode: 13,
      code: "Enter",
      key: "Enter",
      modifiers: 2,
    });
    await this.send("Input.dispatchKeyEvent", {
      type: "keyUp",
      windowsVirtualKeyCode: 13,
      code: "Enter",
      key: "Enter",
      modifiers: 2,
    });
    await this.send("Input.dispatchKeyEvent", {
      type: "keyUp",
      windowsVirtualKeyCode: 17,
      code: "ControlLeft",
      key: "Control",
    });
  }

  public async reloadPage(input?: {
    ignoreCache?: boolean;
    waitMs?: number;
  }): Promise<void> {
    await this.connect();
    await this.send(
      "Page.reload",
      {
        ignoreCache: input?.ignoreCache ?? true,
      },
      {
        label: "Page.reload",
      },
    );
    await delay(input?.waitMs ?? 12_000);
  }

  public async waitFor<T>(
    action: () => Promise<T>,
    predicate: (value: T) => boolean,
    input?: {
      timeoutMs?: number;
      intervalMs?: number;
      label?: string;
    },
  ): Promise<T> {
    const timeoutMs = input?.timeoutMs ?? 15_000;
    const intervalMs = input?.intervalMs ?? 250;
    const deadline = Date.now() + timeoutMs;
    let lastValue: T | null = null;
    let lastError: Error | null = null;
    while (Date.now() < deadline) {
      try {
        lastValue = await action();
        lastError = null;
        if (predicate(lastValue)) {
          return lastValue;
        }
      } catch (error) {
        lastError =
          error instanceof Error ? error : new Error(String(error));
      }
      await delay(intervalMs);
    }

    throw new Error(
      `${input?.label ?? "TradingView CDP wait"} timed out after ${timeoutMs}ms.${
        lastError ? ` Last error: ${lastError.message}` : ""
      }`,
    );
  }

  public async delay(ms: number): Promise<void> {
    await delay(ms);
  }

  public async close(): Promise<void> {
    if (!this.socket) {
      return;
    }

    const socket = this.socket;
    this.socket = null;
    socket.close();
    await delay(50);
  }

  private async send(
    method: string,
    params?: Record<string, unknown>,
    input?: {
      timeoutMs?: number;
      label?: string;
    },
  ): Promise<unknown> {
    if (!this.socket) {
      throw new Error("TradingView CDP socket is not connected.");
    }

    const id = ++this.messageId;
    const payload = JSON.stringify({
      id,
      method,
      ...(params ? { params } : {}),
    });

    return await new Promise((resolve, reject) => {
      const timeoutMs = input?.timeoutMs ?? this.commandTimeoutMs;
      let settled = false;
      const cleanup = () => {
        clearTimeout(timeout);
        this.pending.delete(id);
      };
      const settleResolve = (value: unknown) => {
        if (settled) {
          return;
        }
        settled = true;
        cleanup();
        resolve(value);
      };
      const settleReject = (error: Error) => {
        if (settled) {
          return;
        }
        settled = true;
        cleanup();
        reject(error);
      };
      const timeout = setTimeout(() => {
        settleReject(
          new Error(
            `TradingView CDP command ${input?.label ?? method} timed out after ${timeoutMs}ms.`,
          ),
        );
      }, timeoutMs);

      this.pending.set(id, { resolve: settleResolve, reject: settleReject });
      try {
        this.socket?.send(payload);
      } catch (error) {
        settleReject(error instanceof Error ? error : new Error(String(error)));
      }
    });
  }
}

async function ensureDesktopDebugEndpoint(input: {
  cdpBaseUrl: string;
  executablePath?: string;
  connectTimeoutMs: number;
}): Promise<void> {
  if (await isCdpReachable(input.cdpBaseUrl)) {
    return;
  }

  const executablePath = await resolveTradingViewExecutablePath(input.executablePath);
  if (!executablePath) {
    throw new Error(
      "TradingView Desktop CDP endpoint is unavailable. Configure TRADINGVIEW_CDP_URL or TRADINGVIEW_DESKTOP_PATH.",
    );
  }

  const port = new URL(input.cdpBaseUrl).port || "9222";
  if (process.platform === "win32" && (await isTradingViewDesktopRunning())) {
    await stopTradingViewDesktop();
    await delay(1_500);
  }

  launchTradingViewDesktop(executablePath, port);

  const deadline = Date.now() + input.connectTimeoutMs;
  while (Date.now() < deadline) {
    if (await isCdpReachable(input.cdpBaseUrl)) {
      return;
    }
    await delay(500);
  }

  throw new Error(
    `TradingView Desktop was relaunched from ${executablePath}, but CDP did not become reachable at ${input.cdpBaseUrl}.`,
  );
}

async function ensureWebDebugEndpoint(input: {
  cdpBaseUrl: string;
  executablePath?: string;
  profileDir?: string;
  chartUrl?: string;
  headless?: boolean;
  connectTimeoutMs: number;
}): Promise<void> {
  if (await isCdpReachable(input.cdpBaseUrl)) {
    return;
  }

  const port = new URL(input.cdpBaseUrl).port || "9223";
  const profileDir =
    input.profileDir ?? path.join(process.cwd(), ".af-tradingview-web-profile");
  await mkdir(profileDir, { recursive: true });

  launchTradingViewWebBrowser({
    executablePath: await resolveWebBrowserExecutablePath(input.executablePath),
    port,
    profileDir,
    chartUrl: input.chartUrl ?? DEFAULT_TRADINGVIEW_WEB_CHART_URL,
    headless: input.headless ?? false,
  });

  const deadline = Date.now() + input.connectTimeoutMs;
  while (Date.now() < deadline) {
    if (await isCdpReachable(input.cdpBaseUrl)) {
      return;
    }
    await delay(500);
  }

  throw new Error(
    `TradingView web browser was launched, but CDP did not become reachable at ${input.cdpBaseUrl}.`,
  );
}

async function resolveWebBrowserExecutablePath(
  configuredPath?: string,
): Promise<string> {
  const candidates = [
    configuredPath,
    chromium.executablePath(),
    process.env.ProgramFiles
      ? path.join(process.env.ProgramFiles, "Google", "Chrome", "Application", "chrome.exe")
      : undefined,
    process.env.ProgramFiles
      ? path.join(process.env.ProgramFiles, "Microsoft", "Edge", "Application", "msedge.exe")
      : undefined,
    process.env["ProgramFiles(x86)"]
      ? path.join(
          process.env["ProgramFiles(x86)"]!,
          "Google",
          "Chrome",
          "Application",
          "chrome.exe",
        )
      : undefined,
    process.env["ProgramFiles(x86)"]
      ? path.join(
          process.env["ProgramFiles(x86)"]!,
          "Microsoft",
          "Edge",
          "Application",
          "msedge.exe",
        )
      : undefined,
    process.env.LOCALAPPDATA
      ? path.join(
          process.env.LOCALAPPDATA,
          "Google",
          "Chrome",
          "Application",
          "chrome.exe",
        )
      : undefined,
    process.env.LOCALAPPDATA
      ? path.join(
          process.env.LOCALAPPDATA,
          "Microsoft",
          "Edge",
          "Application",
          "msedge.exe",
        )
      : undefined,
  ];

  for (const candidate of [...new Set(candidates.filter(Boolean))]) {
    if (await isAccessiblePath(candidate as string)) {
      return candidate as string;
    }
  }

  throw new Error(
    "TradingView web browser executable was not found. Configure TRADINGVIEW_WEB_BROWSER_PATH to Chrome or Edge.",
  );
}

async function ensureChartTargetOpen(input: {
  cdpBaseUrl: string;
  chartUrl?: string;
  connectTimeoutMs: number;
}): Promise<void> {
  if (await findChartTarget(input.cdpBaseUrl)) {
    return;
  }

  const chartUrl = input.chartUrl ?? DEFAULT_TRADINGVIEW_WEB_CHART_URL;
  await openCdpTab(input.cdpBaseUrl, chartUrl);

  const deadline = Date.now() + input.connectTimeoutMs;
  while (Date.now() < deadline) {
    if (await findChartTarget(input.cdpBaseUrl)) {
      return;
    }
    await delay(500);
  }
}

export function buildTradingViewExecutableCandidates(input?: {
  configuredPath?: string;
  appxInstallLocation?: string | null;
  localAppData?: string;
  programFiles?: string;
  programFilesX86?: string;
}): string[] {
  const candidates = [
    input?.configuredPath,
    input?.appxInstallLocation
      ? path.join(input.appxInstallLocation, TRADINGVIEW_EXECUTABLE_NAME)
      : undefined,
    input?.localAppData
      ? path.join(
          input.localAppData,
          "Programs",
          "TradingView",
          TRADINGVIEW_EXECUTABLE_NAME,
        )
      : undefined,
    input?.programFiles
      ? path.join(input.programFiles, "TradingView", TRADINGVIEW_EXECUTABLE_NAME)
      : undefined,
    input?.programFilesX86
      ? path.join(input.programFilesX86, "TradingView", TRADINGVIEW_EXECUTABLE_NAME)
      : undefined,
  ];

  return [...new Set(candidates.filter((candidate): candidate is string => Boolean(candidate)))];
}

async function resolveTradingViewExecutablePath(
  configuredPath?: string,
): Promise<string | null> {
  const appxInstallLocation = await resolveWindowsTradingViewAppxInstallLocation();
  const candidates = buildTradingViewExecutableCandidates({
    configuredPath,
    appxInstallLocation,
    localAppData: process.env.LOCALAPPDATA,
    programFiles: process.env.ProgramFiles,
    programFilesX86: process.env["ProgramFiles(x86)"],
  });

  for (const candidate of candidates) {
    if (await isAccessiblePath(candidate)) {
      return candidate;
    }
  }

  return null;
}

async function resolveWindowsTradingViewAppxInstallLocation(): Promise<string | null> {
  if (process.platform !== "win32") {
    return null;
  }

  try {
    const stdout = await execFileStdout("powershell.exe", [
      "-NoProfile",
      "-Command",
      "Get-AppxPackage | Where-Object { $_.Name -eq 'TradingView.Desktop' } | Select-Object -First 1 -ExpandProperty InstallLocation",
    ]);
    const installLocation = stdout
      .split(/\r?\n/)
      .map((line) => line.trim())
      .find(Boolean);
    return installLocation ?? null;
  } catch {
    return null;
  }
}

async function isAccessiblePath(filePath: string): Promise<boolean> {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function isTradingViewDesktopRunning(): Promise<boolean> {
  if (process.platform !== "win32") {
    return false;
  }

  try {
    const stdout = await execFileStdout("tasklist", [
      "/FI",
      `IMAGENAME eq ${TRADINGVIEW_PROCESS_IMAGE}`,
      "/FO",
      "CSV",
      "/NH",
    ]);
    return stdout.toLowerCase().includes(`"${TRADINGVIEW_PROCESS_IMAGE.toLowerCase()}"`);
  } catch {
    return false;
  }
}

async function stopTradingViewDesktop(): Promise<void> {
  if (process.platform !== "win32") {
    return;
  }

  try {
    await execFileStdout("taskkill", ["/IM", TRADINGVIEW_PROCESS_IMAGE, "/F", "/T"]);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (!/not found|no running instance|cannot find/i.test(message)) {
      throw error;
    }
  }
}

function launchTradingViewDesktop(executablePath: string, port: string): void {
  const child = spawn(executablePath, [`--remote-debugging-port=${port}`], {
    detached: true,
    stdio: "ignore",
    windowsHide: true,
  });
  child.unref();
}

function launchTradingViewWebBrowser(input: {
  executablePath: string;
  port: string;
  profileDir: string;
  chartUrl: string;
  headless: boolean;
}): void {
  const args = [
    `--remote-debugging-port=${input.port}`,
    `--user-data-dir=${input.profileDir}`,
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding",
    "--new-window",
    input.chartUrl,
  ];
  if (input.headless) {
    args.unshift("--headless=new");
  }

  const child = spawn(input.executablePath, args, {
    detached: true,
    stdio: "ignore",
    windowsHide: input.headless,
  });
  child.on("error", () => {
    // The caller detects launch failure by waiting for the CDP endpoint.
  });
  child.unref();
}

async function execFileStdout(command: string, args: string[]): Promise<string> {
  return await new Promise((resolve, reject) => {
    execFile(command, args, { windowsHide: true }, (error, stdout) => {
      if (error) {
        reject(error);
        return;
      }

      resolve(stdout);
    });
  });
}

async function isCdpReachable(cdpBaseUrl: string): Promise<boolean> {
  try {
    const response = await fetch(`${cdpBaseUrl}/json/version`);
    return response.ok;
  } catch {
    return false;
  }
}

async function openCdpTab(cdpBaseUrl: string, url: string): Promise<void> {
  const endpoint = `${cdpBaseUrl}/json/new?${encodeURIComponent(url)}`;
  try {
    const putResponse = await fetch(endpoint, { method: "PUT" });
    if (putResponse.ok) {
      return;
    }
  } catch {
    // Older Chromium builds accepted GET here; try it before giving up.
  }

  try {
    await fetch(endpoint);
  } catch {
    // The caller still waits for a chart target because the browser may have
    // been launched with the chart URL already.
  }
}

async function waitForChartTarget(
  cdpBaseUrl: string,
  timeoutMs: number,
): Promise<CdpTargetInfo> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const target = await findChartTarget(cdpBaseUrl);
    if (target) {
      return target;
    }
    await delay(500);
  }

  throw new Error(
    `TradingView chart target was not found on ${cdpBaseUrl}. Open a chart tab in TradingView Desktop first.`,
  );
}

async function findChartTarget(cdpBaseUrl: string): Promise<CdpTargetInfo | null> {
  const response = await fetch(`${cdpBaseUrl}/json/list`);
  if (!response.ok) {
    return null;
  }

  const targets = (await response.json()) as CdpTargetInfo[];
  return (
    targets.find(
      (target) =>
        CHART_TARGET_PATTERN.test(target.url) && Boolean(target.webSocketDebuggerUrl),
    ) ?? null
  );
}

async function openSocket(url: string, timeoutMs: number): Promise<WebSocketLike> {
  const WebSocketCtor = (globalThis as {
    WebSocket?: new (url: string) => WebSocketLike;
  }).WebSocket;
  if (!WebSocketCtor) {
    throw new Error("WebSocket is not available in this Node runtime.");
  }

  return await new Promise((resolve, reject) => {
    const socket = new WebSocketCtor(url);
    const timeout = setTimeout(() => {
      socket.close();
      reject(new Error(`TradingView websocket connection timed out after ${timeoutMs}ms.`));
    }, timeoutMs);

    socket.addEventListener(
      "open",
      () => {
        clearTimeout(timeout);
        resolve(socket);
      },
      { once: true },
    );
    socket.addEventListener(
      "error",
      () => {
        clearTimeout(timeout);
        reject(new Error(`TradingView websocket connection failed for ${url}.`));
      },
      { once: true },
    );
  });
}

function normalizeCdpBaseUrl(url?: string, surface: "desktop" | "web" = "desktop"): string {
  if (!url) {
    return surface === "web" ? DEFAULT_WEB_CDP_URL : DEFAULT_CDP_URL;
  }

  return url.replace(/\/$/, "");
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}
