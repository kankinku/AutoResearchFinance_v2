import { access } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";

import { type RuntimeEnvironment } from "./runtime-config.js";

interface OpenAiEndpointInspection {
  reachable: boolean;
  status: number | null;
}

export interface OpenAiAuthStatus {
  authMode: "api_key" | "oauth_proxy";
  authConfigured: boolean;
  reachable: boolean;
  status: number | null;
  proxyStarted: boolean;
  proxyRestarted: boolean;
  authFilePath: string | null;
}

const DEFAULT_OAUTH_PROXY_COMMAND = "npx openai-oauth";
const ENDPOINT_INSPECTION_TIMEOUT_MS = 5_000;
const DEFAULT_PROXY_STARTUP_TIMEOUT_MS = 20_000;

export interface EnsureOpenAiAuthOptions {
  forceRestartProxy?: boolean;
}

export async function ensureOpenAiAuthReady(
  env: RuntimeEnvironment,
  options: EnsureOpenAiAuthOptions = {},
): Promise<OpenAiAuthStatus> {
  if (env.openAiAuthMode === "api_key") {
    const inspection = await inspectOpenAiEndpoint(env.openAiBaseUrl, env.openAiApiKey);
    return {
      authMode: env.openAiAuthMode,
      authConfigured: Boolean(env.openAiApiKey),
      reachable: inspection.reachable,
      status: inspection.status,
      proxyStarted: false,
      proxyRestarted: false,
      authFilePath: null,
    };
  }

  const authFilePath = await findOpenAiOauthAuthFile(env.openAiOauthAuthFilePath);
  if (!authFilePath) {
    throw new Error(
      "OpenAI OAuth auth.json was not found. Run `npx @openai/codex login` first.",
    );
  }

  let proxyStarted = false;
  let proxyRestarted = false;
  if (options.forceRestartProxy) {
    proxyRestarted = await restartOpenAiOauthProxy(env, authFilePath);
    proxyStarted = proxyRestarted;
    if (proxyRestarted) {
      await waitForOpenAiOauthProxy(env.openAiBaseUrl, DEFAULT_PROXY_STARTUP_TIMEOUT_MS);
    }
  }

  if (!proxyRestarted) {
    const proxyHealth = await inspectProxyHealth(env.openAiBaseUrl);
    if (!proxyHealth.reachable) {
      await startOpenAiOauthProxy(env, authFilePath);
      proxyStarted = true;
      await waitForOpenAiOauthProxy(env.openAiBaseUrl, DEFAULT_PROXY_STARTUP_TIMEOUT_MS);
    }
  }

  const inspection = await inspectOpenAiEndpoint(env.openAiBaseUrl, env.openAiApiKey);
  return {
    authMode: env.openAiAuthMode,
    authConfigured: true,
    reachable: inspection.reachable,
    status: inspection.status,
    proxyStarted,
    proxyRestarted,
    authFilePath,
  };
}

export async function findOpenAiOauthAuthFile(
  preferredPath?: string,
): Promise<string | null> {
  for (const candidate of resolveOpenAiOauthAuthFileCandidates(preferredPath)) {
    try {
      await access(candidate);
      return candidate;
    } catch {}
  }

  return null;
}

export function resolveOpenAiOauthAuthFileCandidates(preferredPath?: string): string[] {
  const candidates = [
    preferredPath,
    process.env.CHATGPT_LOCAL_HOME
      ? path.join(process.env.CHATGPT_LOCAL_HOME, "auth.json")
      : undefined,
    process.env.CODEX_HOME ? path.join(process.env.CODEX_HOME, "auth.json") : undefined,
    path.join(os.homedir(), ".chatgpt-local", "auth.json"),
    path.join(os.homedir(), ".codex", "auth.json"),
  ].filter((value): value is string => Boolean(value));

  return [...new Set(candidates)];
}

export async function inspectOpenAiEndpoint(
  baseUrl: string,
  apiKey?: string,
): Promise<OpenAiEndpointInspection> {
  try {
    const response = await fetchWithTimeout(
      `${baseUrl.replace(/\/$/, "")}/models`,
      {
        headers: {
          ...(apiKey ? { authorization: `Bearer ${apiKey}` } : {}),
        },
      },
      ENDPOINT_INSPECTION_TIMEOUT_MS,
    );
    return {
      reachable: response.ok || response.status === 401 || response.status === 403,
      status: response.status,
    };
  } catch {
    return {
      reachable: false,
      status: null,
    };
  }
}

async function inspectProxyHealth(baseUrl: string): Promise<OpenAiEndpointInspection> {
  const rootUrl = baseUrl.replace(/\/v1\/?$/, "");
  try {
    const response = await fetchWithTimeout(
      `${rootUrl}/health`,
      undefined,
      ENDPOINT_INSPECTION_TIMEOUT_MS,
    );
    return {
      reachable: response.ok,
      status: response.status,
    };
  } catch {
    return {
      reachable: false,
      status: null,
    };
  }
}

async function restartOpenAiOauthProxy(
  env: RuntimeEnvironment,
  authFilePath: string,
): Promise<boolean> {
  const { host, port } = resolveProxyBinding(env.openAiBaseUrl);
  if (!isLocalProxyHost(host)) {
    return false;
  }

  const processIds = await findListeningProcessIdsForPort(port);
  for (const processId of processIds) {
    await terminateProcess(processId).catch(() => undefined);
  }
  if (processIds.length > 0) {
    await waitForPortToRelease(port, 5_000);
  }

  await startOpenAiOauthProxy(env, authFilePath);
  return true;
}

async function startOpenAiOauthProxy(
  env: RuntimeEnvironment,
  authFilePath: string,
): Promise<void> {
  const { host, port } = resolveProxyBinding(env.openAiBaseUrl);
  const command = env.openAiOauthProxyCommand || DEFAULT_OAUTH_PROXY_COMMAND;
  const child = spawn(
    command,
    ["--host", host, "--port", String(port), "--oauth-file", authFilePath],
    {
      detached: true,
      stdio: "ignore",
      shell: true,
      cwd: env.workspaceRoot,
    },
  );
  child.unref();
}

async function findListeningProcessIdsForPort(port: number): Promise<number[]> {
  if (process.platform === "win32") {
    const output = await captureCommandOutput("netstat", ["-ano", "-p", "tcp"]);
    if (!output) {
      return [];
    }

    const processIds = new Set<number>();
    for (const line of output.split(/\r?\n/)) {
      const columns = line.trim().split(/\s+/);
      if (columns.length < 5) {
        continue;
      }
      if (columns[0]?.toUpperCase() !== "TCP" || columns[3]?.toUpperCase() !== "LISTENING") {
        continue;
      }
      if (extractPort(columns[1]) !== port) {
        continue;
      }
      const processId = Number.parseInt(columns[4] ?? "", 10);
      if (Number.isFinite(processId) && processId > 0 && processId !== process.pid) {
        processIds.add(processId);
      }
    }
    return [...processIds];
  }

  const output = await captureCommandOutput("lsof", ["-ti", `tcp:${port}`]);
  if (!output) {
    return [];
  }

  return output
    .split(/\r?\n/)
    .map((line) => Number.parseInt(line.trim(), 10))
    .filter((value) => Number.isFinite(value) && value > 0 && value !== process.pid);
}

async function terminateProcess(processId: number): Promise<void> {
  if (process.platform === "win32") {
    await runCommand("taskkill", ["/PID", String(processId), "/F", "/T"]);
    return;
  }

  await runCommand("kill", ["-9", String(processId)]);
}

async function waitForPortToRelease(port: number, timeoutMs: number): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const processIds = await findListeningProcessIdsForPort(port);
    if (processIds.length === 0) {
      return;
    }
    await delay(200);
  }

  throw new Error(`Timed out waiting for TCP port ${port} to become available.`);
}

function extractPort(value: string | undefined): number | null {
  if (!value) {
    return null;
  }

  const separatorIndex = value.lastIndexOf(":");
  if (separatorIndex < 0 || separatorIndex === value.length - 1) {
    return null;
  }

  const parsed = Number.parseInt(value.slice(separatorIndex + 1), 10);
  return Number.isFinite(parsed) ? parsed : null;
}

function isLocalProxyHost(host: string): boolean {
  return host === "127.0.0.1" || host === "localhost" || host === "::1";
}

async function fetchWithTimeout(
  input: string,
  init: RequestInit | undefined,
  timeoutMs: number,
): Promise<Response> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(input, {
      ...init,
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeout);
  }
}

async function captureCommandOutput(
  command: string,
  args: string[],
): Promise<string | null> {
  try {
    const result = await runCommand(command, args);
    return result.stdout.trim();
  } catch {
    return null;
  }
}

async function runCommand(
  command: string,
  args: string[],
): Promise<{ stdout: string; stderr: string }> {
  return await new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk: Buffer | string) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk: Buffer | string) => {
      stderr += chunk.toString();
    });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code === 0) {
        resolve({ stdout, stderr });
        return;
      }
      reject(
        new Error(
          `${command} ${args.join(" ")} exited with code ${code}: ${stderr || stdout}`,
        ),
      );
    });
  });
}

async function waitForOpenAiOauthProxy(baseUrl: string, timeoutMs: number): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const health = await inspectProxyHealth(baseUrl);
    if (health.reachable) {
      return;
    }
    await delay(500);
  }

  throw new Error(
    `openai-oauth proxy did not become ready at ${baseUrl.replace(/\/$/, "")} within ${timeoutMs}ms.`,
  );
}

function resolveProxyBinding(baseUrl: string): { host: string; port: number } {
  const url = new URL(baseUrl);
  const defaultPort = url.protocol === "https:" ? 443 : 80;
  return {
    host: url.hostname,
    port: Number.parseInt(url.port || String(defaultPort), 10),
  };
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}
