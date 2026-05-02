import { access, mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { describe, expect, test } from "vitest";

import {
  buildTwoHourBars,
  classifyMarketRegime,
  ensureQqqTwoHourContext,
} from "../../src/research/market-context.js";
import { resolveKnowledgePaths } from "../../src/state/knowledge-paths.js";

describe("market context", () => {
  test("compresses hourly QQQ bars into 2-hour bars", () => {
    const bars = buildTwoHourBars([
      {
        time: "2026-04-20T00:00:00.000Z",
        open: 100,
        high: 101,
        low: 99,
        close: 100.5,
        volume: 10,
      },
      {
        time: "2026-04-20T01:00:00.000Z",
        open: 100.5,
        high: 102,
        low: 100,
        close: 101.5,
        volume: 12,
      },
    ]);

    expect(bars).toHaveLength(1);
    expect(bars[0]?.close).toBe(101.5);
    expect(bars[0]?.volume).toBe(22);
  });

  test("classifies clear down-trend bars", () => {
    const regime = classifyMarketRegime({
      close: 95,
      ema20: 97,
      ema50: 100,
      ema200: 110,
      atrPercent: 2.2,
      bbWidth: 0.06,
    });

    expect(regime).toBe("trend_down");
  });

  test("uses an explicit state root for cached QQQ context", async () => {
    const workspaceRoot = await mkdtemp(path.join(tmpdir(), "af-market-workspace-"));
    const stateRoot = await mkdtemp(path.join(tmpdir(), "af-market-state-"));
    const knowledgePaths = resolveKnowledgePaths(stateRoot);
    const cachedBars = [
      {
        time: "2026-04-20T00:00:00.000Z",
        open: 100,
        high: 101,
        low: 99,
        close: 100.5,
        volume: 10,
        ema20: null,
        ema50: null,
        ema200: null,
        atr14: null,
        atrPercent: null,
        rsi14: null,
        bbWidth: null,
        ret3: null,
        ret10: null,
        regime: "range",
      },
    ];
    await mkdir(path.dirname(knowledgePaths.qqqTwoHourContextPath), {
      recursive: true,
    });
    await writeFile(
      knowledgePaths.qqqTwoHourContextPath,
      JSON.stringify({ bars: cachedBars }),
      "utf8",
    );

    const result = await ensureQqqTwoHourContext(workspaceRoot, {
      stateRoot,
      fetchImpl: async () => {
        throw new Error("explicit state root cache should avoid fetching");
      },
    });

    expect(result.cachePath).toBe(knowledgePaths.qqqTwoHourContextPath);
    expect(result.fromCache).toBe(true);
    expect(result.bars).toEqual(cachedBars);
    await expect(
      access(
        path.join(
          workspaceRoot,
          "state",
          "pi-autoresearch",
          "artifacts",
          "results",
          "qqq-2h-context.json",
        ),
      ),
    ).rejects.toThrow();
  });
});
