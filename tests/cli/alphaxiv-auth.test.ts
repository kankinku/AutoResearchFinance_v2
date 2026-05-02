import os from "node:os";
import path from "node:path";

import { describe, expect, test } from "vitest";

import {
  buildAlphaXivCookieHeader,
  resolveAlphaXivAuthFileCandidates,
  resolveAlphaXivSessionFileCandidates,
} from "../../src/cli/alphaxiv-auth.js";

describe("alphaxiv-auth", () => {
  test("includes preferred auth path first and keeps codex default", () => {
    const preferred = "C:\\temp\\alphaxiv-auth.json";
    const candidates = resolveAlphaXivAuthFileCandidates(preferred);

    expect(candidates[0]).toBe(preferred);
    expect(candidates).toContain(
      path.join(os.homedir(), ".codex", "alphaxiv-auth.json"),
    );
  });

  test("includes preferred session path first and keeps codex default", () => {
    const preferred = "C:\\temp\\alphaxiv-session.json";
    const candidates = resolveAlphaXivSessionFileCandidates(preferred);

    expect(candidates[0]).toBe(preferred);
    expect(candidates).toContain(
      path.join(os.homedir(), ".codex", "alphaxiv-session.json"),
    );
  });

  test("builds cookie header only from matching, non-expired cookies", () => {
    const header = buildAlphaXivCookieHeader(
      [
        {
          name: "__session",
          value: "sess",
          domain: ".alphaxiv.org",
          path: "/",
          expires: -1,
          httpOnly: true,
          secure: true,
          sameSite: "Lax",
        },
        {
          name: "__client_uat",
          value: "uat",
          domain: "api.alphaxiv.org",
          path: "/",
          expires: Date.now() / 1000 + 60,
          httpOnly: false,
          secure: true,
          sameSite: "Lax",
        },
        {
          name: "expired",
          value: "nope",
          domain: ".alphaxiv.org",
          path: "/",
          expires: Date.now() / 1000 - 60,
          httpOnly: false,
          secure: true,
          sameSite: "Lax",
        },
      ],
      "https://api.alphaxiv.org/mcp/v1",
    );

    expect(header).toBe("__session=sess; __client_uat=uat");
  });
});
