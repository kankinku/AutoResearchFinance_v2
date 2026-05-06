import { describe, expect, test } from "vitest";

import {
  buildTradingViewCalibrationSource,
  diagnoseTvCalibrationIntegrityIssue,
} from "../../src/research/autonomous/tv-calibration-phase.js";

const generatedSpecPine = [
  "//@version=5",
  "// AF_SPEC_VERSION=af-spec/v1",
  "strategy(\"AF Spec Test\", overlay=true, process_orders_on_close=true, initial_capital=100000, commission_type=strategy.commission.percent, commission_value=0.05, pyramiding=18)",
  "entryPass = close < close[4]",
  "bearEvent = close > close[4]",
  "closeAllOnBearConfRiskOff = true",
  "f_trace(orderAction, exitReason) =>",
  "    \"AFTRACE|v1|barIndex=\" + str.tostring(bar_index)",
  "if entryPass",
  "    strategy.entry(\"AF-L\", strategy.long, comment=f_trace(\"entry\", \"none\"), alert_message=f_trace(\"entry\", \"none\"))",
  "if bearEvent and closeAllOnBearConfRiskOff",
  "    strategy.close_all(comment=f_trace(\"exit\", \"bear_event\"), alert_message=f_trace(\"exit\", \"bear_event\"))",
  "",
].join("\n");

describe("TradingView calibration phase", () => {
  test("adds a local evidence window guard to generated AF Pine", () => {
    const source = buildTradingViewCalibrationSource({
      source: generatedSpecPine,
      localArtifactBundle: {
        state: {
          eventTrace: [
            { time: "2023-05-31T13:30:00.000Z" },
            { time: "2026-04-28T19:30:00.000Z" },
          ],
        },
      } as never,
    });

    expect(source).toContain("AF_TV_CALIBRATION_WINDOW_START=2023-05-31T13:30:00.000Z");
    expect(source).toContain("afCalibrationStart = input.time(1685539800000");
    expect(source).toContain("if entryPass\n    if afCalibrationInWindow\n        strategy.entry");
    expect(source).toContain("calibration_window_end");
  });

  test("adds the calibration window guard to non-AF_SPEC Pine candidates", () => {
    const source = buildTradingViewCalibrationSource({
      source: [
        "//@version=5",
        "strategy(\"AF Seed 01 - Resolved Bull Event Recovery [cand-mut] [cand-95b5fcb4]\", overlay=true, pyramiding=30)",
        "if allowBull and array.size(slotIds) < maxSlots",
        "    strategy.entry(newId, strategy.long, qty=qtyNow)",
        "if useReplacement",
        "    strategy.order(",
        "        repId,",
        "        strategy.long,",
        "        qty=qtyNow",
        "    )",
        "",
      ].join("\n"),
      localArtifactBundle: {
        state: {
          eventTrace: [
            { time: "2023-06-07T18:30:00.000Z" },
            { time: "2026-04-15T14:30:00.000Z" },
          ],
        },
      } as never,
    });

    expect(source).toContain("AF_TV_CALIBRATION_WINDOW_START=2023-06-07T18:30:00.000Z");
    expect(source).toContain(
      "if allowBull and array.size(slotIds) < maxSlots\n    if afCalibrationInWindow\n        strategy.entry(newId, strategy.long, qty=qtyNow)",
    );
    expect(source).toContain(
      "if useReplacement\n    if afCalibrationInWindow\n        strategy.order(\n            repId,",
    );
  });

  test("does not add the calibration guard twice", () => {
    const once = buildTradingViewCalibrationSource({
      source: generatedSpecPine,
      localArtifactBundle: {
        state: {
          eventTrace: [
            { time: "2023-05-31T13:30:00.000Z" },
            { time: "2026-04-28T19:30:00.000Z" },
          ],
        },
      } as never,
    });
    const twice = buildTradingViewCalibrationSource({
      source: once,
      localArtifactBundle: {
        state: {
          eventTrace: [
            { time: "2023-05-31T13:30:00.000Z" },
            { time: "2026-04-28T19:30:00.000Z" },
          ],
        },
      } as never,
    });

    expect(twice).toBe(once);
  });

  test("flags TradingView artifacts from the wrong chart target", () => {
    const issue = diagnoseTvCalibrationIntegrityIssue({
      chartTarget: { symbol: "QQQ", timeframe: "120" },
      candidateSource: generatedSpecPine,
      localArtifactBundle: null,
      tvArtifactBundle: {
        state: {
          symbol: "CRYPTO:BTCUSD",
          timeframe: "120",
          attachedStudies: [],
        },
        trades: [],
      } as never,
      parityStatus: "major_drift",
    });

    expect(issue).toContain("chart_target_mismatch");
    expect(issue).toContain("actual=CRYPTO:BTCUSD:120");
  });
});
