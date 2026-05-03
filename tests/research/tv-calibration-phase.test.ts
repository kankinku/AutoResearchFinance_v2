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
    expect(source).toContain("if afCalibrationInWindow and entryPass");
    expect(source).toContain("if afCalibrationInWindow and bearEvent and closeAllOnBearConfRiskOff");
    expect(source).toContain("calibration_window_end");
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
