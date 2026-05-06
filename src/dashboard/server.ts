import http, { type IncomingMessage, type ServerResponse } from "node:http";

import { buildDashboardStatus } from "./data.js";
import { renderDashboardHtml } from "./static.js";

export interface DashboardServerOptions {
  workspaceRoot: string;
  stateRoot: string;
  autoProcessCalibration?: boolean;
  promotionVerificationExecutor?: string;
  researchModeConfig?: Record<string, unknown>;
  host?: string;
  port?: number;
  open?: boolean;
}

export interface DashboardServerHandle {
  server: http.Server;
  url: string;
  port: number;
  host: string;
}

interface CachedPayload {
  generatedAtMs: number;
  body: string;
}

export async function startDashboardServer(
  options: DashboardServerOptions,
): Promise<DashboardServerHandle> {
  const host = options.host ?? "127.0.0.1";
  const requestedPort = options.port ?? 4177;
  let cache: CachedPayload | null = null;
  const html = renderDashboardHtml();

  const server = http.createServer(async (request, response) => {
    try {
      if (!isLocalRequest(request)) {
        sendText(response, 403, "Forbidden: local dashboard only.");
        return;
      }

      const url = new URL(request.url ?? "/", `http://${host}`);
      if (request.method === "GET" && url.pathname === "/") {
        send(response, 200, "text/html; charset=utf-8", html);
        return;
      }

      if (request.method === "GET" && url.pathname === "/favicon.ico") {
        send(response, 204, "image/x-icon", "");
        return;
      }

      if (request.method === "GET" && url.pathname === "/api/status") {
        const now = Date.now();
        if (!cache || now - cache.generatedAtMs > 3_000) {
          const payload = await buildDashboardStatus({
            workspaceRoot: options.workspaceRoot,
            stateRoot: options.stateRoot,
            autoProcessCalibration: options.autoProcessCalibration,
            promotionVerificationExecutor: options.promotionVerificationExecutor,
            researchModeConfig: options.researchModeConfig,
          });
          cache = {
            generatedAtMs: now,
            body: JSON.stringify(payload),
          };
        }
        send(response, 200, "application/json; charset=utf-8", cache.body);
        return;
      }

      sendText(response, 404, "Not found.");
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      sendText(response, 500, message);
    }
  });

  const bound = await listenWithPortFallback(server, host, requestedPort);
  const url = `http://${host}:${bound.port}/`;
  if (options.open) {
    await openBrowser(url);
  }

  return {
    server,
    url,
    port: bound.port,
    host,
  };
}

function isLocalRequest(request: IncomingMessage): boolean {
  const remoteAddress = request.socket.remoteAddress;
  return (
    remoteAddress == null ||
    remoteAddress === "127.0.0.1" ||
    remoteAddress === "::1" ||
    remoteAddress === "::ffff:127.0.0.1"
  );
}

async function listenWithPortFallback(
  server: http.Server,
  host: string,
  requestedPort: number,
): Promise<{ port: number }> {
  for (let offset = 0; offset < 30; offset += 1) {
    const port = requestedPort + offset;
    try {
      await listen(server, host, port);
      return { port };
    } catch (error) {
      if (!isAddressInUse(error)) {
        throw error;
      }
    }
  }

  throw new Error(
    `Unable to bind dashboard server near port ${requestedPort}; tried 30 ports.`,
  );
}

function listen(server: http.Server, host: string, port: number): Promise<void> {
  return new Promise((resolve, reject) => {
    const onError = (error: Error) => {
      server.off("listening", onListening);
      reject(error);
    };
    const onListening = () => {
      server.off("error", onError);
      resolve();
    };
    server.once("error", onError);
    server.once("listening", onListening);
    server.listen(port, host);
  });
}

function isAddressInUse(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error != null &&
    "code" in error &&
    (error as { code?: string }).code === "EADDRINUSE"
  );
}

function send(
  response: ServerResponse,
  statusCode: number,
  contentType: string,
  body: string,
): void {
  response.writeHead(statusCode, {
    "content-type": contentType,
    "cache-control": "no-store",
    "x-content-type-options": "nosniff",
  });
  response.end(body);
}

function sendText(
  response: ServerResponse,
  statusCode: number,
  body: string,
): void {
  send(response, statusCode, "text/plain; charset=utf-8", body);
}

async function openBrowser(url: string): Promise<void> {
  const { spawn } = await import("node:child_process");
  const command =
    process.platform === "win32"
      ? "cmd"
      : process.platform === "darwin"
        ? "open"
        : "xdg-open";
  const args =
    process.platform === "win32"
      ? ["/c", "start", "", url]
      : [url];
  const child = spawn(command, args, {
    detached: true,
    stdio: "ignore",
  });
  child.unref();
}
