import os from "node:os";
import path from "node:path";

import { describe, expect, test } from "vitest";

import { resolveOpenAiOauthAuthFileCandidates } from "../../src/cli/openai-oauth.js";

describe("openai-oauth", () => {
  test("includes preferred auth path first and keeps defaults", () => {
    const preferred = "C:\\temp\\auth.json";
    const candidates = resolveOpenAiOauthAuthFileCandidates(preferred);

    expect(candidates[0]).toBe(preferred);
    expect(candidates).toContain(path.join(os.homedir(), ".codex", "auth.json"));
    expect(candidates).toContain(path.join(os.homedir(), ".chatgpt-local", "auth.json"));
  });
});
