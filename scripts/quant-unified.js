/* Unified Quant workspace: no iframe or cross-origin navigation.
   Client-side view switch retains the selected development generation/zoom.
   Neither mode triggers strategy training or live trading. */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const tabs = ["development", "oos", "operations"];
  let oosStarted = false;
  let operationsLoading = false;
  let lastView = "development";

  const pct = (value) => {
    if (value == null || !Number.isFinite(Number(value))) return "—";
    const val = Number(value);
    return (val > 0 ? "+" : "") + val.toLocaleString("ko-KR", {
      minimumFractionDigits: 1, maximumFractionDigits: 1,
    }) + "%";
  };
  const showMetric = (id, value) => {
    const node = $(id);
    if (node) node.textContent = value;
  };
  async function getJSON(url) {
    const response = await fetch(url, {
      cache: "no-store", headers: {Accept: "application/json"},
    });
    if (!response.ok) throw new Error("HTTP " + response.status);
    return response.json();
  }

  async function loadSummary() {
    const status = $("quant-period-message");
    try {
      const [dev, out] = await Promise.all([
        getJSON("api/chart/backtest"), getJSON("api/oos/2026-g124"),
      ]);
      const g124 = (dev.runs || []).find((row) =>
        row.generation === 124 &&
        row.run_id === "LAB_REPLAY_14626d55_G124" &&
        row.parameters?.replay_verified_original_audit === true &&
        row.status === "SUCCEEDED");
      if (!g124 || out.generation !== 124 ||
          out.status !== "VERIFIED_RETROSPECTIVE_NON_PIT_NOT_SEALED" ||
          out.original_strategy_hash !== g124.strategy_hash ||
          out.orders_enabled !== false) {
        throw new Error("G124 개발기간·2026년 검증 계보가 일치하지 않습니다.");
      }
      showMetric("quant-metric-dev", pct(g124.total_return * 100));
      showMetric("quant-metric-oos", pct(out.metrics.strategy_return_pct));
      showMetric("quant-metric-qqq", pct(out.metrics.qqq_return_pct));
      status.textContent = "개발기간은 원본 감사 검증 · 2026년은 G124만 사후 평가됨 " +
        "(봉인된 전향적 OOS 아님).";
    } catch (_) {
      ["quant-metric-dev","quant-metric-oos","quant-metric-qqq"].forEach((id) =>
        showMetric(id, "검증 자료 없음"));
      status.textContent = "개발기간과 2026년 검증의 출처 연결을 확인하지 못했습니다. " +
        "성과를 임의로 연결하지 않습니다.";
    }
  }

  async function loadOperations() {
    if (operationsLoading) return;
    operationsLoading = true;
    const status = $("quant-ops-status");
    status.textContent = "현재 연구 원장 조회 중";
    try {
      const overview = await getJSON("api/dashboard");
      // The origin's dashboard API is live; its research count is distinct
      // from the fixed 146-generation P9 chart evidence snapshot.
      const tests = overview.tests || [];
      const generation = Math.max(
        0, ...tests.map((entry) => Number(entry.generation) || 0));
      showMetric("quant-ops-generation", generation ? "G" + generation : "확인 불가");
      const best = overview.strategy || {};
      showMetric("quant-ops-best", best.generation == null ? "없음" :
        "G" + best.generation + " · " +
        pct((best.total_return ?? 0) * 100));
      const health = overview.health || {};
      showMetric("quant-ops-health",
        health.status === "HEALTHY" ? "정상" :
        health.status === "DEGRADED" ? "점검 필요" :
        (health.status || "확인 불가"));
      status.textContent = "원본 연구 대시보드 최신 조회: " +
        (overview.generated_at ? new Date(overview.generated_at).toLocaleString("ko-KR") : "알 수 없음") +
        " · 읽기 전용";
    } catch (_) {
      status.textContent = "연구 운영 상태를 가져오지 못했습니다. 기존 연구 원장은 변경되지 않았습니다.";
      showMetric("quant-ops-health", "연결 확인 필요");
    } finally {
      operationsLoading = false;
    }
  }

  function makeVisible(mode, record = true) {
    if (!tabs.includes(mode)) mode = "development";
    for (const item of tabs) {
      const panel = $("quant-panel-" + item);
      const tab = $("quant-tab-" + item);
      if (panel) panel.hidden = item !== mode;
      if (tab) {
        tab.setAttribute("aria-selected", String(item === mode));
        tab.tabIndex = item === mode ? 0 : -1;
      }
    }
    lastView = mode;
    const fragment = new URL(window.location.href);
    if (mode === "development") fragment.searchParams.delete("view");
    else fragment.searchParams.set("view", mode);
    if (record && fragment.href !== window.location.href) {
      window.history.pushState({quantView: mode}, "", fragment);
    }
    if (mode === "oos" && !oosStarted) {
      oosStarted = true;
      requestAnimationFrame(() => {
        window.dispatchEvent(new CustomEvent("quant:activate-oos"));
      });
    }
    if (mode === "operations") void loadOperations();
    if (mode === "development") {
      // Force a resize observation if the price chart was hidden.
      requestAnimationFrame(() => window.dispatchEvent(new Event("resize")));
    }
    const announcements = {
      development: "개발기간 차트: 2020~2025년, 원본 감사 재현.",
      oos: "G124의 2026년 사후 OOS 차트입니다. 봉인된 전향적 검증이 아닙니다.",
      operations: "원본 Quant 연구 운영 상태를 읽는 중입니다.",
    };
    $("quant-view-status").textContent = announcements[mode];
  }

  function jumpToG124() {
    makeVisible("development");
    const select = $("chart-run-select");
    if (select && [...select.options].some((opt) =>
        opt.value === "LAB_REPLAY_14626d55_G124")) {
      select.value = "LAB_REPLAY_14626d55_G124";
      select.dispatchEvent(new Event("change", {bubbles: true}));
    } else {
      $("quant-view-status").textContent =
        "G124 증거를 아직 불러오지 못했습니다. 선택 목록을 확인하세요.";
    }
  }

  // Quick range presets apply exactly the existing date-input flow. They do
  // not recalculate a backtest or any KPI.
  function dateOffset(iso, days) {
    const stamp = new Date(iso + "T12:00:00Z");
    if (Number.isNaN(stamp.getTime())) return iso;
    stamp.setUTCDate(stamp.getUTCDate() - days);
    return stamp.toISOString().slice(0, 10);
  }
  function chooseRange(dayCount) {
    const oos = lastView === "oos";
    if (lastView === "operations") return;
    const start = $(oos ? "oos-start" : "chart-date-start");
    const end = $(oos ? "oos-end" : "chart-date-end");
    const apply = $(oos ? "oos-zoom" : "chart-date-apply");
    const reset = $(oos ? "oos-reset" : "chart-reset-view");
    if (!start || !end || !apply || apply.disabled || !end.max) return;
    if (dayCount === 0) {
      reset?.click();
      return;
    }
    const until = end.value || end.max;
    const from = dateOffset(until, dayCount);
    start.value = from < start.min ? start.min : from;
    end.value = until > end.max ? end.max : until;
    apply.click();
  }

  document.addEventListener("DOMContentLoaded", () => {
    const shell = $("quant-panel-development");
    if (!shell) return;
    document.querySelectorAll("[data-quant-tab]").forEach((button) => {
      button.addEventListener("click", () =>
        makeVisible(button.getAttribute("data-quant-tab")));
      button.addEventListener("keydown", (evt) => {
        if (evt.key !== "ArrowLeft" && evt.key !== "ArrowRight") return;
        evt.preventDefault();
        const current = tabs.indexOf(button.getAttribute("data-quant-tab"));
        const next = tabs[(current + (evt.key === "ArrowRight" ? 1 : 2)) % tabs.length];
        makeVisible(next);
        $("quant-tab-" + next)?.focus();
      });
    });
    document.querySelectorAll("[data-quant-jump]").forEach((button) => {
      button.addEventListener("click", () => {
        if (button.getAttribute("data-quant-jump") === "g124") jumpToG124();
        else makeVisible("oos");
      });
    });
    document.querySelectorAll("[data-quant-period]").forEach((button) => {
      button.addEventListener("click", () =>
        chooseRange(Number(button.getAttribute("data-quant-period"))));
    });
    $("quant-ops-refresh")?.addEventListener("click", () => void loadOperations());
    window.addEventListener("popstate", () => {
      makeVisible(new URLSearchParams(window.location.search).get("view") || "development", false);
    });
    makeVisible(
      new URLSearchParams(window.location.search).get("view") || "development",
      false,
    );
    void loadSummary();
  });
})();
