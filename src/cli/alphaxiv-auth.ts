import { randomBytes } from "node:crypto";
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { access, mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";

import {
  exchangeAuthorization,
  refreshAuthorization,
  registerClient,
  startAuthorization,
  type AuthorizationServerMetadata,
  type OAuthClientInformationFull,
  type OAuthTokens,
} from "@modelcontextprotocol/client";

import { createAlphaXivMcpClient } from "../research/alphaxiv-mcp-client.js";
import { type RuntimeEnvironment } from "./runtime-config.js";

const DEFAULT_LOGIN_TIMEOUT_MS = 5 * 60 * 1000;
const DEFAULT_SCOPE = "profile email offline_access";
const DEFAULT_OAUTH_METADATA_URL =
  "https://clerk.alphaxiv.org/.well-known/oauth-authorization-server";
const DEFAULT_ALPHAXIV_RESOURCE_URL = "https://api.alphaxiv.org/mcp/v1";

export interface AlphaXivCookieLike {
  name: string;
  value: string;
  domain: string;
  path: string;
  expires: number;
  httpOnly?: boolean;
  secure?: boolean;
  sameSite?: string;
}

interface SavedAlphaXivAuth {
  savedAt: string;
  authorizationServerUrl: string;
  metadataUrl: string;
  resourceUrl?: string;
  redirectUri?: string;
  clientInformation?: OAuthClientInformationFull;
  client?: {
    clientId: string;
    redirectUri: string;
  };
  tokens: {
    accessToken: string;
    refreshToken?: string;
    tokenType: string;
    scope?: string;
    expiresAt?: number;
  };
}

export interface AlphaXivAuthStatus {
  authConfigured: boolean;
  reachable: boolean;
  status: number | null;
  authMethod: "bearer" | "oauth_token" | "session_cookie" | "none";
  authFilePath: string | null;
  sessionFilePath: string | null;
  error: string | null;
}

export interface AlphaXivLoginResult {
  authFilePath: string;
  toolNames: string[];
}

export async function ensureAlphaXivAuthReady(
  env: RuntimeEnvironment,
): Promise<AlphaXivAuthStatus> {
  if (env.alphaXivMcpBearerToken) {
    const inspection = await inspectAlphaXivEndpoint(env.alphaXivMcpUrl, {
      bearerToken: env.alphaXivMcpBearerToken,
    });
    return {
      authConfigured: true,
      reachable: inspection.reachable,
      status: inspection.status,
      authMethod: "bearer",
      authFilePath: null,
      sessionFilePath: null,
      error: null,
    };
  }

  const authFilePath = await findAlphaXivAuthFile(env.alphaXivAuthFilePath);
  if (authFilePath) {
    try {
      const accessToken = await loadAlphaXivAccessToken(authFilePath);
      const inspection = await inspectAlphaXivEndpoint(env.alphaXivMcpUrl, {
        bearerToken: accessToken,
      });
      return {
        authConfigured: inspection.reachable || inspection.status === 401 || inspection.status === 403,
        reachable: inspection.reachable,
        status: inspection.status,
        authMethod: "oauth_token",
        authFilePath,
        sessionFilePath: null,
        error: null,
      };
    } catch (error) {
      return {
        authConfigured: false,
        reachable: false,
        status: null,
        authMethod: "none",
        authFilePath,
        sessionFilePath: null,
        error: error instanceof Error ? error.message : String(error),
      };
    }
  }

  const sessionFilePath = await findAlphaXivSessionFile(env.alphaXivSessionFilePath);
  if (!sessionFilePath) {
    return {
      authConfigured: false,
      reachable: false,
      status: null,
      authMethod: "none",
      authFilePath: null,
      sessionFilePath: null,
      error: null,
    };
  }

  const cookieHeader = await loadAlphaXivSessionCookieHeader(sessionFilePath);
  if (!cookieHeader) {
    return {
      authConfigured: false,
      reachable: false,
      status: null,
      authMethod: "none",
      authFilePath: null,
      sessionFilePath,
      error: "alphaXiv session file exists but does not contain usable cookies.",
    };
  }

  const inspection = await inspectAlphaXivEndpoint(env.alphaXivMcpUrl, {
    cookieHeader,
  });
  return {
    authConfigured: inspection.reachable,
    reachable: inspection.reachable,
    status: inspection.status,
    authMethod: "session_cookie",
    authFilePath: null,
    sessionFilePath,
    error: inspection.reachable ? null : "alphaXiv session cookies do not satisfy MCP authorization.",
  };
}

export async function loginAlphaXivWithBrowser(
  env: RuntimeEnvironment,
  options?: {
    authFilePath?: string;
    timeoutMs?: number;
    onAuthorizationUrl?: (url: string) => void;
  },
): Promise<AlphaXivLoginResult> {
  const timeoutMs = options?.timeoutMs ?? DEFAULT_LOGIN_TIMEOUT_MS;
  const authFilePath =
    options?.authFilePath ?? resolveAlphaXivAuthFileCandidates(env.alphaXivAuthFilePath)[0];
  const callback = await createLocalCallbackServer(timeoutMs);

  try {
    const metadata = await fetchAlphaXivOAuthMetadata();
    const registration = await registerAlphaXivClient(metadata, callback.redirectUri);
    const resourceUrl = new URL(env.alphaXivMcpUrl);
    const state = createStateToken();
    const requestedScope = resolveRequestedScope(registration);
    const { authorizationUrl, codeVerifier } = await startAuthorization(
      metadata.issuer,
      {
        metadata,
        clientInformation: registration,
        redirectUrl: callback.redirectUri,
        scope: requestedScope,
        resource: resourceUrl,
        state,
      },
    );

    const authorizationUrlText = String(authorizationUrl);
    options?.onAuthorizationUrl?.(authorizationUrlText);
    openExternalBrowser(authorizationUrlText);
    const authResult = await callback.waitForResult();
    if (authResult.error) {
      const detail = authResult.errorDescription
        ? `${authResult.error}: ${authResult.errorDescription}`
        : authResult.error;
      throw new Error(`alphaXiv authorization failed: ${detail}`);
    }
    if (!authResult.code) {
      throw new Error("alphaXiv authorization did not return an authorization code.");
    }
    if (authResult.state !== state) {
      throw new Error("alphaXiv authorization returned an unexpected state value.");
    }

    const tokenResponse = await exchangeAuthorization(metadata.issuer, {
      metadata,
      clientInformation: registration,
      authorizationCode: authResult.code,
      codeVerifier,
      redirectUri: callback.redirectUri,
      resource: resourceUrl,
    });

    const savedAuth: SavedAlphaXivAuth = {
      savedAt: new Date().toISOString(),
      authorizationServerUrl: metadata.issuer,
      metadataUrl: DEFAULT_OAUTH_METADATA_URL,
      resourceUrl: resourceUrl.href,
      redirectUri: callback.redirectUri,
      clientInformation: registration,
      tokens: mapTokenResponse(tokenResponse),
    };
    await saveAlphaXivAuth(authFilePath, savedAuth);

    const client = await createAlphaXivMcpClient({
      endpoint: env.alphaXivMcpUrl,
      bearerToken: savedAuth.tokens.accessToken,
    });
    try {
      const toolNames = await client.listToolNames();
      return {
        authFilePath,
        toolNames,
      };
    } finally {
      await client.close();
    }
  } finally {
    await callback.close();
  }
}

export function resolveAlphaXivAuthFileCandidates(preferredPath?: string): string[] {
  const codeXHome = process.env.CODEX_HOME
    ? path.join(process.env.CODEX_HOME, "alphaxiv-auth.json")
    : undefined;
  const candidates = [
    preferredPath,
    codeXHome,
    path.join(os.homedir(), ".codex", "alphaxiv-auth.json"),
  ].filter((value): value is string => Boolean(value));

  return [...new Set(candidates)];
}

export async function findAlphaXivAuthFile(
  preferredPath?: string,
): Promise<string | null> {
  for (const candidate of resolveAlphaXivAuthFileCandidates(preferredPath)) {
    try {
      await access(candidate);
      return candidate;
    } catch {}
  }

  return null;
}

export async function loadAlphaXivAccessToken(
  preferredPath?: string,
): Promise<string> {
  const authFilePath = preferredPath ?? (await findAlphaXivAuthFile());
  if (!authFilePath) {
    throw new Error("alphaXiv OAuth auth file was not found. Run `af login-alphaxiv` first.");
  }

  const saved = await readAlphaXivAuth(authFilePath);
  const usable = await refreshAlphaXivTokensIfNeeded(authFilePath, saved);
  return usable.tokens.accessToken;
}

export function resolveAlphaXivSessionFileCandidates(preferredPath?: string): string[] {
  const codeXHome = process.env.CODEX_HOME
    ? path.join(process.env.CODEX_HOME, "alphaxiv-session.json")
    : undefined;
  const candidates = [
    preferredPath,
    codeXHome,
    path.join(os.homedir(), ".codex", "alphaxiv-session.json"),
  ].filter((value): value is string => Boolean(value));

  return [...new Set(candidates)];
}

export async function findAlphaXivSessionFile(
  preferredPath?: string,
): Promise<string | null> {
  for (const candidate of resolveAlphaXivSessionFileCandidates(preferredPath)) {
    try {
      await access(candidate);
      return candidate;
    } catch {}
  }

  return null;
}

export async function loadAlphaXivSessionCookieHeader(
  sessionFilePath?: string,
): Promise<string | null> {
  const resolvedPath = sessionFilePath
    ? sessionFilePath
    : await findAlphaXivSessionFile();
  if (!resolvedPath) {
    return null;
  }

  const payload = JSON.parse(
    await readFile(resolvedPath, "utf8"),
  ) as { cookies: AlphaXivCookieLike[] };
  return buildAlphaXivCookieHeader(payload.cookies, DEFAULT_ALPHAXIV_RESOURCE_URL);
}

export async function inspectAlphaXivEndpoint(
  endpoint: string,
  auth?: {
    bearerToken?: string;
    cookieHeader?: string;
  },
): Promise<{ reachable: boolean; status: number | null }> {
  try {
    const response = await fetch(endpoint, {
      headers: {
        Accept: "text/event-stream",
        ...(auth?.bearerToken
          ? { authorization: `Bearer ${auth.bearerToken}` }
          : {}),
        ...(auth?.cookieHeader ? { cookie: auth.cookieHeader } : {}),
      },
    });
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

export function buildAlphaXivCookieHeader(
  cookies: AlphaXivCookieLike[],
  targetUrl: string,
): string | null {
  const target = new URL(targetUrl);
  const now = Date.now() / 1000;
  const usableCookies = cookies.filter((cookie) => {
    const domain = cookie.domain.startsWith(".")
      ? cookie.domain.slice(1)
      : cookie.domain;
    const domainMatches =
      target.hostname === domain || target.hostname.endsWith(`.${domain}`);
    const pathMatches = target.pathname.startsWith(cookie.path);
    const notExpired = cookie.expires === -1 || cookie.expires > now;
    return domainMatches && pathMatches && notExpired;
  });

  if (usableCookies.length === 0) {
    return null;
  }

  return usableCookies.map((cookie) => `${cookie.name}=${cookie.value}`).join("; ");
}

async function fetchAlphaXivOAuthMetadata(): Promise<AuthorizationServerMetadata> {
  const response = await fetch(DEFAULT_OAUTH_METADATA_URL);
  if (!response.ok) {
    throw new Error(`alphaXiv OAuth metadata request failed with ${response.status}.`);
  }

  return (await response.json()) as AuthorizationServerMetadata;
}

async function registerAlphaXivClient(
  metadata: AuthorizationServerMetadata,
  redirectUri: string,
): Promise<OAuthClientInformationFull> {
  return registerClient(metadata.issuer, {
    metadata,
    clientMetadata: {
      client_name: "AF alphaXiv MCP",
      redirect_uris: [redirectUri],
      grant_types: ["authorization_code"],
      response_types: ["code"],
      token_endpoint_auth_method: "none",
    },
  });
}

async function refreshAlphaXivTokensIfNeeded(
  authFilePath: string,
  saved: SavedAlphaXivAuth,
): Promise<SavedAlphaXivAuth> {
  if (
    saved.tokens.expiresAt &&
    saved.tokens.expiresAt > Date.now() + 60_000
  ) {
    return saved;
  }
  if (!saved.tokens.refreshToken) {
    return saved;
  }

  const metadata = await fetchAlphaXivOAuthMetadata();
  const refreshedTokens = await refreshAuthorization(saved.authorizationServerUrl, {
    metadata,
    clientInformation: resolveSavedClientInformation(saved),
    refreshToken: saved.tokens.refreshToken,
    resource: resolveSavedResourceUrl(saved),
  });

  const refreshed: SavedAlphaXivAuth = {
    ...saved,
    savedAt: new Date().toISOString(),
    tokens: {
      accessToken: refreshedTokens.access_token,
      refreshToken: refreshedTokens.refresh_token ?? saved.tokens.refreshToken,
      tokenType: refreshedTokens.token_type ?? saved.tokens.tokenType,
      scope: refreshedTokens.scope ?? saved.tokens.scope,
      expiresAt: refreshedTokens.expires_in
        ? Date.now() + refreshedTokens.expires_in * 1000
        : saved.tokens.expiresAt,
    },
  };
  await saveAlphaXivAuth(authFilePath, refreshed);
  return refreshed;
}

function resolveSavedClientInformation(
  saved: SavedAlphaXivAuth,
): OAuthClientInformationFull {
  if (saved.clientInformation) {
    return saved.clientInformation;
  }

  if (!saved.client) {
    throw new Error("alphaXiv auth file is missing registered client information.");
  }

  return {
    client_id: saved.client.clientId,
    redirect_uris: [saved.client.redirectUri],
    grant_types: ["authorization_code"],
    response_types: ["code"],
    token_endpoint_auth_method: "none",
  };
}

function resolveSavedResourceUrl(saved: SavedAlphaXivAuth): URL {
  return new URL(saved.resourceUrl ?? DEFAULT_ALPHAXIV_RESOURCE_URL);
}

function mapTokenResponse(tokens: OAuthTokens): SavedAlphaXivAuth["tokens"] {
  return {
    accessToken: tokens.access_token,
    refreshToken: tokens.refresh_token,
    tokenType: tokens.token_type ?? "Bearer",
    scope: tokens.scope,
    expiresAt: tokens.expires_in
      ? Date.now() + tokens.expires_in * 1000
      : undefined,
  };
}

function resolveRequestedScope(registration: OAuthClientInformationFull): string {
  const registrationScope =
    typeof registration.scope === "string" && registration.scope.trim().length > 0
      ? registration.scope.trim()
      : null;

  return registrationScope ?? DEFAULT_SCOPE;
}

async function readAlphaXivAuth(authFilePath: string): Promise<SavedAlphaXivAuth> {
  return JSON.parse(await readFile(authFilePath, "utf8")) as SavedAlphaXivAuth;
}

async function saveAlphaXivAuth(
  authFilePath: string,
  auth: SavedAlphaXivAuth,
): Promise<void> {
  await mkdir(path.dirname(authFilePath), { recursive: true });
  await writeFile(authFilePath, JSON.stringify(auth, null, 2), "utf8");
}

async function createLocalCallbackServer(timeoutMs: number): Promise<{
  redirectUri: string;
  waitForResult(): Promise<{
    code: string;
    state: string | null;
    error: string | null;
    errorDescription: string | null;
  }>;
  close(): Promise<void>;
}> {
  let resolveResult:
    | ((value: {
      code: string;
      state: string | null;
      error: string | null;
      errorDescription: string | null;
    }) => void)
    | null = null;
  let rejectResult: ((reason?: unknown) => void) | null = null;
  const resultPromise = new Promise<{
    code: string;
    state: string | null;
    error: string | null;
    errorDescription: string | null;
  }>((resolve, reject) => {
    resolveResult = resolve;
    rejectResult = reject;
  });

  const server = createServer((request, response) => {
    handleCallbackRequest(request.url ?? "/", response, resolveResult);
  });
  await new Promise<void>((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      server.off("error", reject);
      resolve();
    });
  });

  const address = server.address();
  if (!address || typeof address === "string") {
    throw new Error("Failed to start alphaXiv OAuth callback server.");
  }
  const redirectUri = `http://127.0.0.1:${address.port}/callback`;
  const timer = setTimeout(() => {
    rejectResult?.(
      new Error(`Timed out after ${timeoutMs}ms waiting for alphaXiv authorization callback.`),
    );
  }, timeoutMs);

  return {
    redirectUri,
    waitForResult: async () => {
      try {
        return await resultPromise;
      } finally {
        clearTimeout(timer);
      }
    },
    close: async () => {
      clearTimeout(timer);
      await new Promise<void>((resolve) => {
        server.close(() => resolve());
      });
    },
  };
}

function handleCallbackRequest(
  requestPath: string,
  response: ServerResponse<IncomingMessage>,
  resolveResult: ((value: {
    code: string;
    state: string | null;
    error: string | null;
    errorDescription: string | null;
  }) => void) | null,
): void {
  const url = new URL(requestPath, "http://127.0.0.1");
  if (url.pathname !== "/callback") {
    response.statusCode = 404;
    response.end("Not found");
    return;
  }

  const error = url.searchParams.get("error");
  const errorDescription = url.searchParams.get("error_description");
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  response.statusCode = 200;
  response.setHeader("content-type", "text/html; charset=utf-8");
  response.end(
    "<html><body><h1>alphaXiv login complete</h1><p>You can close this window and return to AF.</p></body></html>",
  );

  resolveResult?.({
    code: code ?? "",
    state,
    error,
    errorDescription,
  });
}

function openExternalBrowser(url: string): void {
  if (process.platform === "win32") {
    const escapedUrl = url.replace(/'/g, "''");
    const launchers: Array<{ command: string; args: string[] }> = [
      {
        command: "powershell.exe",
        args: ["-NoProfile", "-Command", `Start-Process '${escapedUrl}'`],
      },
      {
        command: "explorer.exe",
        args: [url],
      },
      {
        command: "rundll32.exe",
        args: ["url.dll,FileProtocolHandler", url],
      },
    ];

    for (const launcher of launchers) {
      try {
        const child = spawn(launcher.command, launcher.args, {
          detached: true,
          stdio: "ignore",
        });
        child.unref();
        return;
      } catch {}
    }
    return;
  }

  if (process.platform === "darwin") {
    const child = spawn("open", [url], {
      detached: true,
      stdio: "ignore",
    });
    child.unref();
    return;
  }

  const child = spawn("xdg-open", [url], {
    detached: true,
    stdio: "ignore",
  });
  child.unref();
}

function createStateToken(): string {
  return toBase64Url(randomBytes(16));
}

function toBase64Url(value: Buffer): string {
  return value
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}
