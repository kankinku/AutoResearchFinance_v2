import { describe, expect, test } from "vitest";

import { DASHBOARD_CLIENT_SCRIPT } from "../../src/dashboard/static-client.js";
import {
  DASHBOARD_CONTEXT_SECTION,
  DASHBOARD_EXPLANATION_PAGE,
  DASHBOARD_HISTORY_PAGE,
  DASHBOARD_OVERVIEW_PAGE,
  DASHBOARD_STRATEGY_PAGE,
  DASHBOARD_VALIDATION_PAGE,
} from "../../src/dashboard/static-sections.js";
import { DASHBOARD_STYLES } from "../../src/dashboard/static-styles.js";
import { renderDashboardHtml } from "../../src/dashboard/static.js";

describe("renderDashboardHtml", () => {
  test("composes the split dashboard sections into one page", () => {
    const html = renderDashboardHtml();

    expect(html).toContain("<style>");
    expect(html).toContain(DASHBOARD_STYLES.trim().slice(0, 60));
    expect(html).toContain(DASHBOARD_CONTEXT_SECTION.trim().slice(0, 60));
    expect(html).toContain(DASHBOARD_OVERVIEW_PAGE.trim().slice(0, 60));
    expect(html).toContain(DASHBOARD_STRATEGY_PAGE.trim().slice(0, 60));
    expect(html).toContain(DASHBOARD_EXPLANATION_PAGE.trim().slice(0, 60));
    expect(html).toContain(DASHBOARD_VALIDATION_PAGE.trim().slice(0, 60));
    expect(html).toContain(DASHBOARD_HISTORY_PAGE.trim().slice(0, 60));
    expect(html).toContain(DASHBOARD_CLIENT_SCRIPT.trim().slice(0, 60));
    expect(html).toContain("refreshIntervalMs: 8000");
  });
});
