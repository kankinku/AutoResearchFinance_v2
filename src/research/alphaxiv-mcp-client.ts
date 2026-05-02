import type { AuthProvider } from "@modelcontextprotocol/client";
import {
  Client,
  SSEClientTransport,
  StreamableHTTPClientTransport,
} from "@modelcontextprotocol/client";

export interface AlphaXivMcpClient {
  listToolNames(): Promise<string[]>;
  callTool(name: string, args: Record<string, unknown>): Promise<string>;
  close(): Promise<void>;
}

interface CreateAlphaXivMcpClientInput {
  endpoint: string;
  bearerToken?: string;
  sessionCookieHeader?: string;
}

export async function createAlphaXivMcpClient(
  input: CreateAlphaXivMcpClientInput,
): Promise<AlphaXivMcpClient> {
  const authProvider: AuthProvider | undefined = input.bearerToken
    ? {
        token: async () => input.bearerToken!,
      }
    : undefined;
  const client = new Client({
    name: "af-research-refresh",
    version: "0.1.0",
  });
  const baseUrl = new URL(input.endpoint);
  const requestInit = input.sessionCookieHeader
    ? {
        headers: {
          Cookie: input.sessionCookieHeader,
        },
      }
    : undefined;
  let transport:
    | StreamableHTTPClientTransport
    | SSEClientTransport
    | null = null;

  try {
    transport = new StreamableHTTPClientTransport(
      baseUrl,
      {
        ...(authProvider ? { authProvider } : {}),
        ...(requestInit ? { requestInit } : {}),
      },
    );
    await client.connect(transport);
  } catch {
    transport = new SSEClientTransport(
      baseUrl,
      {
        ...(authProvider ? { authProvider } : {}),
        ...(requestInit ? { requestInit } : {}),
        ...(requestInit
          ? { eventSourceInit: { headers: requestInit.headers } as EventSourceInit }
          : {}),
      },
    );
    await client.connect(transport);
  }

  return {
    async listToolNames() {
      const result = await client.listTools();
      return result.tools.map((tool) => tool.name);
    },
    async callTool(name, args) {
      const result = await client.callTool({
        name,
        arguments: args,
      });
      return extractTextResult(result.content);
    },
    async close() {
      if (transport instanceof StreamableHTTPClientTransport) {
        try {
          await transport.terminateSession();
        } catch {
          // Ignore transport termination issues during shutdown.
        }
      }
      await client.close();
    },
  };
}

function extractTextResult(
  content: Array<
    | { type: "text"; text: string }
    | { type: "resource"; resource: { text?: string } }
    | { type: string }
  >,
): string {
  return content
    .map((item) => {
      if ("type" in item && item.type === "text" && "text" in item) {
        return item.text;
      }
      if ("type" in item && item.type === "resource" && "resource" in item) {
        return item.resource.text ?? "";
      }
      return "";
    })
    .filter(Boolean)
    .join("\n\n");
}
